"""MetaOrchestrator Tick state-machine and Agent barrier runner."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from Ouroboros.core.agents import AgentRuntime
from Ouroboros.core.schemas import (
    AgentAction,
    AgentPayload,
    AgentResults,
    AgentType,
    InternalVisibility,
    LifecycleState,
    OrderActionType,
    RunTickCommand,
    RunTickResult,
    RiskResult,
    RouteRef,
    RuntimeAgentLifecycleEvent,
    RuntimeTickStateEvent,
    SplitAgentPayloadResult,
    SCHEMA_VERSION,
    TickContext,
    TickState,
)


META_ORCHESTRATOR_TICK_SEQUENCE: tuple[TickState, ...] = (
    TickState.INIT_TICK,
    TickState.RELEASE_FACTS,
    TickState.PUBLISH_MARKET_VIEW,
    TickState.AGENT_STEP,
    TickState.BARRIER_WAIT,
    TickState.PAYLOAD_SPLIT,
    TickState.MATCH_AND_CLEAR,
    TickState.RISK_AND_LIFECYCLE,
    TickState.REFEREE_PUBLICATION,
    TickState.COMMIT_TICK,
)


@dataclass(frozen=True)
class TickStateTransition:
    current: TickState
    next_state: TickState | None


TickContextProvider = Callable[[RunTickCommand], Iterable[TickContext | Mapping[str, Any]]]
NextTickIdProvider = Callable[[RunTickCommand], str]
StateHandler = Callable[[RunTickCommand], Iterable[str] | None]


class MetaOrchestratorStateMachine:
    """State-machine runner for one Meta-Orchestrator Tick.

    External Layer 0/3/Referee work stays behind injected state handlers. This
    class owns Tick order and the Agent barrier timeout policy.
    """

    def __init__(
        self,
        initial_state: TickState = TickState.INIT_TICK,
        *,
        agent_runtime: AgentRuntime | None = None,
        tick_context_provider: TickContextProvider | None = None,
        next_tick_id_provider: NextTickIdProvider | None = None,
        state_handlers: Mapping[TickState | str, StateHandler] | None = None,
        agent_timeout_seconds: float = 15.0,
    ) -> None:
        if initial_state not in META_ORCHESTRATOR_TICK_SEQUENCE:
            raise ValueError(f"unknown Tick state: {initial_state!r}")
        if agent_timeout_seconds <= 0:
            raise ValueError("agent_timeout_seconds must be > 0")
        self._state = initial_state
        self.agent_runtime = agent_runtime or AgentRuntime()
        self.tick_context_provider = tick_context_provider or _empty_tick_contexts
        self.next_tick_id_provider = next_tick_id_provider or _same_tick_id
        self.state_handlers = {
            TickState(state): handler for state, handler in (state_handlers or {}).items()
        }
        self.agent_timeout_seconds = agent_timeout_seconds
        self.last_agent_payloads: dict[str, AgentPayload] = {}
        self.last_split_results: dict[str, SplitAgentPayloadResult] = {}
        self.last_runtime_tick_state_events: list[RuntimeTickStateEvent] = []
        self.last_agent_lifecycle_events: dict[str, RuntimeAgentLifecycleEvent] = {}
        self.last_lifecycle_actions: dict[str, dict[str, Any]] = {}

    @property
    def current_state(self) -> TickState:
        return self._state

    def transition_for(self, state: TickState | str) -> TickStateTransition:
        current = TickState(state)
        index = META_ORCHESTRATOR_TICK_SEQUENCE.index(current)
        next_state = (
            META_ORCHESTRATOR_TICK_SEQUENCE[index + 1]
            if index + 1 < len(META_ORCHESTRATOR_TICK_SEQUENCE)
            else None
        )
        return TickStateTransition(current=current, next_state=next_state)

    def can_advance(self) -> bool:
        return self.transition_for(self._state).next_state is not None

    def advance(self) -> TickStateTransition:
        transition = self.transition_for(self._state)
        if transition.next_state is None:
            return transition
        self._state = transition.next_state
        return transition

    def reset(self, state: TickState = TickState.INIT_TICK) -> None:
        if state not in META_ORCHESTRATOR_TICK_SEQUENCE:
            raise ValueError(f"unknown Tick state: {state!r}")
        self._state = state

    def run_tick(self, command: RunTickCommand | Mapping[str, Any]) -> RunTickResult:
        """Run one Tick synchronously, using asyncio.gather for Agent steps."""

        parsed = _coerce_command(command)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run_tick_async(parsed))
        raise RuntimeError("run_tick cannot be called from a running event loop; use run_tick_async")

    async def run_tick_async(
        self, command: RunTickCommand | Mapping[str, Any]
    ) -> RunTickResult:
        """Run one Tick and apply the documented timeout->hold policy."""

        parsed = _coerce_command(command)
        self.reset(TickState.INIT_TICK)
        published_event_ids: list[str] = []
        contexts: list[TickContext] = []
        completed = 0
        timeout = 0
        failed = 0
        previous_state: TickState | None = None
        active_agent_count = 0
        self.last_split_results = {}
        self.last_runtime_tick_state_events = []
        self.last_agent_lifecycle_events = {}
        self.last_lifecycle_actions = {}

        for state in META_ORCHESTRATOR_TICK_SEQUENCE:
            self._state = state

            if state == TickState.AGENT_STEP:
                contexts = [
                    item if isinstance(item, TickContext) else TickContext.from_dict(item)
                    for item in self.tick_context_provider(parsed)
                ]
                active_agent_count = len(contexts)
                completed, timeout, failed = await self._run_agent_barrier(contexts)
            elif state == TickState.PAYLOAD_SPLIT:
                self.last_split_results = {
                    context.agent_id: self.split_agent_payload(
                        self.last_agent_payloads[context.agent_id],
                        can_post_forum=context.constraints.can_post_forum,
                        allowed_actions=context.constraints.allowed_actions,
                    )
                    for context in contexts
                    if context.agent_id in self.last_agent_payloads
                }
            else:
                handler = self.state_handlers.get(state)
                if handler is not None:
                    event_ids = handler(parsed)
                    if event_ids:
                        published_event_ids.extend(str(item) for item in event_ids)

            self.last_runtime_tick_state_events.append(
                self._build_runtime_tick_state_event(
                    parsed=parsed,
                    state=state,
                    previous_state=previous_state,
                    active_agent_count=active_agent_count,
                    completed_agent_count=completed,
                    timeout_agent_count=timeout,
                )
            )
            previous_state = state

        return RunTickResult(
            schema_version=SCHEMA_VERSION,
            command_id=parsed.command_id,
            session_id=parsed.session_id,
            tick_id=parsed.tick_id,
            status="committed",
            next_tick_id=self.next_tick_id_provider(parsed),
            agent_results=AgentResults(
                completed=completed,
                timeout=timeout,
                failed=failed,
            ),
            published_event_ids=published_event_ids,
        )

    def split_agent_payload(
        self,
        payload: AgentPayload | Mapping[str, Any],
        *,
        can_post_forum: bool | None = None,
        allowed_actions: Iterable[OrderActionType] | None = None,
    ) -> SplitAgentPayloadResult:
        """Split one Agent payload into field-level control-plane routes."""

        parsed = payload if isinstance(payload, AgentPayload) else AgentPayload.from_dict(payload)
        allowed = set(allowed_actions) if allowed_actions is not None else None
        routes: list[RouteRef] = []
        dropped_fields: list[str] = []
        validation_status = "ok"

        action_type = parsed.action.action_type
        if action_type == OrderActionType.CANCEL:
            validation_status = "rejected"
            dropped_fields.append("action")
        elif allowed is not None and action_type not in allowed:
            validation_status = "rejected"
            dropped_fields.append("action")
        elif action_type in {OrderActionType.BUY, OrderActionType.SELL}:
            routes.append(
                RouteRef(
                    target="Order_Input",
                    event_id=self._route_event_id(
                        "order", parsed.agent_id, parsed.tick_id, action_type.value
                    ),
                )
            )
        else:
            dropped_fields.append("action")

        if parsed.thought is not None:
            routes.append(
                RouteRef(
                    target="UI_Audit",
                    event_id=self._route_event_id("audit_thought", parsed.agent_id, parsed.tick_id),
                )
            )
        if parsed.belief_shift is not None:
            routes.append(
                RouteRef(
                    target="UI_Audit",
                    event_id=self._route_event_id("audit_belief", parsed.agent_id, parsed.tick_id),
                )
            )
        if parsed.evidence_refs:
            routes.append(
                RouteRef(
                    target="UI_Audit",
                    event_id=self._route_event_id("audit_evidence", parsed.agent_id, parsed.tick_id),
                )
            )

        if parsed.forum_post is not None:
            if can_post_forum is False:
                validation_status = "rejected"
                dropped_fields.append("forum_post")
            else:
                routes.append(
                    RouteRef(
                        target="Forum_Rumors",
                        event_id=self._route_event_id(
                            "forum", parsed.agent_id, parsed.tick_id, parsed.forum_post.post_id
                        ),
                    )
                )

        if parsed.memory_update is not None:
            dropped_fields.append("memory_update")

        return SplitAgentPayloadResult(
            schema_version=SCHEMA_VERSION,
            tick_id=parsed.tick_id,
            trace_id=parsed.trace_id,
            agent_id=parsed.agent_id,
            routes=routes,
            dropped_fields=_unique_strings(dropped_fields),
            validation_status=validation_status,
        )

    def split_payload(
        self,
        payload: AgentPayload | Mapping[str, Any],
        *,
        can_post_forum: bool | None = None,
        allowed_actions: Iterable[OrderActionType] | None = None,
    ) -> SplitAgentPayloadResult:
        """Backward-compatible alias for split_agent_payload."""

        return self.split_agent_payload(
            payload,
            can_post_forum=can_post_forum,
            allowed_actions=allowed_actions,
        )

    def handle_lifecycle(
        self,
        risk_result: RiskResult | Mapping[str, Any],
        *,
        agent_type: AgentType = AgentType.RETAIL,
    ) -> dict[str, Any]:
        """Turn a Layer 3 risk result into an internal lifecycle decision."""

        parsed = risk_result if isinstance(risk_result, RiskResult) else RiskResult.from_dict(risk_result)
        lifecycle_state, decision, public_label = _lifecycle_decision_for_risk(parsed.risk_state)
        event = RuntimeAgentLifecycleEvent(
            agent_id=parsed.agent_id,
            agent_type=agent_type,
            lifecycle_state=lifecycle_state,
            reason_code=parsed.reason_code,
            public_label=public_label,
        )
        self.last_agent_lifecycle_events[parsed.agent_id] = event
        self.last_lifecycle_actions[parsed.agent_id] = {
            "schema_version": SCHEMA_VERSION,
            "tick_id": parsed.tick_id,
            "agent_id": parsed.agent_id,
            "lifecycle_state": lifecycle_state.value,
            "decision": decision,
            "order_event_id": (
                f"forced_liq_{_stable_id(parsed.agent_id)}_{_stable_id(parsed.tick_id)}"
                if decision == "forced_liquidation"
                else None
            ),
        }
        return self.last_lifecycle_actions[parsed.agent_id]

    async def _run_agent_barrier(
        self, contexts: list[TickContext]
    ) -> tuple[int, int, int]:
        self.last_agent_payloads = {}
        if not contexts:
            return 0, 0, 0

        tasks = [asyncio.create_task(self._act_agent(context)) for context in contexts]
        results: list[Any] | None = None
        timed_out = False
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.agent_timeout_seconds,
            )
        except asyncio.TimeoutError:
            timed_out = True
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        completed = 0
        failed = 0
        timeout = 0
        if results is not None:
            for context, result in zip(contexts, results, strict=True):
                if isinstance(result, Exception):
                    if _agent_runtime_raises_llm_errors(self.agent_runtime):
                        raise result
                    failed += 1
                    self.last_agent_payloads[context.agent_id] = _hold_payload(context)
                else:
                    completed += 1
                    self.last_agent_payloads[context.agent_id] = result
            return completed, timeout, failed

        for context, task in zip(contexts, tasks, strict=True):
            if task.cancelled():
                timeout += 1
                self.last_agent_payloads[context.agent_id] = _hold_payload(context)
                continue
            if not task.done():
                timeout += 1
                self.last_agent_payloads[context.agent_id] = _hold_payload(context)
                continue
            try:
                result = task.result()
            except asyncio.CancelledError:
                timeout += 1
                self.last_agent_payloads[context.agent_id] = _hold_payload(context)
            except Exception as exc:
                if _agent_runtime_raises_llm_errors(self.agent_runtime):
                    raise exc
                failed += 1
                self.last_agent_payloads[context.agent_id] = _hold_payload(context)
            else:
                completed += 1
                self.last_agent_payloads[context.agent_id] = result

        if timed_out and completed + failed + timeout < len(contexts):
            timeout = len(contexts) - completed - failed
        return completed, timeout, failed

    async def _act_agent(self, context: TickContext) -> AgentPayload:
        act_async = getattr(self.agent_runtime, "act_async", None)
        if act_async is not None:
            return await act_async(context)
        return await asyncio.to_thread(self.agent_runtime.act, context)

    def _build_runtime_tick_state_event(
        self,
        *,
        parsed: RunTickCommand,
        state: TickState,
        previous_state: TickState | None,
        active_agent_count: int,
        completed_agent_count: int,
        timeout_agent_count: int,
    ) -> RuntimeTickStateEvent:
        return RuntimeTickStateEvent(
            schema_version=SCHEMA_VERSION,
            event_id=self._route_event_id("runtime", parsed.command_id, parsed.tick_id, state.value),
            session_id=parsed.session_id,
            tick_id=parsed.tick_id,
            trace_id=parsed.trace_id,
            producer="meta_orchestrator",
            visibility=InternalVisibility.CONTROL_ONLY,
            state=state,
            previous_state=previous_state,
            active_agent_count=active_agent_count,
            completed_agent_count=completed_agent_count,
            timeout_agent_count=timeout_agent_count,
            can_advance=self.transition_for(state).next_state is not None,
        )

    @staticmethod
    def _route_event_id(prefix: str, *parts: str) -> str:
        stable = "_".join(_stable_id(part) for part in parts if part)
        return f"{prefix}_{stable}" if stable else prefix


def _coerce_command(command: RunTickCommand | Mapping[str, Any]) -> RunTickCommand:
    if isinstance(command, RunTickCommand):
        return command
    return RunTickCommand.from_dict(command)


def _empty_tick_contexts(_: RunTickCommand) -> Iterable[TickContext]:
    return []


def _same_tick_id(command: RunTickCommand) -> str:
    return command.tick_id


def _hold_payload(context: TickContext) -> AgentPayload:
    return AgentPayload(
        schema_version=SCHEMA_VERSION,
        tick_id=context.tick_id,
        trace_id=context.trace_id,
        agent_id=context.agent_id,
        action=AgentAction(action_type=OrderActionType.HOLD),
    )


def _agent_runtime_raises_llm_errors(agent_runtime: AgentRuntime) -> bool:
    return bool(getattr(agent_runtime, "raises_llm_errors", False))


def _lifecycle_decision_for_risk(risk_state: Any) -> tuple[LifecycleState, str, str]:
    parsed_state = risk_state if isinstance(risk_state, str) else getattr(risk_state, "value", risk_state)
    if parsed_state in {"margin_call", "liquidating"}:
        return LifecycleState.LIQUIDATING, "forced_liquidation", "Risk escalation routed to liquidation."
    if parsed_state == "terminated":
        return LifecycleState.TERMINATED, "terminate", "Agent terminated by risk policy."
    if parsed_state == "warning":
        return LifecycleState.SUSPENDED, "suspend", "Agent suspended pending review."
    return LifecycleState.ACTIVE, "continue", "Agent remains active."


def _unique_strings(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _stable_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_") or "unknown"

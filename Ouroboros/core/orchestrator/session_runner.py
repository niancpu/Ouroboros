"""In-process session runner that wires core modules into a Tick loop."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from Ouroboros.core.agents import AgentRuntime
from Ouroboros.core.chronos import (
    Chronos,
    InMemoryChronosRepository,
    InMemoryOfficialNewsPublisher,
)
from Ouroboros.core.clearing import ClearingConfig, ClearingHouse, SettlementResult
from Ouroboros.core.market_data import MarketDataPublisher
from Ouroboros.core.matching import MatchingConfig, MatchingEngine, OrderSubmissionResult
from Ouroboros.core.referee import ExchangeBroadcaster, UIAuditOfficer
from Ouroboros.core.routing import Channel, ChannelRouter
from Ouroboros.core.schemas import (
    AccountSnapshotEvent,
    AgentPayload,
    AgentPermissionProfile,
    AgentResults,
    AuditGraphEvent,
    CausalChainEvent,
    CreateSessionCommand,
    CreateSessionResult,
    ErrorCode,
    ForumRumorEvent,
    InternalVisibility,
    LifecycleState,
    MarketPriceEvent,
    OrderActionType,
    OrderInputEvent,
    OrderRejectEvent,
    ReleaseFactsResult,
    RiskResult,
    RunMode,
    RunTickCommand,
    RunTickResult,
    RuntimeAgentLifecycleEvent,
    RuntimeTickStateEvent,
    SCHEMA_VERSION,
    SchemaValidationError,
    SessionStatus,
    SplitAgentPayloadResult,
    TapeAlertEvent,
    TickContext,
    TickState,
    TradeBatch,
    WebEventEnvelope,
    WebVisibility,
    map_internal_visibility_to_web,
)
from Ouroboros.core.schemas.common import (
    coerce_enum,
    require_int,
    require_mapping,
    require_non_empty_str,
    require_number,
)
from Ouroboros.core.web_api.control_rest import (
    ControlRestError,
    filter_web_api_payload,
)

from .state_machine import META_ORCHESTRATOR_TICK_SEQUENCE, MetaOrchestratorStateMachine
from .agent_barrier import run_agent_barrier
from .session_utils import (
    default_session_id,
    frontend_safe_refs as filter_frontend_safe_refs,
    is_final_tick,
    next_tick_id,
    position_value,
    previous_tick_id,
    stable_id,
    tick_after_end,
)


DEFAULT_AGENT_DEADLINE_MS = 30_000
DEFAULT_SESSION_PREFIX = "sim"
GRAPH_LOG_PATH_ENV = "OUROBOROS_GRAPH_LOG_PATH"
DEFAULT_GRAPH_LOG_PATH = (
    Path(__file__).resolve().parents[3] / "logs" / "audit_graph_generation.jsonl"
)
FRONTEND_SAFE_EVENT_REF_PREFIXES = (
    "audit_graph_",
    "chain_",
    "mkt_",
    "tape_",
    "eod_",
    "forum_",
    "news_",
    "trade_",
)


@dataclass(frozen=True)
class SessionAgentSpec:
    """Agent permission and initial account data supplied to a session."""

    permission_profile: AgentPermissionProfile
    cash: float
    positions: Mapping[str, int] = field(default_factory=dict)
    mark_prices: Mapping[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SessionAgentSpec":
        data = require_mapping(data, "SessionAgentSpec")
        return cls(
            permission_profile=AgentPermissionProfile.from_dict(
                require_mapping(data.get("permission_profile"), "permission_profile")
            ),
            cash=require_number(data.get("cash"), "cash", minimum=0),
            positions=dict(require_mapping(data.get("positions", {}), "positions")),
            mark_prices=dict(require_mapping(data.get("mark_prices", {}), "mark_prices")),
        )

    @property
    def agent_id(self) -> str:
        return self.permission_profile.agent_id


@dataclass(frozen=True)
class SessionRunnerConfig:
    """Runtime policy knobs that do not belong to a domain module."""

    agent_timeout_seconds: float = 15.0
    agent_deadline_ms: int = DEFAULT_AGENT_DEADLINE_MS
    default_ttl_seconds: float = 60.0
    replay_buffer_size: int = 500

    def __post_init__(self) -> None:
        if self.agent_timeout_seconds <= 0:
            raise SchemaValidationError("agent_timeout_seconds must be > 0")
        if self.agent_deadline_ms <= 0:
            raise SchemaValidationError("agent_deadline_ms must be > 0")
        if self.default_ttl_seconds <= 0:
            raise SchemaValidationError("default_ttl_seconds must be > 0")
        if self.replay_buffer_size < 1:
            raise SchemaValidationError("replay_buffer_size must be >= 1")


@dataclass
class _SessionRuntime:
    command: CreateSessionCommand
    result: CreateSessionResult
    router: ChannelRouter
    chronos: Chronos
    official_news_publisher: "RoutingOfficialNewsPublisher"
    clearing_house: ClearingHouse
    matching_engine: MatchingEngine
    market_data: MarketDataPublisher
    exchange_broadcaster: ExchangeBroadcaster
    ui_audit_officer: UIAuditOfficer
    agent_runtime: AgentRuntime
    agent_specs: dict[str, SessionAgentSpec]
    status: SessionStatus = SessionStatus.CREATED
    tick_state: TickState = TickState.INIT_TICK
    current_tick_id: str = ""
    initialized: bool = False
    last_release_from_tick: str | None = None
    last_trace_id: str = "trace_session"
    last_market_event: MarketPriceEvent | None = None
    previous_market_event: MarketPriceEvent | None = None
    last_audit_graph: AuditGraphEvent | None = None
    recent_causal_chains: list[CausalChainEvent] = field(default_factory=list)
    last_trade_batch: TradeBatch | None = None
    last_order_submission: OrderSubmissionResult | None = None
    last_settlement: SettlementResult | None = None
    last_account_snapshots: dict[str, AccountSnapshotEvent] = field(default_factory=dict)
    last_risk_results: dict[str, RiskResult] = field(default_factory=dict)
    lifecycle_states: dict[str, LifecycleState] = field(default_factory=dict)
    lifecycle_events: dict[str, RuntimeAgentLifecycleEvent] = field(default_factory=dict)
    frontend_events: list[WebEventEnvelope] = field(default_factory=list)
    next_frontend_seq: int = 1
    continuous_worker: threading.Thread | None = None

    @property
    def session_id(self) -> str:
        return self.result.session_id


@dataclass
class _TickArtifacts:
    active_agent_ids: list[str] = field(default_factory=list)
    contexts: list[TickContext] = field(default_factory=list)
    payloads: dict[str, AgentPayload] = field(default_factory=dict)
    split_results: dict[str, SplitAgentPayloadResult] = field(default_factory=dict)
    order_inputs: list[OrderInputEvent] = field(default_factory=list)
    forum_events: list[ForumRumorEvent] = field(default_factory=list)
    ui_audit_events: list[dict[str, Any]] = field(default_factory=list)
    release_result: ReleaseFactsResult | None = None
    market_event: MarketPriceEvent | None = None
    tape_alerts: list[TapeAlertEvent] = field(default_factory=list)
    trade_batch: TradeBatch | None = None
    settlement: SettlementResult | None = None
    risk_results: list[RiskResult] = field(default_factory=list)
    order_rejects: list[OrderRejectEvent] = field(default_factory=list)
    completed_agent_count: int = 0
    timeout_agent_count: int = 0
    failed_agent_count: int = 0
    published_event_ids: list[str] = field(default_factory=list)


class RoutingOfficialNewsPublisher(InMemoryOfficialNewsPublisher):
    """Chronos publisher that records and routes Official_News events."""

    def __init__(self, router: ChannelRouter) -> None:
        super().__init__()
        self.router = router

    def publish_official_news(self, event: Any) -> None:
        super().publish_official_news(event)
        self.router.publish(Channel.OFFICIAL_NEWS, event, producer="chronos")


class SessionRunner:
    """Wire Chronos, routing, agents, Layer 3, Referee, and frontend replay.

    The runner implements the existing control-plane protocol shape used by
    ControlRestApi. It owns only session runtime metadata and orchestration
    state; domain SSOT remains in the injected core modules.
    """

    def __init__(
        self,
        *,
        chronos_repository: InMemoryChronosRepository | None = None,
        agent_profile_sets: Mapping[str, Iterable[SessionAgentSpec | Mapping[str, Any]]] | None = None,
        agent_specs: Iterable[SessionAgentSpec | Mapping[str, Any]] = (),
        agent_runtime: AgentRuntime | None = None,
        agent_runtime_factory: Callable[[], AgentRuntime] | None = None,
        clearing_config: ClearingConfig | None = None,
        matching_config: MatchingConfig | None = None,
        runner_config: SessionRunnerConfig | None = None,
        session_id_factory: Callable[[CreateSessionCommand, int], str] | None = None,
        frontend_event_sink: Callable[[WebEventEnvelope], None] | None = None,
    ) -> None:
        if agent_runtime is not None and agent_runtime_factory is not None:
            raise SchemaValidationError("use either agent_runtime or agent_runtime_factory")
        self._chronos_repository = chronos_repository or InMemoryChronosRepository()
        self._default_agent_specs = {
            spec.agent_id: spec for spec in (_coerce_agent_spec(item) for item in agent_specs)
        }
        self._agent_profile_sets = {
            profile_set_id: {
                spec.agent_id: spec
                for spec in (_coerce_agent_spec(item) for item in specs)
            }
            for profile_set_id, specs in (agent_profile_sets or {}).items()
        }
        self._agent_runtime_factory = agent_runtime_factory or (
            (lambda: agent_runtime) if agent_runtime is not None else AgentRuntime
        )
        self._clearing_config = clearing_config
        self._matching_config = matching_config
        self._config = runner_config or SessionRunnerConfig()
        self._session_id_factory = session_id_factory or (
            lambda command, sequence: default_session_id(
                command,
                sequence,
                prefix=DEFAULT_SESSION_PREFIX,
            )
        )
        self._frontend_event_sink = frontend_event_sink
        self._sessions: dict[str, _SessionRuntime] = {}
        self._orchestrator = MetaOrchestratorStateMachine(
            agent_timeout_seconds=self._config.agent_timeout_seconds
        )
        self._session_sequence = 0

    def set_frontend_event_sink(
        self,
        sink: Callable[[WebEventEnvelope], None] | None,
    ) -> None:
        """Install an optional realtime sink for newly published Web API events."""

        self._frontend_event_sink = sink

    def create_session(
        self, command: CreateSessionCommand | Mapping[str, Any]
    ) -> CreateSessionResult:
        parsed = _coerce_create_session(command)
        self._session_sequence += 1
        session_id = self._session_id_factory(parsed, self._session_sequence)
        if session_id in self._sessions:
            raise ControlRestError(
                ErrorCode.SESSION_STATE_CONFLICT,
                f"session already exists: {session_id}",
            )

        agent_specs = self._resolve_agent_specs(parsed.agent_profile_set)

        router = ChannelRouter(
            session_id=session_id,
            default_ttl_seconds=self._config.default_ttl_seconds,
        )
        publisher = RoutingOfficialNewsPublisher(router)
        chronos = Chronos(repository=self._chronos_repository, publisher=publisher)
        clearing_house = ClearingHouse(config=self._clearing_config)
        matching_engine = MatchingEngine(
            config=self._matching_config,
            order_ledger=clearing_house,
        )
        market_data = MarketDataPublisher(router=router)
        exchange_broadcaster = ExchangeBroadcaster(router=router)
        ui_audit_officer = UIAuditOfficer(router=router)
        agent_runtime = self._agent_runtime_factory()
        if agent_runtime is None:
            raise SchemaValidationError("agent_runtime_factory returned None")

        result = CreateSessionResult(
            schema_version=SCHEMA_VERSION,
            command_id=parsed.command_id,
            session_id=session_id,
            status=SessionStatus.CREATED,
            current_tick_id=parsed.start_tick_id,
            agent_count=len(agent_specs),
        )
        runtime = _SessionRuntime(
            command=parsed,
            result=result,
            router=router,
            chronos=chronos,
            official_news_publisher=publisher,
            clearing_house=clearing_house,
            matching_engine=matching_engine,
            market_data=market_data,
            exchange_broadcaster=exchange_broadcaster,
            ui_audit_officer=ui_audit_officer,
            agent_runtime=agent_runtime,
            agent_specs=dict(agent_specs),
            current_tick_id=parsed.start_tick_id,
            lifecycle_states={
                agent_id: LifecycleState.ACTIVE for agent_id in agent_specs
            },
        )
        self._sessions[session_id] = runtime
        return result

    def get_session(
        self, session_id: str, *, request_id: str, trace_id: str
    ) -> Mapping[str, Any]:
        runtime = self._require_session(session_id)
        return self._session_status_data(runtime)

    def start_session(
        self,
        session_id: str,
        *,
        mode: RunMode,
        command_id: str,
        trace_id: str,
    ) -> Mapping[str, Any]:
        mode = coerce_enum(RunMode, mode, "mode")
        if mode != RunMode.CONTINUOUS:
            raise ControlRestError(ErrorCode.BAD_REQUEST, "start mode must be continuous")
        runtime = self._require_session(session_id)
        self._ensure_status(runtime, {SessionStatus.CREATED, SessionStatus.PAUSED}, "start")
        runtime.status = SessionStatus.RUNNING
        runtime.continuous_worker = threading.Thread(
            target=self._run_continuous_session,
            name=f"ouroboros-session-{session_id}",
            kwargs={
                "runtime": runtime,
                "command_id": command_id,
                "trace_id": trace_id,
            },
            daemon=True,
        )
        runtime.continuous_worker.start()
        return {
            "session_id": session_id,
            "status": SessionStatus.RUNNING.value,
            "accepted": True,
        }

    def pause_session(
        self,
        session_id: str,
        *,
        reason: str,
        command_id: str,
        trace_id: str,
    ) -> Mapping[str, Any]:
        runtime = self._require_session(session_id)
        self._ensure_status(runtime, {SessionStatus.RUNNING}, "pause")
        runtime.status = SessionStatus.PAUSED
        return {
            "session_id": session_id,
            "status": runtime.status.value,
            "pause_after_state": TickState.COMMIT_TICK.value,
            "reason": require_non_empty_str(reason, "reason"),
        }

    def step_session(
        self,
        session_id: str,
        *,
        ticks: int,
        command_id: str,
        trace_id: str,
    ) -> Mapping[str, Any]:
        ticks = require_int(ticks, "ticks", minimum=1)
        if ticks != 1:
            raise ControlRestError(ErrorCode.BAD_REQUEST, "ticks must be 1")
        runtime = self._require_session(session_id)
        self._ensure_status(runtime, {SessionStatus.CREATED, SessionStatus.PAUSED}, "step")
        runtime.status = SessionStatus.RUNNING
        result = self._run_current_tick(
            runtime,
            command_id=command_id,
            trace_id=trace_id,
            mode=RunMode.STEP,
        )
        if runtime.status == SessionStatus.RUNNING:
            runtime.status = SessionStatus.PAUSED
        return {
            "session_id": session_id,
            "status": runtime.status.value,
            "scheduled_ticks": ticks,
            "tick_result": result.to_dict(),
        }

    def stop_session(
        self,
        session_id: str,
        *,
        reason: str,
        command_id: str,
        trace_id: str,
    ) -> Mapping[str, Any]:
        runtime = self._require_session(session_id)
        self._ensure_status(
            runtime,
            {SessionStatus.CREATED, SessionStatus.RUNNING, SessionStatus.PAUSED},
            "stop",
        )
        completion_reason = require_non_empty_str(reason, "reason")
        runtime.status = SessionStatus.COMPLETED
        return {
            "session_id": session_id,
            "status": runtime.status.value,
            "completion_reason": completion_reason,
        }

    def get_frontend_snapshot(
        self, session_id: str, *, request_id: str, trace_id: str
    ) -> Mapping[str, Any]:
        runtime = self._require_session(session_id)
        return filter_web_api_payload(
            {
                "session_id": session_id,
                "status": runtime.status.value,
                "last_seq": runtime.next_frontend_seq - 1,
                "current_tick_id": runtime.current_tick_id,
                "tick_state": runtime.tick_state.value,
                "market": (
                    runtime.last_market_event.to_dict()
                    if runtime.last_market_event is not None
                    else None
                ),
                "agents": [
                    self._agent_snapshot_data(runtime, agent_id)
                    for agent_id in sorted(runtime.agent_specs)
                ],
                "audit_graph": (
                    runtime.last_audit_graph.to_dict()
                    if runtime.last_audit_graph is not None
                    else {"nodes": [], "edges": []}
                ),
                "causal_chains": [
                    _causal_chain_summary(chain)
                    for chain in runtime.recent_causal_chains
                ],
            }
        )

    def get_frontend_events(
        self,
        session_id: str,
        *,
        from_seq: int,
        limit: int,
        request_id: str,
        trace_id: str,
    ) -> Mapping[str, Any]:
        runtime = self._require_session(session_id)
        from_seq = require_int(from_seq, "from_seq", minimum=0)
        limit = require_int(limit, "limit", minimum=1)
        events = [
            event.to_dict()
            for event in runtime.frontend_events
            if event.seq > from_seq
        ][:limit]
        next_from_seq = events[-1]["seq"] if events else from_seq
        return {
            "session_id": session_id,
            "events": events,
            "next_from_seq": next_from_seq,
            "has_more": any(event.seq > next_from_seq for event in runtime.frontend_events),
        }

    def run_tick(self, command: RunTickCommand | Mapping[str, Any]) -> RunTickResult:
        parsed = _coerce_run_tick(command)
        runtime = self._require_session(parsed.session_id)
        if parsed.tick_id != runtime.current_tick_id:
            raise ControlRestError(
                ErrorCode.SESSION_STATE_CONFLICT,
                "run_tick tick_id must match current session tick",
                details={
                    "current_tick_id": runtime.current_tick_id,
                    "requested_tick_id": parsed.tick_id,
                },
            )
        if runtime.status in {SessionStatus.COMPLETED, SessionStatus.FAILED}:
            raise ControlRestError(
                ErrorCode.SESSION_STATE_CONFLICT,
                f"run_tick is not allowed while session is {runtime.status.value}",
            )
        runtime.status = SessionStatus.RUNNING
        result = self._run_tick(runtime, parsed)
        if runtime.status == SessionStatus.RUNNING:
            runtime.status = SessionStatus.PAUSED
        return result

    def _run_current_tick(
        self,
        runtime: _SessionRuntime,
        *,
        command_id: str,
        trace_id: str,
        mode: RunMode,
    ) -> RunTickResult:
        command = RunTickCommand(
            schema_version=SCHEMA_VERSION,
            command_id=command_id,
            session_id=runtime.session_id,
            tick_id=runtime.current_tick_id,
            trace_id=trace_id,
            mode=mode,
        )
        return self._run_tick(runtime, command)

    def _run_continuous_session(
        self,
        *,
        runtime: _SessionRuntime,
        command_id: str,
        trace_id: str,
    ) -> None:
        tick_count = 0
        while runtime.status == SessionStatus.RUNNING:
            tick_count += 1
            try:
                self._run_current_tick(
                    runtime,
                    command_id=f"{command_id}_{tick_count:06d}",
                    trace_id=trace_id,
                    mode=RunMode.CONTINUOUS,
                )
            except ControlRestError:
                break
        runtime.continuous_worker = None

    def _run_tick(self, runtime: _SessionRuntime, command: RunTickCommand) -> RunTickResult:
        try:
            artifacts = _TickArtifacts(active_agent_ids=self._active_agent_ids(runtime))
            previous_state: TickState | None = None
            for state in META_ORCHESTRATOR_TICK_SEQUENCE:
                runtime.tick_state = state
                self._prepare_tick_state_artifacts(runtime, artifacts, state)
                self._publish_runtime_tick_state(
                    runtime,
                    command,
                    state=state,
                    previous_state=previous_state,
                    artifacts=artifacts,
                )
                self._apply_tick_state(runtime, command, artifacts, state)
                previous_state = state

            next_tick = next_tick_id(command.tick_id, runtime.command.tick_interval)
            result = RunTickResult(
                schema_version=SCHEMA_VERSION,
                command_id=command.command_id,
                session_id=runtime.session_id,
                tick_id=command.tick_id,
                status="committed",
                next_tick_id=next_tick,
                agent_results=AgentResults(
                    completed=artifacts.completed_agent_count,
                    timeout=artifacts.timeout_agent_count,
                    failed=artifacts.failed_agent_count,
                ),
                published_event_ids=artifacts.published_event_ids,
            )
            runtime.last_trace_id = command.trace_id
            if tick_after_end(next_tick, runtime.command.end_tick_id):
                runtime.status = SessionStatus.COMPLETED
            else:
                runtime.current_tick_id = next_tick
            runtime.result = CreateSessionResult(
                schema_version=SCHEMA_VERSION,
                command_id=runtime.result.command_id,
                session_id=runtime.session_id,
                status=runtime.status,
                current_tick_id=runtime.current_tick_id,
                agent_count=len(runtime.agent_specs),
            )
            return result
        except ControlRestError:
            runtime.status = SessionStatus.FAILED
            raise
        except Exception as exc:
            runtime.status = SessionStatus.FAILED
            self._publish_system_error(
                runtime,
                tick_id=command.tick_id,
                trace_id=command.trace_id,
                message="session runner failed",
            )
            raise ControlRestError(ErrorCode.INTERNAL_ERROR, "session runner failed") from exc

    def _ensure_initialized(self, runtime: _SessionRuntime, *, trace_id: str) -> None:
        if runtime.initialized:
            return
        seed = runtime.chronos.build_initial_market_seed(runtime.command)
        seed_price = seed.previous_close

        for spec in runtime.agent_specs.values():
            runtime.router.register_agent_permissions(spec.permission_profile)

        runtime.matching_engine.initialize_market(seed)
        runtime.market_data.initialize_market(
            seed,
            tick_id=runtime.command.start_tick_id,
            trace_id=trace_id,
            publish=False,
        )

        for spec in runtime.agent_specs.values():
            mark_prices = dict(spec.mark_prices) or {runtime.command.symbol: seed_price}
            runtime.clearing_house.open_account(
                agent_id=spec.agent_id,
                cash=spec.cash,
                positions=spec.positions,
                mark_prices=mark_prices,
            )
            snapshot = runtime.clearing_house.account_snapshot(
                spec.agent_id,
                tick_id=runtime.command.start_tick_id,
                trace_id=trace_id,
            )
            runtime.last_account_snapshots[spec.agent_id] = snapshot
            runtime.router.publish(
                Channel.ACCOUNT_SNAPSHOT,
                snapshot,
                producer="clearing_house",
            )

        runtime.initialized = True

    def _prepare_tick_state_artifacts(
        self,
        runtime: _SessionRuntime,
        artifacts: _TickArtifacts,
        state: TickState,
    ) -> None:
        if state == TickState.INIT_TICK:
            artifacts.active_agent_ids = self._active_agent_ids(runtime)
        if state == TickState.AGENT_STEP and not artifacts.active_agent_ids:
            artifacts.active_agent_ids = self._active_agent_ids(runtime)

    def _apply_tick_state(
        self,
        runtime: _SessionRuntime,
        command: RunTickCommand,
        artifacts: _TickArtifacts,
        state: TickState,
    ) -> None:
        if state == TickState.INIT_TICK:
            self._ensure_initialized(runtime, trace_id=command.trace_id)
            return
        if state == TickState.RELEASE_FACTS:
            self._release_facts(runtime, command, artifacts)
            return
        if state == TickState.PUBLISH_MARKET_VIEW:
            self._publish_pre_agent_market(runtime, command, artifacts)
            self._publish_account_snapshots(runtime, command)
            return
        if state == TickState.AGENT_STEP:
            artifacts.contexts = [
                self._build_tick_context(runtime, command, agent_id)
                for agent_id in artifacts.active_agent_ids
            ]

            def publish_agent_progress(completed: int, timeout: int, failed: int) -> None:
                artifacts.completed_agent_count = completed
                artifacts.timeout_agent_count = timeout
                artifacts.failed_agent_count = failed
                self._publish_runtime_tick_state(
                    runtime,
                    command,
                    state=TickState.AGENT_STEP,
                    previous_state=TickState.PUBLISH_MARKET_VIEW,
                    artifacts=artifacts,
                )

            (
                artifacts.completed_agent_count,
                artifacts.timeout_agent_count,
                artifacts.failed_agent_count,
                artifacts.payloads,
            ) = run_agent_barrier(
                runtime.agent_runtime,
                artifacts.contexts,
                timeout_seconds=self._config.agent_timeout_seconds,
                on_progress=publish_agent_progress,
            )
            return
        if state == TickState.BARRIER_WAIT:
            return
        if state == TickState.PAYLOAD_SPLIT:
            self._split_agent_payloads(runtime, artifacts)
            return
        if state == TickState.MATCH_AND_CLEAR:
            self._match_and_clear(runtime, command, artifacts)
            return
        if state == TickState.RISK_AND_LIFECYCLE:
            self._handle_risk_and_lifecycle(runtime, command, artifacts)
            return
        if state == TickState.REFEREE_PUBLICATION:
            self._publish_referee_outputs(runtime, command, artifacts)
            return
        if state == TickState.COMMIT_TICK:
            runtime.clearing_house.commit_tick(command.tick_id)
            runtime.last_release_from_tick = command.tick_id
            return

    def _release_facts(
        self,
        runtime: _SessionRuntime,
        command: RunTickCommand,
        artifacts: _TickArtifacts,
    ) -> None:
        release_from = runtime.last_release_from_tick or previous_tick_id(
            command.tick_id,
            runtime.command.tick_interval,
        )
        result = runtime.chronos.release_facts(
            {
                "schema_version": SCHEMA_VERSION,
                "command_id": f"cmd_release_{stable_id(command.command_id)}",
                "tick_id": command.tick_id,
                "trace_id": command.trace_id,
                "symbol": runtime.command.symbol,
                "release_window": {
                    "from": release_from,
                    "to": command.tick_id,
                },
            }
        )
        artifacts.release_result = result
        artifacts.published_event_ids.extend(result.published_event_ids)

    def _publish_pre_agent_market(
        self,
        runtime: _SessionRuntime,
        command: RunTickCommand,
        artifacts: _TickArtifacts,
    ) -> None:
        event = runtime.market_data.publish_market_view(
            symbol=runtime.command.symbol,
            tick_id=command.tick_id,
            trace_id=command.trace_id,
            lob_view=runtime.matching_engine.lob_view(runtime.command.symbol),
        )
        runtime.previous_market_event = runtime.last_market_event
        runtime.last_market_event = event
        artifacts.market_event = event
        artifacts.published_event_ids.append(event.event_id)
        self._publish_frontend_event(
            runtime,
            event_type="market.price",
            tick_id=command.tick_id,
            trace_id=command.trace_id,
            visibility=map_internal_visibility_to_web(event.visibility),
            payload=event.to_dict(),
        )

    def _publish_account_snapshots(
        self, runtime: _SessionRuntime, command: RunTickCommand
    ) -> None:
        for agent_id in self._active_agent_ids(runtime):
            snapshot = runtime.clearing_house.account_snapshot(
                agent_id,
                tick_id=command.tick_id,
                trace_id=command.trace_id,
            )
            runtime.last_account_snapshots[agent_id] = snapshot
            runtime.router.publish(
                Channel.ACCOUNT_SNAPSHOT,
                snapshot,
                producer="clearing_house",
            )
            self._publish_frontend_event(
                runtime,
                event_type="agent.account_snapshot",
                tick_id=command.tick_id,
                trace_id=command.trace_id,
                visibility=map_internal_visibility_to_web(snapshot.visibility),
                payload=snapshot.to_dict(),
            )

    def _build_tick_context(
        self,
        runtime: _SessionRuntime,
        command: RunTickCommand,
        agent_id: str,
    ) -> TickContext:
        spec = runtime.agent_specs[agent_id]
        inputs = runtime.router.build_agent_input_events(agent_id)
        can_post_forum = spec.permission_profile.publish_permissions.forum_post
        allowed_actions = [OrderActionType.HOLD.value]
        if spec.permission_profile.publish_permissions.order_action:
            allowed_actions.extend([OrderActionType.BUY.value, OrderActionType.SELL.value])
        if can_post_forum:
            allowed_actions.append(OrderActionType.POST_FORUM.value)
        return TickContext.from_dict(
            {
                "schema_version": SCHEMA_VERSION,
                "tick_id": command.tick_id,
                "trace_id": command.trace_id,
                "agent_id": agent_id,
                "agent_role": spec.permission_profile.agent_type.value,
                "public_inputs": {
                    Channel.OFFICIAL_NEWS.value: inputs.get(Channel.OFFICIAL_NEWS.value, []),
                    Channel.MARKET_PRICE.value: inputs.get(Channel.MARKET_PRICE.value, []),
                    Channel.TAPE_ALERTS.value: inputs.get(Channel.TAPE_ALERTS.value, []),
                    Channel.END_OF_DAY.value: inputs.get(Channel.END_OF_DAY.value, []),
                    Channel.FORUM_RUMORS.value: inputs.get(Channel.FORUM_RUMORS.value, []),
                },
                "private_inputs": {
                    Channel.ACCOUNT_SNAPSHOT.value: inputs.get(
                        Channel.ACCOUNT_SNAPSHOT.value, []
                    )
                },
                "constraints": {
                    "allowed_actions": allowed_actions,
                    "deadline_ms": self._config.agent_deadline_ms,
                    "can_post_forum": can_post_forum,
                },
            }
        )

    def _split_agent_payloads(
        self, runtime: _SessionRuntime, artifacts: _TickArtifacts
    ) -> None:
        contexts = {context.agent_id: context for context in artifacts.contexts}
        for agent_id, payload in artifacts.payloads.items():
            context = contexts[agent_id]
            split = self._orchestrator.split_agent_payload(
                payload,
                can_post_forum=context.constraints.can_post_forum,
                allowed_actions=context.constraints.allowed_actions,
            )
            artifacts.split_results[agent_id] = split
            route_ids = {route.target: route.event_id for route in split.routes}
            if "Order_Input" in route_ids:
                order = self._order_input_from_payload(
                    payload,
                    event_id=route_ids["Order_Input"],
                )
                runtime.router.publish(
                    Channel.ORDER_INPUT,
                    order,
                    producer="meta_orchestrator",
                )
                artifacts.order_inputs.append(order)
                artifacts.published_event_ids.append(order.event_id)
            if "Forum_Rumors" in route_ids and payload.forum_post is not None:
                forum = self._forum_event_from_payload(
                    payload,
                    event_id=route_ids["Forum_Rumors"],
                    agent_type=context.agent_role,
                )
                runtime.router.publish(
                    Channel.FORUM_RUMORS,
                    forum,
                    producer="meta_orchestrator",
                )
                artifacts.forum_events.append(forum)
                artifacts.published_event_ids.append(forum.event_id)
                self._publish_frontend_event(
                    runtime,
                    event_type="forum.post",
                    tick_id=forum.tick_id,
                    trace_id=forum.trace_id,
                    visibility=map_internal_visibility_to_web(forum.visibility),
                    payload=forum.to_dict(),
                )
            if any(route.target == "UI_Audit" for route in split.routes):
                internal_audit, frontend_audit = self._ui_audit_from_payload(
                    runtime,
                    payload,
                    context=context,
                    event_id=route_ids.get(
                        "UI_Audit",
                        f"audit_{stable_id(agent_id)}_{stable_id(payload.tick_id)}",
                    ),
                )
                runtime.router.publish(
                    Channel.UI_AUDIT,
                    internal_audit,
                    producer="meta_orchestrator",
                )
                artifacts.ui_audit_events.append(frontend_audit)
                artifacts.published_event_ids.append(internal_audit["event_id"])

    def _order_input_from_payload(
        self, payload: AgentPayload, *, event_id: str
    ) -> OrderInputEvent:
        action = payload.action
        return OrderInputEvent.from_dict(
            {
                "schema_version": SCHEMA_VERSION,
                "event_id": event_id,
                "tick_id": payload.tick_id,
                "trace_id": payload.trace_id,
                "producer": "meta_orchestrator",
                "visibility": InternalVisibility.CONTROL_ONLY.value,
                "agent_id": payload.agent_id,
                "symbol": action.symbol,
                "side": action.action_type.value,
                "order_type": action.order_type.value if action.order_type else None,
                "price": action.price,
                "quantity": action.quantity,
                "time_in_force": (
                    action.time_in_force.value if action.time_in_force else "day"
                ),
                "client_order_id": action.client_order_id,
            }
        )

    def _forum_event_from_payload(
        self,
        payload: AgentPayload,
        *,
        event_id: str,
        agent_type: str,
    ) -> ForumRumorEvent:
        if payload.forum_post is None:
            raise SchemaValidationError("forum_post is required")
        return ForumRumorEvent.from_dict(
            {
                "schema_version": SCHEMA_VERSION,
                "event_id": event_id,
                "tick_id": payload.tick_id,
                "trace_id": payload.trace_id,
                "producer": "meta_orchestrator",
                "visibility": InternalVisibility.PUBLIC.value,
                "post_id": payload.forum_post.post_id,
                "author_agent_id": payload.forum_post.author_agent_id,
                "author_type": agent_type,
                "text": payload.forum_post.text,
                "stance": payload.forum_post.stance.value,
                "created_tick_id": payload.forum_post.tick_id,
            }
        )

    def _ui_audit_from_payload(
        self,
        runtime: _SessionRuntime,
        payload: AgentPayload,
        *,
        context: TickContext,
        event_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        belief_shift = payload.belief_shift.to_dict() if payload.belief_shift else None
        evidence_refs = list(payload.evidence_refs)
        internal = {
            "schema_version": SCHEMA_VERSION,
            "event_id": event_id,
            "tick_id": payload.tick_id,
            "trace_id": payload.trace_id,
            "producer": "meta_orchestrator",
            "visibility": InternalVisibility.CONTROL_ONLY.value,
            "agent_id": payload.agent_id,
            "thought": payload.thought,
            "belief_shift": belief_shift,
            "evidence_refs": evidence_refs,
        }
        snapshot = runtime.last_account_snapshots.get(payload.agent_id)
        frontend = {
            **internal,
            "agent_type": context.agent_role,
            "belief_score": 0.5,
            "position_value": snapshot.market_value if snapshot else 0.0,
            "risk_state": snapshot.risk_state.value if snapshot else "normal",
            "evidence_refs": frontend_safe_refs(evidence_refs),
            "public_reason": "Agent decision audit.",
        }
        return internal, frontend

    def _match_and_clear(
        self,
        runtime: _SessionRuntime,
        command: RunTickCommand,
        artifacts: _TickArtifacts,
    ) -> None:
        submission = runtime.matching_engine.submit_orders(
            artifacts.order_inputs,
            tick_id=command.tick_id,
        )
        runtime.last_order_submission = submission
        artifacts.order_rejects.extend(submission.rejected_orders)
        trade_batch = runtime.matching_engine.match_orders(command.tick_id)
        settlement = runtime.clearing_house.settle_trade_batch(trade_batch)
        runtime.last_trade_batch = trade_batch
        runtime.last_settlement = settlement
        artifacts.trade_batch = trade_batch
        artifacts.settlement = settlement

        for snapshot in settlement.account_snapshots:
            runtime.last_account_snapshots[snapshot.agent_id] = snapshot
            runtime.router.publish(
                Channel.ACCOUNT_SNAPSHOT,
                snapshot,
                producer="clearing_house",
            )
            self._publish_frontend_event(
                runtime,
                event_type="agent.account_snapshot",
                tick_id=snapshot.tick_id,
                trace_id=snapshot.trace_id,
                visibility=map_internal_visibility_to_web(snapshot.visibility),
                payload=snapshot.to_dict(),
            )

        event = runtime.market_data.publish_market_view(
            symbol=runtime.command.symbol,
            tick_id=command.tick_id,
            trace_id=command.trace_id,
            trade_batch=trade_batch,
            lob_view=runtime.matching_engine.lob_view(runtime.command.symbol),
        )
        runtime.previous_market_event = artifacts.market_event or runtime.last_market_event
        runtime.last_market_event = event
        artifacts.market_event = event
        artifacts.published_event_ids.append(event.event_id)
        self._publish_frontend_event(
            runtime,
            event_type="market.price",
            tick_id=command.tick_id,
            trace_id=command.trace_id,
            visibility=map_internal_visibility_to_web(event.visibility),
            payload=event.to_dict(),
        )

    def _handle_risk_and_lifecycle(
        self,
        runtime: _SessionRuntime,
        command: RunTickCommand,
        artifacts: _TickArtifacts,
    ) -> None:
        batch_id = artifacts.trade_batch.batch_id if artifacts.trade_batch else "batch_none"
        forced_liquidation_orders: list[OrderInputEvent] = []
        for agent_id in artifacts.active_agent_ids:
            risk = runtime.clearing_house.risk_result(
                agent_id,
                batch_id=batch_id,
                tick_id=command.tick_id,
                trace_id=command.trace_id,
            )
            runtime.last_risk_results[agent_id] = risk
            artifacts.risk_results.append(risk)
            action = self._orchestrator.handle_lifecycle(
                risk,
                agent_type=runtime.agent_specs[agent_id].permission_profile.agent_type,
            )
            event = self._orchestrator.last_agent_lifecycle_events[agent_id]
            runtime.lifecycle_states[agent_id] = event.lifecycle_state
            runtime.lifecycle_events[agent_id] = event
            lifecycle_payload: dict[str, Any] = {
                **event.to_dict(),
                "decision": action["decision"],
            }
            if action["decision"] == "forced_liquidation":
                order, liquidation_status = self._forced_liquidation_order_from_action(
                    runtime,
                    command,
                    risk,
                    action,
                )
                lifecycle_payload.update(liquidation_status)
                if order is not None:
                    forced_liquidation_orders.append(order)
            self._publish_frontend_event(
                runtime,
                event_type="runtime.agent_lifecycle",
                tick_id=command.tick_id,
                trace_id=command.trace_id,
                visibility=WebVisibility.CONTROL_ONLY_VIEW,
                payload=lifecycle_payload,
            )
        if forced_liquidation_orders:
            self._submit_forced_liquidation_orders(
                runtime,
                command,
                artifacts,
                forced_liquidation_orders,
            )

    def _forced_liquidation_order_from_action(
        self,
        runtime: _SessionRuntime,
        command: RunTickCommand,
        risk: RiskResult,
        action: Mapping[str, Any],
    ) -> tuple[OrderInputEvent | None, dict[str, Any]]:
        order_event_id = str(
            action.get("order_event_id")
            or f"forced_liq_{stable_id(risk.agent_id)}_{stable_id(command.tick_id)}"
        )
        snapshot = runtime.clearing_house.account_snapshot(
            risk.agent_id,
            tick_id=command.tick_id,
            trace_id=command.trace_id,
        )
        available_quantity = snapshot.available_shares.get(runtime.command.symbol, 0)
        lot_size = runtime.matching_engine.config.lot_size
        liquidation_quantity = available_quantity - (available_quantity % lot_size)
        status = {
            "forced_liquidation_order_event_id": order_event_id,
            "forced_liquidation_order_status": "queued_for_layer3",
            "forced_liquidation_quantity": liquidation_quantity,
            "sellable_quantity": available_quantity,
        }
        if available_quantity <= 0:
            return None, {
                **status,
                "forced_liquidation_order_status": "skipped_no_sellable_position",
                "forced_liquidation_quantity": 0,
            }
        if liquidation_quantity <= 0:
            return None, {
                **status,
                "forced_liquidation_order_status": "skipped_below_lot_size",
                "forced_liquidation_quantity": 0,
            }
        order = OrderInputEvent.from_dict(
            {
                "schema_version": SCHEMA_VERSION,
                "event_id": order_event_id,
                "tick_id": command.tick_id,
                "trace_id": command.trace_id,
                "producer": "meta_orchestrator",
                "visibility": InternalVisibility.CONTROL_ONLY.value,
                "agent_id": risk.agent_id,
                "symbol": runtime.command.symbol,
                "side": "sell",
                "order_type": "market",
                "price": None,
                "quantity": liquidation_quantity,
                "time_in_force": "ioc",
                "client_order_id": f"system_forced_liquidation_{stable_id(risk.agent_id)}_{stable_id(command.tick_id)}",
                "order_kind": "forced_liquidation",
                "reason_code": risk.reason_code,
                "source_risk_state": risk.risk_state.value,
            }
        )
        return order, status

    def _submit_forced_liquidation_orders(
        self,
        runtime: _SessionRuntime,
        command: RunTickCommand,
        artifacts: _TickArtifacts,
        orders: list[OrderInputEvent],
    ) -> None:
        for order in orders:
            runtime.router.publish(
                Channel.ORDER_INPUT,
                order,
                producer="meta_orchestrator",
            )
            artifacts.order_inputs.append(order)
            artifacts.published_event_ids.append(order.event_id)

        submission = runtime.matching_engine.submit_orders(
            orders,
            tick_id=command.tick_id,
        )
        runtime.last_order_submission = submission
        artifacts.order_rejects.extend(submission.rejected_orders)
        if not submission.accepted_orders:
            return

        trade_batch = runtime.matching_engine.match_orders(command.tick_id)
        settlement = runtime.clearing_house.settle_trade_batch(trade_batch)
        runtime.last_trade_batch = trade_batch
        runtime.last_settlement = settlement
        artifacts.trade_batch = trade_batch
        artifacts.settlement = settlement

        for snapshot in settlement.account_snapshots:
            runtime.last_account_snapshots[snapshot.agent_id] = snapshot
            runtime.router.publish(
                Channel.ACCOUNT_SNAPSHOT,
                snapshot,
                producer="clearing_house",
            )
            self._publish_frontend_event(
                runtime,
                event_type="agent.account_snapshot",
                tick_id=snapshot.tick_id,
                trace_id=snapshot.trace_id,
                visibility=map_internal_visibility_to_web(snapshot.visibility),
                payload=snapshot.to_dict(),
            )

        if trade_batch.trades:
            event = runtime.market_data.publish_market_view(
                symbol=runtime.command.symbol,
                tick_id=command.tick_id,
                trace_id=command.trace_id,
                trade_batch=trade_batch,
                lob_view=runtime.matching_engine.lob_view(runtime.command.symbol),
            )
            runtime.previous_market_event = artifacts.market_event or runtime.last_market_event
            runtime.last_market_event = event
            artifacts.market_event = event
            artifacts.published_event_ids.append(event.event_id)
            self._publish_frontend_event(
                runtime,
                event_type="market.price",
                tick_id=command.tick_id,
                trace_id=command.trace_id,
                visibility=map_internal_visibility_to_web(event.visibility),
                payload=event.to_dict(),
            )

    def _publish_referee_outputs(
        self,
        runtime: _SessionRuntime,
        command: RunTickCommand,
        artifacts: _TickArtifacts,
    ) -> None:
        if artifacts.market_event is not None:
            alerts = runtime.exchange_broadcaster.publish_tape_alerts(
                artifacts.market_event,
                previous_market_output=runtime.previous_market_event,
            )
            artifacts.tape_alerts.extend(alerts)
            for alert in alerts:
                artifacts.published_event_ids.append(alert.event_id)
                self._publish_frontend_event(
                    runtime,
                    event_type="market.tape_alert",
                    tick_id=alert.tick_id,
                    trace_id=alert.trace_id,
                    visibility=map_internal_visibility_to_web(alert.visibility),
                    payload=alert.to_dict(),
                )

        audit_events = [
            *self._public_input_audit_events(runtime, command, artifacts),
            *self._enrich_audit_events_with_stigmergy_sources(artifacts),
        ]
        audit_graph = runtime.ui_audit_officer.publish_audit_graph(
            audit_events,
            event_id=f"audit_graph_{stable_id(command.tick_id)}",
            tick_id=command.tick_id,
            trace_id=command.trace_id,
        )
        _append_graph_generation_log(
            runtime=runtime,
            command=command,
            event_type="audit.graph",
            event_id=audit_graph.event_id,
            audit_graph=audit_graph,
            causal_chain_step_count=0,
        )
        runtime.last_audit_graph = audit_graph
        artifacts.published_event_ids.append(audit_graph.event_id)
        self._publish_frontend_event(
            runtime,
            event_type="audit.graph",
            tick_id=command.tick_id,
            trace_id=command.trace_id,
            visibility=map_internal_visibility_to_web(audit_graph.visibility),
            payload=audit_graph.to_dict(),
        )
        self._publish_causal_chain(
            runtime,
            command,
            artifacts,
            audit_graph=audit_graph,
        )
        if is_final_tick(command.tick_id, runtime.command.end_tick_id):
            self._publish_end_of_day(runtime, command, artifacts)

    def _publish_causal_chain(
        self,
        runtime: _SessionRuntime,
        command: RunTickCommand,
        artifacts: _TickArtifacts,
        *,
        audit_graph: AuditGraphEvent,
    ) -> None:
        steps = _causal_chain_steps(command, artifacts, audit_graph)
        if not steps:
            return
        chain_id = f"chain_{stable_id(command.tick_id)}"
        chain = runtime.ui_audit_officer.publish_causal_chain(
            event_id=chain_id,
            tick_id=command.tick_id,
            trace_id=command.trace_id,
            chain_id=chain_id,
            title="Tick public audit chain",
            summary="Public market, forum, and audit references were linked into a frontend-safe chain.",
            steps=steps,
            metrics={
                "affected_agent_count": len(audit_graph.nodes),
                "audit_edge_count": len(audit_graph.edges),
            },
            trades=artifacts.trade_batch,
        )
        _append_graph_generation_log(
            runtime=runtime,
            command=command,
            event_type="audit.causal_chain",
            event_id=chain.event_id,
            audit_graph=audit_graph,
            causal_chain_step_count=len(chain.steps),
        )
        runtime.recent_causal_chains.append(chain)
        while len(runtime.recent_causal_chains) > 20:
            runtime.recent_causal_chains.pop(0)
        artifacts.published_event_ids.append(chain.event_id)
        self._publish_frontend_event(
            runtime,
            event_type="audit.causal_chain",
            tick_id=command.tick_id,
            trace_id=command.trace_id,
            visibility=map_internal_visibility_to_web(chain.visibility),
            payload=chain.to_dict(),
        )

    def _publish_end_of_day(
        self,
        runtime: _SessionRuntime,
        command: RunTickCommand,
        artifacts: _TickArtifacts,
    ) -> None:
        market_event = artifacts.market_event or runtime.last_market_event
        if market_event is None:
            return
        event = runtime.exchange_broadcaster.publish_end_of_day(
            market_event,
            market_phase="closed",
            event_id=f"eod_{stable_id(runtime.command.symbol)}_{stable_id(command.tick_id)}",
        )
        artifacts.published_event_ids.append(event.event_id)
        self._publish_frontend_event(
            runtime,
            event_type="market.end_of_day",
            tick_id=event.tick_id,
            trace_id=event.trace_id,
            visibility=map_internal_visibility_to_web(event.visibility),
            payload=event.to_dict(),
        )

    def _public_input_audit_events(
        self,
        runtime: _SessionRuntime,
        command: RunTickCommand,
        artifacts: _TickArtifacts,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        market_event_id = artifacts.market_event.event_id if artifacts.market_event else None
        if market_event_id is not None:
            market_source = _market_graph_source_agent_id(runtime, artifacts)
            for agent_id in artifacts.active_agent_ids:
                links_to_market_source = market_source is not None and market_source != agent_id
                events.append(
                    self._frontend_audit_event(
                        runtime,
                        command,
                        agent_id=agent_id,
                        event_id=f"audit_market_{stable_id(agent_id)}_{stable_id(command.tick_id)}",
                        evidence_refs=[market_event_id] if links_to_market_source else [],
                        source_agent_id=market_source or agent_id,
                        belief_shift=0.18,
                        public_reason="公开行情快照进入该智能体本 Tick 可见输入。",
                    )
                )

        order_agent_by_id = {
            order.event_id: order.agent_id for order in artifacts.order_inputs
        }
        if artifacts.trade_batch is None:
            return events
        for trade in artifacts.trade_batch.trades:
            buy_agent = order_agent_by_id.get(trade.buy_order_id)
            sell_agent = order_agent_by_id.get(trade.sell_order_id)
            if buy_agent is not None:
                events.append(
                    self._frontend_audit_event(
                        runtime,
                        command,
                        agent_id=buy_agent,
                        event_id=f"audit_trade_buy_{stable_id(trade.event_id)}",
                        evidence_refs=[trade.event_id],
                        source_agent_id=sell_agent or "anonymous_order_flow",
                        belief_shift=0.55,
                        public_reason="公开成交把买方连接到同一条订单流链路。",
                    )
                )
            if sell_agent is not None:
                events.append(
                    self._frontend_audit_event(
                        runtime,
                        command,
                        agent_id=sell_agent,
                        event_id=f"audit_trade_sell_{stable_id(trade.event_id)}",
                        evidence_refs=[trade.event_id],
                        source_agent_id=buy_agent or "anonymous_order_flow",
                        belief_shift=0.55,
                        public_reason="公开成交把卖方连接到同一条订单流链路。",
                    )
                )
        return events

    def _frontend_audit_event(
        self,
        runtime: _SessionRuntime,
        command: RunTickCommand,
        *,
        agent_id: str,
        event_id: str,
        evidence_refs: list[str],
        source_agent_id: str,
        belief_shift: float,
        public_reason: str,
    ) -> dict[str, Any]:
        snapshot = runtime.last_account_snapshots.get(agent_id)
        spec = runtime.agent_specs[agent_id]
        return {
            "schema_version": SCHEMA_VERSION,
            "event_id": event_id,
            "tick_id": command.tick_id,
            "trace_id": command.trace_id,
            "producer": "meta_orchestrator",
            "visibility": InternalVisibility.CONTROL_ONLY.value,
            "agent_id": agent_id,
            "agent_type": spec.permission_profile.agent_type.value,
            "belief_score": 0.5,
            "position_value": snapshot.market_value if snapshot else 0.0,
            "risk_state": snapshot.risk_state.value if snapshot else "normal",
            "evidence_refs": evidence_refs,
            "source_agent_id": source_agent_id,
            "belief_shift": belief_shift,
            "public_reason": public_reason,
        }

    def _enrich_audit_events_with_stigmergy_sources(
        self,
        artifacts: _TickArtifacts,
    ) -> list[dict[str, Any]]:
        forum_author_by_ref: dict[str, str] = {}
        for forum in artifacts.forum_events:
            forum_author_by_ref[forum.post_id] = forum.author_agent_id
            forum_author_by_ref[forum.event_id] = forum.author_agent_id

        market_source = _dominant_market_source(artifacts)
        market_refs = set()
        if artifacts.market_event is not None:
            market_refs.add(artifacts.market_event.event_id)
        market_refs.update(alert.event_id for alert in artifacts.tape_alerts)

        enriched_events: list[dict[str, Any]] = []
        for raw in artifacts.ui_audit_events:
            event = dict(raw)
            refs = [ref for ref in event.get("evidence_refs", []) if isinstance(ref, str)]
            source_id = event.get("source_agent_id")

            if not source_id:
                forum_source = next(
                    (forum_author_by_ref[ref] for ref in refs if ref in forum_author_by_ref),
                    None,
                )
                if forum_source and forum_source != event.get("agent_id"):
                    event["source_agent_id"] = forum_source
                    event["public_reason"] = "公开股吧消息影响该 Agent 的信念或交易倾向。"
                elif market_source and market_source != event.get("agent_id") and _refs_market_medium(refs, market_refs):
                    event["source_agent_id"] = market_source
                    event["public_reason"] = "价格与订单簿变化影响该 Agent 的信念或风险暴露。"
            enriched_events.append(event)
        return enriched_events

    def _publish_runtime_tick_state(
        self,
        runtime: _SessionRuntime,
        command: RunTickCommand,
        *,
        state: TickState,
        previous_state: TickState | None,
        artifacts: _TickArtifacts,
    ) -> None:
        event = RuntimeTickStateEvent(
            schema_version=SCHEMA_VERSION,
            event_id=f"runtime_{stable_id(command.command_id)}_{stable_id(state.value)}",
            session_id=runtime.session_id,
            tick_id=command.tick_id,
            trace_id=command.trace_id,
            producer="meta_orchestrator",
            visibility=InternalVisibility.CONTROL_ONLY,
            state=state,
            previous_state=previous_state,
            active_agent_count=len(artifacts.active_agent_ids),
            completed_agent_count=artifacts.completed_agent_count,
            timeout_agent_count=artifacts.timeout_agent_count,
            failed_agent_count=artifacts.failed_agent_count,
            can_advance=state != TickState.COMMIT_TICK,
        )
        self._publish_frontend_event(
            runtime,
            event_type="runtime.tick_state",
            tick_id=command.tick_id,
            trace_id=command.trace_id,
            visibility=map_internal_visibility_to_web(event.visibility),
            payload=event.to_dict(),
        )

    def _publish_system_error(
        self,
        runtime: _SessionRuntime,
        *,
        tick_id: str,
        trace_id: str,
        message: str,
    ) -> None:
        self._publish_frontend_event(
            runtime,
            event_type="system.error",
            tick_id=tick_id,
            trace_id=trace_id,
            visibility=WebVisibility.CONTROL_ONLY_VIEW,
            payload={
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": message,
                "retryable": True,
            },
        )

    def _publish_frontend_event(
        self,
        runtime: _SessionRuntime,
        *,
        event_type: str,
        tick_id: str,
        trace_id: str,
        visibility: WebVisibility,
        payload: Mapping[str, Any],
    ) -> WebEventEnvelope:
        envelope = WebEventEnvelope.from_dict(
            {
                "schema_version": SCHEMA_VERSION,
                "seq": runtime.next_frontend_seq,
                "type": event_type,
                "session_id": runtime.session_id,
                "tick_id": tick_id,
                "trace_id": trace_id,
                "server_time": _server_time(),
                "visibility": visibility.value,
                "payload": filter_web_api_payload(dict(payload)),
            }
        )
        runtime.next_frontend_seq += 1
        runtime.frontend_events.append(envelope)
        while len(runtime.frontend_events) > self._config.replay_buffer_size:
            runtime.frontend_events.pop(0)
        if self._frontend_event_sink is not None:
            try:
                self._frontend_event_sink(envelope)
            except Exception:
                pass
        return envelope

    def _active_agent_ids(self, runtime: _SessionRuntime) -> list[str]:
        return [
            agent_id
            for agent_id in sorted(runtime.agent_specs)
            if runtime.lifecycle_states.get(agent_id) != LifecycleState.TERMINATED
        ]

    def _agent_snapshot_data(
        self, runtime: _SessionRuntime, agent_id: str
    ) -> dict[str, Any]:
        spec = runtime.agent_specs[agent_id]
        snapshot = runtime.last_account_snapshots.get(agent_id)
        risk = runtime.last_risk_results.get(agent_id)
        lifecycle = runtime.lifecycle_states.get(agent_id, LifecycleState.ACTIVE)
        initialposition_value = position_value(spec.positions, spec.mark_prices)
        data = {
            "agent_id": agent_id,
            "agent_type": spec.permission_profile.agent_type.value,
            "lifecycle_state": lifecycle.value,
            "risk_state": "normal",
            "equity": spec.cash + initialposition_value,
            "position_value": initialposition_value,
        }
        if snapshot is not None:
            data.update(
                {
                    "cash": snapshot.cash,
                    "available_cash": snapshot.available_cash,
                    "positions": snapshot.positions,
                    "available_shares": snapshot.available_shares,
                    "frozen_shares": snapshot.frozen_shares,
                    "market_value": snapshot.market_value,
                    "position_value": snapshot.market_value,
                    "equity": snapshot.equity,
                    "risk_state": snapshot.risk_state.value,
                }
            )
        if risk is not None:
            data.update(
                {
                    "drawdown_pct": risk.drawdown_pct,
                    "risk_reason_code": risk.reason_code,
                }
            )
        return data

    def _session_status_data(self, runtime: _SessionRuntime) -> dict[str, Any]:
        return {
            "session_id": runtime.session_id,
            "status": runtime.status.value,
            "current_tick_id": runtime.current_tick_id,
            "tick_state": runtime.tick_state.value,
            "agent_count": len(runtime.agent_specs),
            "active_agent_count": len(self._active_agent_ids(runtime)),
            "last_seq": runtime.next_frontend_seq - 1,
        }

    def _require_session(self, session_id: str) -> _SessionRuntime:
        session_id = require_non_empty_str(session_id, "session_id")
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise ControlRestError(ErrorCode.SESSION_NOT_FOUND, "session does not exist") from exc

    def _resolve_agent_specs(self, profile_set_id: str) -> dict[str, SessionAgentSpec]:
        profile_set_id = require_non_empty_str(profile_set_id, "agent_profile_set")
        if self._agent_profile_sets:
            try:
                return self._agent_profile_sets[profile_set_id]
            except KeyError as exc:
                raise ControlRestError(
                    ErrorCode.BAD_REQUEST,
                    f"unknown agent_profile_set: {profile_set_id}",
                ) from exc
        return self._default_agent_specs

    @staticmethod
    def _ensure_status(
        runtime: _SessionRuntime, allowed: set[SessionStatus], operation: str
    ) -> None:
        if runtime.status not in allowed:
            raise ControlRestError(
                ErrorCode.SESSION_STATE_CONFLICT,
                f"{operation} is not allowed while session is {runtime.status.value}",
                details={
                    "status": runtime.status.value,
                    "allowed_statuses": sorted(item.value for item in allowed),
                },
            )


def _coerce_agent_spec(value: SessionAgentSpec | Mapping[str, Any]) -> SessionAgentSpec:
    if isinstance(value, SessionAgentSpec):
        return value
    return SessionAgentSpec.from_dict(value)


def _coerce_create_session(
    command: CreateSessionCommand | Mapping[str, Any]
) -> CreateSessionCommand:
    if isinstance(command, CreateSessionCommand):
        return command
    return CreateSessionCommand.from_dict(command)


def _coerce_run_tick(command: RunTickCommand | Mapping[str, Any]) -> RunTickCommand:
    if isinstance(command, RunTickCommand):
        return command
    return RunTickCommand.from_dict(command)


def frontend_safe_refs(refs: Iterable[str]) -> list[str]:
    return filter_frontend_safe_refs(refs, FRONTEND_SAFE_EVENT_REF_PREFIXES)


def _causal_chain_summary(chain: CausalChainEvent) -> dict[str, Any]:
    return {
        "chain_id": chain.chain_id,
        "title": chain.title,
        "summary": chain.summary,
        "last_event_ref": chain.last_event_ref,
    }


def _append_graph_generation_log(
    *,
    runtime: _SessionRuntime,
    command: RunTickCommand,
    event_type: str,
    event_id: str,
    audit_graph: AuditGraphEvent,
    causal_chain_step_count: int,
) -> None:
    raw_path = os.environ.get(GRAPH_LOG_PATH_ENV)
    if raw_path is not None and not raw_path.strip():
        return
    path = Path(raw_path) if raw_path is not None else DEFAULT_GRAPH_LOG_PATH
    edge_summaries = [
        {
            "source": edge.source,
            "target": edge.target,
            "reason_ref": edge.reason_ref,
        }
        for edge in audit_graph.edges
    ]
    record = {
        "record_type": "graph_generation",
        "created_at": datetime.now(UTC).isoformat(),
        "session_id": runtime.session_id,
        "tick_id": command.tick_id,
        "event_type": event_type,
        "event_id": event_id,
        "nodes_count": len(audit_graph.nodes),
        "edges_count": len(audit_graph.edges),
        "causal_chain_steps_count": causal_chain_step_count,
        "edges": edge_summaries,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        return


def _causal_chain_steps(
    command: RunTickCommand,
    artifacts: _TickArtifacts,
    audit_graph: AuditGraphEvent,
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for forum in artifacts.forum_events:
        steps.append(
            _causal_step(
                steps,
                step_type="public_message",
                tick_id=command.tick_id,
                actor_id="public_forum",
                event_ref=forum.event_id,
                label="Forum",
                public_text="A public forum post entered the visible information set.",
            )
        )
    if artifacts.market_event is not None:
        steps.append(
            _causal_step(
                steps,
                step_type="price_move",
                tick_id=command.tick_id,
                actor_id="anonymous_market",
                event_ref=artifacts.market_event.event_id,
                label="Market",
                public_text="A public market snapshot was published for this Tick.",
            )
        )
    for alert in artifacts.tape_alerts:
        steps.append(
            _causal_step(
                steps,
                step_type="tape_alert",
                tick_id=command.tick_id,
                actor_id="exchange_broadcaster",
                event_ref=alert.event_id,
                label="Tape",
                public_text="An anonymous tape alert was linked to the audit trail.",
            )
        )
    if audit_graph.nodes or audit_graph.edges:
        steps.append(
            _causal_step(
                steps,
                step_type="belief_shift",
                tick_id=command.tick_id,
                actor_id="ui_audit_officer",
                event_ref=audit_graph.event_id,
                label="Audit",
                public_text="Frontend audit graph summarized public evidence and agent-level effects.",
            )
        )
    elif artifacts.ui_audit_events:
        steps.append(
            _causal_step(
                steps,
                step_type="belief_shift",
                tick_id=command.tick_id,
                actor_id="ui_audit_officer",
                event_ref=audit_graph.event_id,
                label="Audit",
                public_text="Frontend audit material existed, but no public evidence references were exposed.",
            )
        )
    if artifacts.trade_batch is not None and artifacts.trade_batch.trades:
        steps.append(
            _causal_step(
                steps,
                step_type="order_flow",
                tick_id=command.tick_id,
                actor_id="anonymous_order_flow",
                event_ref=f"trade_{stable_id(artifacts.trade_batch.batch_id)}",
                label="Trades",
                public_text="Anonymous trade count was attached without order or agent identifiers.",
            )
        )
    return steps


def _causal_step(
    existing_steps: list[dict[str, Any]],
    *,
    step_type: str,
    tick_id: str,
    actor_id: str,
    event_ref: str,
    label: str,
    public_text: str,
) -> dict[str, Any]:
    return {
        "step_id": f"step_{len(existing_steps) + 1:03d}",
        "step_type": step_type,
        "tick_id": tick_id,
        "actor_id": actor_id,
        "event_ref": event_ref,
        "label": label,
        "public_text": public_text,
    }


def _refs_market_medium(refs: Iterable[str], market_refs: set[str]) -> bool:
    for ref in refs:
        if ref in market_refs or ref.startswith(("mkt_", "tape_")):
            return True
    return False


def _dominant_market_source(artifacts: _TickArtifacts) -> str | None:
    quantities: dict[str, int] = {}
    for order in artifacts.order_inputs:
        if order.side.value not in {"buy", "sell"}:
            continue
        quantities[order.agent_id] = quantities.get(order.agent_id, 0) + order.quantity
    if not quantities:
        return None
    return max(sorted(quantities), key=lambda agent_id: quantities[agent_id])


def _market_graph_source_agent_id(
    runtime: _SessionRuntime,
    artifacts: _TickArtifacts,
) -> str | None:
    dominant_source = _dominant_market_source(artifacts)
    if dominant_source is not None:
        return dominant_source

    type_priority = {
        "hot_money": 0,
        "quant_algo": 1,
        "mutual_fund": 2,
        "national_team": 3,
        "retail": 4,
    }
    candidates = [
        agent_id
        for agent_id in artifacts.active_agent_ids
        if agent_id in runtime.agent_specs
    ]
    if len(candidates) < 2:
        return None
    return min(
        candidates,
        key=lambda agent_id: (
            type_priority.get(
                runtime.agent_specs[agent_id].permission_profile.agent_type.value,
                99,
            ),
            agent_id,
        ),
    )


def _server_time() -> str:
    return datetime.now(UTC).isoformat()


__all__ = [
    "RoutingOfficialNewsPublisher",
    "SessionAgentSpec",
    "SessionRunner",
    "SessionRunnerConfig",
]

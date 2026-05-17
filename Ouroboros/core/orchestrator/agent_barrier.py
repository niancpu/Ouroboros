"""Agent-step barrier execution for orchestrated ticks."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping

from Ouroboros.core.agents import AgentRuntime
from Ouroboros.core.schemas import AgentAction, AgentPayload, OrderActionType, TickContext


def hold_payload(context: TickContext) -> AgentPayload:
    return AgentPayload(
        schema_version="v1",
        tick_id=context.tick_id,
        trace_id=context.trace_id,
        agent_id=context.agent_id,
        action=AgentAction(action_type=OrderActionType.HOLD),
    )


def run_agent_barrier(
    agent_runtime: AgentRuntime,
    contexts: list[TickContext],
    *,
    timeout_seconds: float,
    on_progress: Callable[[int, int, int], None] | None = None,
) -> tuple[int, int, int, dict[str, AgentPayload]]:
    if not contexts:
        return 0, 0, 0, {}
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            _run_agent_barrier_async(
                agent_runtime,
                contexts,
                timeout_seconds=timeout_seconds,
                on_progress=on_progress,
            )
        )
    raise RuntimeError("SessionRunner.run_tick cannot run inside an active event loop")


async def _run_agent_barrier_async(
    agent_runtime: AgentRuntime,
    contexts: list[TickContext],
    *,
    timeout_seconds: float,
    on_progress: Callable[[int, int, int], None] | None = None,
) -> tuple[int, int, int, dict[str, AgentPayload]]:
    task_by_agent = {
        asyncio.create_task(_act_agent(agent_runtime, context)): context
        for context in contexts
    }
    pending = set(task_by_agent)
    completed = 0
    timeout = 0
    failed = 0
    payloads: dict[str, AgentPayload] = {}
    deadline = asyncio.get_running_loop().time() + timeout_seconds

    while pending:
        remaining_timeout = max(0.0, deadline - asyncio.get_running_loop().time())
        done, pending = await asyncio.wait(
            pending,
            timeout=remaining_timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in pending:
                context = task_by_agent[task]
                timeout += 1
                payloads[context.agent_id] = hold_payload(context)
                on_progress and on_progress(completed, timeout, failed)
            break

        for task in done:
            context = task_by_agent[task]
            try:
                payloads[context.agent_id] = task.result()
            except asyncio.CancelledError:
                timeout += 1
                payloads[context.agent_id] = hold_payload(context)
            except Exception as exc:
                if _agent_runtime_raises_llm_errors(agent_runtime):
                    for pending_task in pending:
                        pending_task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    raise exc
                failed += 1
                payloads[context.agent_id] = hold_payload(context)
            else:
                error = _agent_runtime_error(agent_runtime, context.agent_id)
                if error:
                    failed += 1
                    payloads[context.agent_id] = hold_payload(context)
                else:
                    completed += 1
            on_progress and on_progress(completed, timeout, failed)
    return completed, timeout, failed, payloads


def _agent_runtime_raises_llm_errors(agent_runtime: AgentRuntime) -> bool:
    return bool(getattr(agent_runtime, "raises_llm_errors", False))


async def _act_agent(agent_runtime: AgentRuntime, context: TickContext) -> AgentPayload:
    clear_error = getattr(agent_runtime, "clear_last_error", None)
    if clear_error is not None:
        clear_error(context.agent_id)
    act_async = getattr(agent_runtime, "act_async", None)
    if act_async is not None:
        return await act_async(context)
    return await asyncio.to_thread(agent_runtime.act, context)


def _agent_runtime_error(agent_runtime: AgentRuntime, agent_id: str) -> str | None:
    last_errors = getattr(agent_runtime, "last_errors", None)
    if last_errors is None:
        return None
    errors = last_errors() if callable(last_errors) else last_errors
    if isinstance(errors, Mapping):
        error = errors.get(agent_id)
        return str(error) if error else None
    return None

from __future__ import annotations

import unittest
import asyncio

from Ouroboros.core.orchestrator import (
    META_ORCHESTRATOR_TICK_SEQUENCE,
    MetaOrchestratorStateMachine,
)
from Ouroboros.core.schemas import (
    AgentAction,
    AgentPayload,
    InternalVisibility,
    OrderActionType,
    RiskState,
    SCHEMA_VERSION,
    TickContext,
    TickState,
)


class MetaOrchestratorStateMachineTests(unittest.TestCase):
    def test_tick_sequence_matches_contract_order(self) -> None:
        self.assertEqual(
            META_ORCHESTRATOR_TICK_SEQUENCE,
            (
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
            ),
        )

    def test_empty_state_machine_advances_without_side_effects(self) -> None:
        machine = MetaOrchestratorStateMachine()

        transition = machine.advance()

        self.assertEqual(transition.current, TickState.INIT_TICK)
        self.assertEqual(transition.next_state, TickState.RELEASE_FACTS)
        self.assertEqual(machine.current_state, TickState.RELEASE_FACTS)

    def test_run_tick_commits_empty_tick(self) -> None:
        machine = MetaOrchestratorStateMachine()

        result = machine.run_tick(run_tick_command())

        self.assertEqual(result.status, "committed")
        self.assertEqual(result.agent_results.completed, 0)
        self.assertEqual(result.agent_results.timeout, 0)
        self.assertEqual(machine.current_state, TickState.COMMIT_TICK)

    def test_run_tick_uses_gather_timeout_and_falls_back_to_hold(self) -> None:
        contexts = [tick_context("fast_agent"), tick_context("slow_agent")]
        machine = MetaOrchestratorStateMachine(
            agent_runtime=MixedRuntime(),
            tick_context_provider=lambda _: contexts,
            agent_timeout_seconds=0.05,
        )

        result = machine.run_tick(run_tick_command())

        self.assertEqual(result.agent_results.completed, 1)
        self.assertEqual(result.agent_results.timeout, 1)
        self.assertEqual(result.agent_results.failed, 0)
        self.assertEqual(
            machine.last_agent_payloads["slow_agent"].action.action_type,
            OrderActionType.HOLD,
        )

    def test_run_tick_raises_agent_error_when_strict_llm_mode_is_enabled(self) -> None:
        machine = MetaOrchestratorStateMachine(
            agent_runtime=StrictFailingRuntime(),
            tick_context_provider=lambda _: [tick_context("agent_a")],
        )

        with self.assertRaisesRegex(RuntimeError, "llm_provider_error"):
            machine.run_tick(run_tick_command())

    def test_run_tick_records_control_only_tick_state_events(self) -> None:
        machine = MetaOrchestratorStateMachine(
            tick_context_provider=lambda _: [tick_context("agent_a")]
        )

        machine.run_tick(run_tick_command())

        events = machine.last_runtime_tick_state_events
        self.assertEqual([event.state for event in events], list(META_ORCHESTRATOR_TICK_SEQUENCE))
        self.assertEqual(events[0].previous_state, None)
        self.assertEqual(events[-1].state, TickState.COMMIT_TICK)
        self.assertEqual(events[-1].visibility, InternalVisibility.CONTROL_ONLY)
        self.assertFalse(events[-1].can_advance)
        self.assertEqual(events[-1].active_agent_count, 1)
        self.assertNotIn("thought", repr([event.to_dict() for event in events]))

    def test_split_agent_payload_routes_only_field_level_targets(self) -> None:
        machine = MetaOrchestratorStateMachine()
        payload = AgentPayload.from_dict(
            {
                "schema_version": SCHEMA_VERSION,
                "tick_id": "2024-01-02T14:02:00+08:00",
                "trace_id": "trace_abc",
                "agent_id": "agent_a",
                "thought": "private rationale",
                "action": {
                    "action_type": "buy",
                    "symbol": "demo_stock",
                    "order_type": "limit",
                    "price": 15.2,
                    "quantity": 100,
                    "time_in_force": "day",
                },
                "evidence_refs": ["forum_post_001"],
                "memory_update": {
                    "should_write": True,
                    "summary": "private memory summary",
                },
            }
        )

        result = machine.split_agent_payload(payload, can_post_forum=False)

        self.assertEqual(result.validation_status, "ok")
        self.assertIn("memory_update", result.dropped_fields)
        self.assertEqual(
            {route.target for route in result.routes},
            {"Order_Input", "UI_Audit"},
        )
        route_dump = repr(result.to_dict())
        self.assertNotIn("private rationale", route_dump)
        self.assertNotIn("private memory summary", route_dump)

    def test_split_agent_payload_rejects_cancel_even_if_allowed_by_context(self) -> None:
        machine = MetaOrchestratorStateMachine()
        payload = AgentPayload.from_dict(
            {
                "schema_version": SCHEMA_VERSION,
                "tick_id": "2024-01-02T14:02:00+08:00",
                "trace_id": "trace_abc",
                "agent_id": "agent_a",
                "action": {"action_type": "cancel"},
            }
        )

        result = machine.split_agent_payload(
            payload,
            allowed_actions=[OrderActionType.CANCEL],
        )

        self.assertEqual(result.validation_status, "rejected")
        self.assertEqual(result.routes, [])
        self.assertIn("action", result.dropped_fields)

    def test_handle_lifecycle_returns_control_plane_decision_only(self) -> None:
        machine = MetaOrchestratorStateMachine()

        result = machine.handle_lifecycle(
            {
                "schema_version": SCHEMA_VERSION,
                "batch_id": "batch_risk",
                "tick_id": "2024-01-02T14:02:00+08:00",
                "trace_id": "trace_abc",
                "agent_id": "agent_a",
                "risk_state": RiskState.MARGIN_CALL.value,
                "equity": 4800.0,
                "drawdown_pct": 52.0,
                "reason_code": "equity_drawdown_limit",
            }
        )

        self.assertEqual(result["lifecycle_state"], "liquidating")
        self.assertEqual(result["decision"], "forced_liquidation")
        self.assertEqual(
            result["order_event_id"],
            "forced_liq_agent_a_2024_01_02T14_02_00_08_00",
        )
        self.assertEqual(
            machine.last_agent_lifecycle_events["agent_a"].reason_code,
            "equity_drawdown_limit",
        )


class MixedRuntime:
    async def act_async(self, context: TickContext) -> AgentPayload:
        if context.agent_id == "slow_agent":
            await asyncio.sleep(1)
        return AgentPayload(
            schema_version=SCHEMA_VERSION,
            tick_id=context.tick_id,
            trace_id=context.trace_id,
            agent_id=context.agent_id,
            action=AgentAction(action_type=OrderActionType.HOLD),
        )


class StrictFailingRuntime:
    raises_llm_errors = True

    async def act_async(self, context: TickContext) -> AgentPayload:
        raise RuntimeError("llm_provider_error")


def run_tick_command() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "command_id": "cmd_run_tick",
        "session_id": "sim_001",
        "tick_id": "2024-01-02T14:02:00+08:00",
        "trace_id": "trace_abc",
        "mode": "step",
    }


def tick_context(agent_id: str) -> TickContext:
    return TickContext.from_dict(
        {
            "schema_version": SCHEMA_VERSION,
            "tick_id": "2024-01-02T14:02:00+08:00",
            "trace_id": "trace_abc",
            "agent_id": agent_id,
            "agent_role": "retail",
            "public_inputs": {"market_price": {}},
            "private_inputs": {"account_snapshot": {}},
            "constraints": {
                "allowed_actions": ["buy", "sell", "hold"],
                "deadline_ms": 30000,
                "can_post_forum": False,
            },
        }
    )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest

from Ouroboros.core.agents import AgentRuntime
from Ouroboros.core.chronos import InMemoryChronosRepository
from Ouroboros.core.matching import MatchingConfig
from Ouroboros.core.orchestrator import SessionAgentSpec, SessionRunner
from Ouroboros.core.schemas import (
    CreateSessionCommand,
    RestSuccessResponse,
    SCHEMA_VERSION,
    SessionStatus,
)
from Ouroboros.core.web_api.control_rest import ControlRestApi, RestHttpRequest


SESSION_ID = "sim_runner_001"
SYMBOL = "demo_stock"
TICK = "2024-01-02T14:02:00+08:00"
NEXT_TICK = "2024-01-02T14:07:00+08:00"
TRACE = "trace_runner"


class SessionRunnerTests(unittest.TestCase):
    def test_create_session_is_lightweight_and_step_runs_full_tick(self) -> None:
        runner = session_runner()

        created = runner.create_session(create_command())

        self.assertEqual(created.status, SessionStatus.CREATED)
        snapshot_before = runner.get_frontend_snapshot(
            SESSION_ID,
            request_id="req_snapshot_before",
            trace_id=TRACE,
        )
        self.assertEqual(snapshot_before["last_seq"], 0)
        self.assertIsNone(snapshot_before["market"])

        step = runner.step_session(
            SESSION_ID,
            ticks=1,
            command_id="cmd_step_runner",
            trace_id=TRACE,
        )

        self.assertEqual(step["status"], "paused")
        self.assertEqual(step["tick_result"]["status"], "committed")
        self.assertEqual(step["tick_result"]["agent_results"]["completed"], 2)
        self.assertEqual(step["tick_result"]["agent_results"]["timeout"], 0)

        snapshot_after = runner.get_frontend_snapshot(
            SESSION_ID,
            request_id="req_snapshot_after",
            trace_id=TRACE,
        )
        self.assertEqual(snapshot_after["current_tick_id"], NEXT_TICK)
        self.assertEqual(snapshot_after["market"]["last_price"], 10.0)
        agents = {agent["agent_id"]: agent for agent in snapshot_after["agents"]}
        self.assertEqual(agents["buyer"]["positions"], {SYMBOL: 100})
        self.assertEqual(agents["seller"]["positions"], {SYMBOL: 900})

        events = runner.get_frontend_events(
            SESSION_ID,
            from_seq=0,
            limit=500,
            request_id="req_events",
            trace_id=TRACE,
        )["events"]
        event_types = {event["type"] for event in events}
        self.assertIn("runtime.tick_state", event_types)
        self.assertIn("market.price", event_types)
        self.assertIn("agent.account_snapshot", event_types)
        self.assertIn("audit.graph", event_types)
        self.assertNotIn("Order_Input", event_types)
        self.assertNotIn("UI_Audit", event_types)
        self.assertIn("news_runner_visible", step["tick_result"]["published_event_ids"])

        audit_events = [event for event in events if event["type"] == "audit.graph"]
        self.assertTrue(audit_events)
        audit_nodes = audit_events[-1]["payload"]["nodes"]
        self.assertEqual({node["agent_id"] for node in audit_nodes}, {"buyer", "seller"})

        rendered = json.dumps(events, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("private buyer alpha", rendered)
        self.assertNotIn("private seller alpha", rendered)
        self.assertNotIn("news_runner_future", rendered)
        self.assertNotIn("thought", rendered)

    def test_control_rest_api_can_drive_session_runner(self) -> None:
        runner = session_runner()
        api = ControlRestApi(control_plane=runner)

        create_response = api.handle(
            RestHttpRequest(
                method="POST",
                path="/api/v1/sessions",
                headers={
                    "X-Request-Id": "req_create",
                    "X-Trace-Id": TRACE,
                    "Content-Type": "application/json",
                },
                body={
                    "scenario_id": "runner_scenario",
                    "symbol": SYMBOL,
                    "agent_profile_set": "runner_agents",
                    "start_tick_id": TICK,
                    "end_tick_id": NEXT_TICK,
                    "tick_interval": "5m",
                },
            )
        )
        created = RestSuccessResponse.from_dict(create_response.body).to_dict()
        self.assertEqual(created["data"]["session_id"], SESSION_ID)
        self.assertEqual(created["data"]["status"], "created")

        step_response = api.handle(
            RestHttpRequest(
                method="POST",
                path=f"/api/v1/sessions/{SESSION_ID}/step",
                headers={
                    "X-Request-Id": "req_step",
                    "X-Trace-Id": TRACE,
                    "Content-Type": "application/json",
                },
                body={"ticks": 1},
            )
        )
        stepped = RestSuccessResponse.from_dict(step_response.body).to_dict()

        self.assertEqual(stepped["data"]["session_id"], SESSION_ID)
        self.assertEqual(stepped["data"]["status"], "paused")
        self.assertEqual(stepped["data"]["tick_result"]["status"], "committed")


def session_runner() -> SessionRunner:
    return SessionRunner(
        chronos_repository=chronos_repository(),
        agent_specs=agent_specs(),
        agent_runtime=AgentRuntime(scripted_actions=scripted_actions()),
        matching_config=MatchingConfig(lot_size=100),
        session_id_factory=lambda _command, _sequence: SESSION_ID,
    )


def create_command() -> CreateSessionCommand:
    return CreateSessionCommand.from_dict(
        {
            "schema_version": SCHEMA_VERSION,
            "command_id": "cmd_create_runner",
            "scenario_id": "runner_scenario",
            "symbol": SYMBOL,
            "agent_profile_set": "runner_agents",
            "start_tick_id": TICK,
            "end_tick_id": NEXT_TICK,
            "tick_interval": "5m",
        }
    )


def chronos_repository() -> InMemoryChronosRepository:
    return InMemoryChronosRepository.from_dicts(
        facts=[
            {
                "fact_id": "fact_runner_visible",
                "event_id": "news_runner_visible",
                "symbol": SYMBOL,
                "fact_time": "2024-01-02T14:01:00+08:00",
                "source_type": "announcement",
                "source_name": "exchange",
                "title": "Runner visible fact",
                "summary": "Visible in the runner tick.",
                "confidence": "official",
                "permission_tags": ["retail"],
            },
            {
                "fact_id": "fact_runner_future",
                "event_id": "news_runner_future",
                "symbol": SYMBOL,
                "fact_time": "2024-01-02T14:10:00+08:00",
                "source_type": "news",
                "source_name": "wire",
                "title": "Runner future fact",
                "summary": "Must stay hidden until a later tick.",
                "confidence": "official",
                "permission_tags": ["retail"],
            },
        ],
        initial_market_seeds={
            SYMBOL: {
                "schema_version": SCHEMA_VERSION,
                "seed_id": "seed_runner",
                "symbol": SYMBOL,
                "previous_close": 10.0,
                "limit_up": 11.0,
                "limit_down": 9.0,
                "initial_l2_snapshot": {"bids": [], "asks": []},
            }
        },
    )


def agent_specs() -> list[SessionAgentSpec]:
    return [
        SessionAgentSpec.from_dict(
            {
                "permission_profile": agent_profile("buyer"),
                "cash": 20_000.0,
                "positions": {},
                "mark_prices": {SYMBOL: 10.0},
            }
        ),
        SessionAgentSpec.from_dict(
            {
                "permission_profile": agent_profile("seller"),
                "cash": 1_000.0,
                "positions": {SYMBOL: 1_000},
                "mark_prices": {SYMBOL: 10.0},
            }
        ),
    ]


def agent_profile(agent_id: str) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "agent_id": agent_id,
        "agent_type": "retail",
        "subscriptions": ["Official_News", "Market_Price", "Account_Snapshot:self", "Forum_Rumors"],
        "publish_permissions": {
            "order_action": True,
            "ui_audit": True,
            "forum_post": False,
        },
        "official_news_scope": ["announcement", "news"],
    }


def scripted_actions() -> dict[str, list[dict[str, object]]]:
    return {
        "buyer": [
            {
                "schema_version": SCHEMA_VERSION,
                "tick_id": TICK,
                "trace_id": TRACE,
                "agent_id": "buyer",
                "thought": "private buyer alpha",
                "action": {
                    "action_type": "buy",
                    "symbol": SYMBOL,
                    "order_type": "limit",
                    "price": 10.0,
                    "quantity": 100,
                    "time_in_force": "day",
                },
            }
        ],
        "seller": [
            {
                "schema_version": SCHEMA_VERSION,
                "tick_id": TICK,
                "trace_id": TRACE,
                "agent_id": "seller",
                "thought": "private seller alpha",
                "action": {
                    "action_type": "sell",
                    "symbol": SYMBOL,
                    "order_type": "limit",
                    "price": 10.0,
                    "quantity": 100,
                    "time_in_force": "day",
                },
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()

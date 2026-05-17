from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Ouroboros.core.agents import AgentRuntime
from Ouroboros.core.chronos import InMemoryChronosRepository
from Ouroboros.core.clearing import ClearingConfig
from Ouroboros.core.matching import MatchingConfig
from Ouroboros.core.orchestrator import SessionAgentSpec, SessionRunner
from Ouroboros.core.orchestrator.session_runner import GRAPH_LOG_PATH_ENV
from Ouroboros.core.schemas import (
    CreateSessionCommand,
    RestSuccessResponse,
    SCHEMA_VERSION,
    SchemaValidationError,
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
        self.assertEqual(snapshot_before["audit_graph"], {"nodes": [], "edges": []})

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
        self.assertTrue(snapshot_after["causal_chains"])
        self.assertEqual(
            snapshot_after["causal_chains"][-1]["chain_id"],
            "chain_2024_01_02T14_02_00_08_00",
        )
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
        self.assertIn("audit.causal_chain", event_types)
        self.assertNotIn("Order_Input", event_types)
        self.assertNotIn("UI_Audit", event_types)
        self.assertIn("news_runner_visible", step["tick_result"]["published_event_ids"])

        audit_events = [event for event in events if event["type"] == "audit.graph"]
        self.assertTrue(audit_events)
        audit_nodes = audit_events[-1]["payload"]["nodes"]
        audit_edges = audit_events[-1]["payload"]["edges"]
        audit_node_ids = {node["agent_id"] for node in audit_nodes}
        self.assertEqual({node["agent_id"] for node in audit_nodes}, {"buyer", "seller"})
        self.assertTrue(audit_edges)
        self.assertTrue(
            all(
                edge["source"] in audit_node_ids and edge["target"] in audit_node_ids
                for edge in audit_edges
            )
        )
        self.assertTrue(any(edge["reason_ref"].startswith("mkt_") for edge in audit_edges))
        self.assertTrue(any(edge["reason_ref"].startswith("trade_") for edge in audit_edges))
        self.assertTrue(
            any(edge["source"] == "buyer" and edge["target"] == "seller" for edge in audit_edges)
        )

        chain_events = [event for event in events if event["type"] == "audit.causal_chain"]
        self.assertTrue(chain_events)
        chain_payload = chain_events[-1]["payload"]
        self.assertEqual(chain_payload["last_event_ref"], chain_payload["steps"][-1]["event_ref"])
        self.assertEqual(chain_payload["metrics"]["trade_count"], 1)
        self.assertIn(chain_payload["chain_id"], step["tick_result"]["published_event_ids"])

        rendered = json.dumps(events, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("private buyer alpha", rendered)
        self.assertNotIn("private seller alpha", rendered)
        self.assertNotIn("news_runner_future", rendered)
        self.assertNotIn("thought", rendered)
        self.assertNotIn("memory_update", rendered)

    def test_audit_graph_generation_log_is_appended(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "audit_graph_generation.jsonl"
            with patch.dict(os.environ, {GRAPH_LOG_PATH_ENV: str(log_path)}, clear=False):
                runner = session_runner()
                runner.create_session(create_command())

                runner.step_session(
                    SESSION_ID,
                    ticks=1,
                    command_id="cmd_step_graph_log",
                    trace_id=TRACE,
                )

            lines = log_path.read_text(encoding="utf-8").splitlines()

        self.assertGreaterEqual(len(lines), 2)
        records = [json.loads(line) for line in lines]
        event_types = {record["event_type"] for record in records}
        self.assertIn("audit.graph", event_types)
        self.assertIn("audit.causal_chain", event_types)
        for record in records:
            self.assertEqual(record["session_id"], SESSION_ID)
            self.assertEqual(record["tick_id"], TICK)
            self.assertTrue(record["event_id"])
            self.assertEqual(record["nodes_count"], 2)
            self.assertGreater(record["edges_count"], 0)
            self.assertTrue(record["edges"])
            self.assertIn("source", record["edges"][0])
            self.assertIn("target", record["edges"][0])
            self.assertIn("reason_ref", record["edges"][0])
        chain_records = [
            record for record in records if record["event_type"] == "audit.causal_chain"
        ]
        self.assertTrue(any(record["causal_chain_steps_count"] > 0 for record in chain_records))

    def test_market_only_tick_still_generates_frontend_renderable_graph_edges(self) -> None:
        runner = market_only_session_runner()
        runner.create_session(create_command())

        runner.step_session(
            SESSION_ID,
            ticks=1,
            command_id="cmd_step_market_only_graph",
            trace_id=TRACE,
        )

        events = runner.get_frontend_events(
            SESSION_ID,
            from_seq=0,
            limit=500,
            request_id="req_market_only_graph",
            trace_id=TRACE,
        )["events"]
        audit_events = [event for event in events if event["type"] == "audit.graph"]
        self.assertTrue(audit_events)
        graph = audit_events[-1]["payload"]
        node_ids = {node["agent_id"] for node in graph["nodes"]}
        self.assertEqual(node_ids, {"buyer", "seller"})
        self.assertTrue(graph["edges"])
        self.assertTrue(
            all(
                edge["source"] in node_ids
                and edge["target"] in node_ids
                and edge["source"] != edge["target"]
                for edge in graph["edges"]
            )
        )
        self.assertTrue(any(edge["reason_ref"].startswith("mkt_") for edge in graph["edges"]))

    def test_audit_graph_generation_log_write_failure_does_not_fail_tick(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "missing_parent" / "audit_graph_generation.jsonl"
            with patch.dict(os.environ, {GRAPH_LOG_PATH_ENV: str(log_path)}, clear=False), patch(
                "pathlib.Path.mkdir",
                side_effect=OSError("cannot create log directory"),
            ):
                runner = session_runner()
                runner.create_session(create_command())

                step = runner.step_session(
                    SESSION_ID,
                    ticks=1,
                    command_id="cmd_step_graph_log_failure",
                    trace_id=TRACE,
                )

        self.assertEqual(step["status"], "running")
        self.assertIn("audit_graph_2024_01_02t14_02_00_08_00", step["tick_result"]["published_event_ids"])

    def test_final_tick_publishes_end_of_day(self) -> None:
        runner = session_runner()
        runner.create_session(create_command(end_tick_id=TICK))

        step = runner.step_session(
            SESSION_ID,
            ticks=1,
            command_id="cmd_step_final_tick",
            trace_id=TRACE,
        )

        events = runner.get_frontend_events(
            SESSION_ID,
            from_seq=0,
            limit=500,
            request_id="req_events_eod",
            trace_id=TRACE,
        )["events"]
        eod_events = [event for event in events if event["type"] == "market.end_of_day"]
        self.assertTrue(eod_events)
        eod_payload = eod_events[-1]["payload"]
        self.assertEqual(eod_payload["symbol"], SYMBOL)
        self.assertEqual(eod_payload["close_price"], 10.0)
        self.assertIn(eod_payload["event_id"], step["tick_result"]["published_event_ids"])
        self.assertEqual(step["status"], "completed")

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

    def test_frontend_event_sink_receives_events_during_tick_publication(self) -> None:
        pushed: list[dict[str, object]] = []
        runner = session_runner(frontend_event_sink=lambda event: pushed.append(event.to_dict()))
        runner.create_session(create_command())

        runner.step_session(
            SESSION_ID,
            ticks=1,
            command_id="cmd_step_realtime_sink",
            trace_id=TRACE,
        )

        pushed_types = [event["type"] for event in pushed]
        self.assertGreater(len(pushed), 1)
        self.assertEqual(pushed[0]["seq"], 1)
        self.assertEqual(pushed_types[0], "runtime.tick_state")
        self.assertIn("market.price", pushed_types)
        self.assertIn("audit.graph", pushed_types)
        self.assertEqual([event["seq"] for event in pushed], sorted(event["seq"] for event in pushed))

    def test_strict_llm_agent_failure_fails_tick_and_publishes_system_error(self) -> None:
        runner = SessionRunner(
            chronos_repository=chronos_repository(),
            agent_specs=agent_specs(),
            agent_runtime=AgentRuntime(
                llm_gateway=FailingGateway(),
                allow_prompt_profile_fallback=True,
                raise_llm_errors=True,
            ),
            matching_config=MatchingConfig(lot_size=100),
            session_id_factory=lambda _command, _sequence: SESSION_ID,
        )
        runner.create_session(create_command())

        with self.assertRaisesRegex(Exception, "session runner failed"):
            runner.step_session(
                SESSION_ID,
                ticks=1,
                command_id="cmd_step_llm_failure",
                trace_id=TRACE,
            )

        events = runner.get_frontend_events(
            SESSION_ID,
            from_seq=0,
            limit=500,
            request_id="req_events_llm_failure",
            trace_id=TRACE,
        )["events"]
        self.assertEqual(runner._sessions[SESSION_ID].status, SessionStatus.FAILED)
        self.assertTrue(any(event["type"] == "system.error" for event in events))
        self.assertFalse(any(event["payload"].get("state") == "commit_tick" for event in events))

    def test_margin_call_generates_forced_liquidation_order_through_layer3(self) -> None:
        runner = liquidation_session_runner(
            risk_seller_position=200,
            include_second_buyer=True,
        )
        runner.create_session(create_command())

        step = runner.step_session(
            SESSION_ID,
            ticks=1,
            command_id="cmd_step_forced_liq",
            trace_id=TRACE,
        )

        runtime = runner._sessions[SESSION_ID]
        self.assertIsNotNone(runtime.last_order_submission)
        forced_orders = [
            order
            for order in runtime.last_order_submission.accepted_orders
            if order.order_kind.value == "forced_liquidation"
        ]
        self.assertEqual(len(forced_orders), 1)
        forced_order = forced_orders[0]
        self.assertEqual(forced_order.agent_id, "risk_seller")
        self.assertEqual(forced_order.side.value, "sell")
        self.assertEqual(forced_order.order_type.value, "market")
        self.assertEqual(forced_order.time_in_force.value, "ioc")
        self.assertEqual(forced_order.quantity, 100)
        self.assertEqual(forced_order.source_risk_state.value, "margin_call")
        self.assertIn(forced_order.event_id, step["tick_result"]["published_event_ids"])

        self.assertIsNotNone(runtime.last_trade_batch)
        self.assertEqual(
            [trade.sell_order_id for trade in runtime.last_trade_batch.trades],
            [forced_order.event_id],
        )
        snapshot = runtime.last_account_snapshots["risk_seller"]
        self.assertEqual(snapshot.positions, {})

        lifecycle_payload = lifecycle_payload_for(runner, "risk_seller")
        self.assertEqual(lifecycle_payload["lifecycle_state"], "liquidating")
        self.assertEqual(lifecycle_payload["decision"], "forced_liquidation")
        self.assertEqual(
            lifecycle_payload["forced_liquidation_order_status"],
            "queued_for_layer3",
        )
        self.assertEqual(lifecycle_payload["forced_liquidation_quantity"], 100)

    def test_margin_call_without_sellable_position_marks_lifecycle_without_order(self) -> None:
        runner = liquidation_session_runner(
            risk_seller_position=100,
            include_second_buyer=False,
        )
        runner.create_session(create_command())

        step = runner.step_session(
            SESSION_ID,
            ticks=1,
            command_id="cmd_step_forced_liq_no_position",
            trace_id=TRACE,
        )

        runtime = runner._sessions[SESSION_ID]
        published_event_ids = step["tick_result"]["published_event_ids"]
        self.assertFalse(any(event_id.startswith("forced_liq_") for event_id in published_event_ids))
        self.assertIsNotNone(runtime.last_order_submission)
        self.assertFalse(
            any(
                order.order_kind.value == "forced_liquidation"
                for order in runtime.last_order_submission.accepted_orders
            )
        )
        self.assertIsNotNone(runtime.last_trade_batch)
        self.assertEqual(len(runtime.last_trade_batch.trades), 1)
        snapshot = runtime.last_account_snapshots["risk_seller"]
        self.assertEqual(snapshot.positions, {})

        lifecycle_payload = lifecycle_payload_for(runner, "risk_seller")
        self.assertEqual(lifecycle_payload["lifecycle_state"], "liquidating")
        self.assertEqual(lifecycle_payload["decision"], "forced_liquidation")
        self.assertEqual(
            lifecycle_payload["forced_liquidation_order_status"],
            "skipped_no_sellable_position",
        )
        self.assertEqual(lifecycle_payload["forced_liquidation_quantity"], 0)


def session_runner(frontend_event_sink=None) -> SessionRunner:
    return SessionRunner(
        chronos_repository=chronos_repository(),
        agent_specs=agent_specs(),
        agent_runtime=AgentRuntime(scripted_actions=scripted_actions()),
        matching_config=MatchingConfig(lot_size=100),
        session_id_factory=lambda _command, _sequence: SESSION_ID,
        frontend_event_sink=frontend_event_sink,
    )



def market_only_session_runner() -> SessionRunner:
    return SessionRunner(
        chronos_repository=chronos_repository(),
        agent_specs=agent_specs(),
        agent_runtime=AgentRuntime(
            default_actions={
                "buyer": {"action_type": "hold"},
                "seller": {"action_type": "hold"},
            }
        ),
        matching_config=MatchingConfig(lot_size=100),
        session_id_factory=lambda _command, _sequence: SESSION_ID,
    )

def liquidation_session_runner(
    *,
    risk_seller_position: int,
    include_second_buyer: bool,
) -> SessionRunner:
    return SessionRunner(
        chronos_repository=liquidation_chronos_repository(),
        agent_specs=liquidation_agent_specs(
            risk_seller_position=risk_seller_position,
            include_second_buyer=include_second_buyer,
        ),
        agent_runtime=AgentRuntime(
            scripted_actions=liquidation_scripted_actions(
                include_second_buyer=include_second_buyer,
            )
        ),
        clearing_config=ClearingConfig(margin_call_drawdown_pct=50.0),
        matching_config=MatchingConfig(lot_size=100),
        session_id_factory=lambda _command, _sequence: SESSION_ID,
    )


def create_command(*, end_tick_id: str = NEXT_TICK) -> CreateSessionCommand:
    return CreateSessionCommand.from_dict(
        {
            "schema_version": SCHEMA_VERSION,
            "command_id": "cmd_create_runner",
            "scenario_id": "runner_scenario",
            "symbol": SYMBOL,
            "agent_profile_set": "runner_agents",
            "start_tick_id": TICK,
            "end_tick_id": end_tick_id,
            "tick_interval": "5m",
        }
    )


def lifecycle_payload_for(runner: SessionRunner, agent_id: str) -> dict[str, object]:
    events = runner.get_frontend_events(
        SESSION_ID,
        from_seq=0,
        limit=500,
        request_id=f"req_lifecycle_{agent_id}",
        trace_id=TRACE,
    )["events"]
    lifecycle_events = [
        event["payload"]
        for event in events
        if event["type"] == "runtime.agent_lifecycle"
        and event["payload"]["agent_id"] == agent_id
    ]
    if not lifecycle_events:
        raise AssertionError(f"missing lifecycle event for {agent_id}")
    return lifecycle_events[-1]


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


def liquidation_chronos_repository() -> InMemoryChronosRepository:
    return InMemoryChronosRepository.from_dicts(
        facts=[],
        initial_market_seeds={
            SYMBOL: {
                "schema_version": SCHEMA_VERSION,
                "seed_id": "seed_liquidation",
                "symbol": SYMBOL,
                "previous_close": 4.0,
                "limit_up": 20.0,
                "limit_down": 0.01,
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


def liquidation_agent_specs(
    *,
    risk_seller_position: int,
    include_second_buyer: bool,
) -> list[SessionAgentSpec]:
    specs = [
        SessionAgentSpec.from_dict(
            {
                "permission_profile": agent_profile("buyer_a"),
                "cash": 20_000.0,
                "positions": {},
                "mark_prices": {SYMBOL: 10.0},
            }
        ),
        SessionAgentSpec.from_dict(
            {
                "permission_profile": agent_profile("risk_seller"),
                "cash": 0.0,
                "positions": {SYMBOL: risk_seller_position},
                "mark_prices": {SYMBOL: 10.0},
            }
        ),
    ]
    if include_second_buyer:
        specs.append(
            SessionAgentSpec.from_dict(
                {
                    "permission_profile": agent_profile("buyer_b"),
                    "cash": 20_000.0,
                    "positions": {},
                    "mark_prices": {SYMBOL: 10.0},
                }
            )
        )
    return specs


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


def liquidation_scripted_actions(*, include_second_buyer: bool) -> dict[str, list[dict[str, object]]]:
    actions = {
        "buyer_a": [
            {
                "schema_version": SCHEMA_VERSION,
                "tick_id": TICK,
                "trace_id": TRACE,
                "agent_id": "buyer_a",
                "action": {
                    "action_type": "buy",
                    "symbol": SYMBOL,
                    "order_type": "limit",
                    "price": 4.0,
                    "quantity": 100,
                    "time_in_force": "day",
                },
            }
        ],
        "risk_seller": [
            {
                "schema_version": SCHEMA_VERSION,
                "tick_id": TICK,
                "trace_id": TRACE,
                "agent_id": "risk_seller",
                "action": {
                    "action_type": "sell",
                    "symbol": SYMBOL,
                    "order_type": "limit",
                    "price": 4.0,
                    "quantity": 100,
                    "time_in_force": "day",
                },
            }
        ],
    }
    if include_second_buyer:
        actions["buyer_b"] = [
            {
                "schema_version": SCHEMA_VERSION,
                "tick_id": TICK,
                "trace_id": TRACE,
                "agent_id": "buyer_b",
                "action": {
                    "action_type": "buy",
                    "symbol": SYMBOL,
                    "order_type": "limit",
                    "price": 4.0,
                    "quantity": 100,
                    "time_in_force": "day",
                },
            }
        ]
    return actions


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


class FailingGateway:
    def complete(self, _: object) -> dict[str, object]:
        raise SchemaValidationError("llm_provider_error")


if __name__ == "__main__":
    unittest.main()

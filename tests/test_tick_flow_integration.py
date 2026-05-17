from __future__ import annotations

import unittest
from typing import Any, Mapping

from Ouroboros.core.agents import AgentRuntime
from Ouroboros.core.chronos import Chronos, InMemoryChronosRepository, InMemoryOfficialNewsPublisher
from Ouroboros.core.clearing import ClearingConfig, ClearingHouse
from Ouroboros.core.market_data import MarketDataPublisher
from Ouroboros.core.matching import MatchingConfig, MatchingEngine
from Ouroboros.core.referee import UIAuditOfficer
from Ouroboros.core.routing import Channel, ChannelRouter, RoutingAccessError, SubscriberRef, SubscriberRole
from Ouroboros.core.schemas import (
    AgentPayload,
    CreateSessionCommand,
    CreateSessionResult,
    ErrorCode,
    ForumRumorEvent,
    InternalVisibility,
    OrderInputEvent,
    OrderRejectEvent,
    OrderActionType,
    RiskState,
    SCHEMA_VERSION,
    SchemaValidationError,
    SessionStatus,
    TickContext,
    TickState,
)
from Ouroboros.core.web_api.control_rest import ControlRestError
from Ouroboros.core.web_api.realtime_ws import FrontendRealtimeGateway


SESSION_ID = "sim_tick_flow_001"
SYMBOL = "demo_stock"
TICK = "2024-01-02T14:02:00+08:00"
NEXT_TICK = "2024-01-03T09:31:00+08:00"
TRACE = "trace_tick_flow"


def create_session() -> tuple[CreateSessionCommand, CreateSessionResult]:
    command = CreateSessionCommand.from_dict(
        {
            "schema_version": SCHEMA_VERSION,
            "command_id": "cmd_create_tick_flow",
            "scenario_id": "scenario_tick_flow",
            "symbol": SYMBOL,
            "agent_profile_set": "default_agents",
            "start_tick_id": TICK,
            "end_tick_id": NEXT_TICK,
            "tick_interval": "5m",
        }
    )
    result = CreateSessionResult.from_dict(
        {
            "schema_version": SCHEMA_VERSION,
            "command_id": command.command_id,
            "session_id": SESSION_ID,
            "status": "created",
            "current_tick_id": command.start_tick_id,
            "agent_count": 2,
        }
    )
    return command, result


def chronos() -> Chronos:
    repository = InMemoryChronosRepository.from_dicts(
        facts=[
            {
                "fact_id": "official_tick_flow_001",
                "event_id": "news_tick_flow_001",
                "symbol": SYMBOL,
                "fact_time": "2024-01-02T14:01:00+08:00",
                "source_type": "announcement",
                "source_name": "exchange",
                "title": "Tick flow visible fact",
                "summary": "Visible only after release_facts.",
                "confidence": "official",
                "permission_tags": ["retail"],
            },
            {
                "fact_id": "future_tick_flow_001",
                "event_id": "news_future_tick_flow_001",
                "symbol": SYMBOL,
                "fact_time": "2024-01-02T14:10:00+08:00",
                "source_type": "news",
                "source_name": "wire",
                "title": "Future fact",
                "summary": "Must not be visible in the current Tick.",
                "confidence": "official",
                "permission_tags": ["retail"],
            },
        ],
        initial_market_seeds={
            SYMBOL: {
                "schema_version": SCHEMA_VERSION,
                "seed_id": "seed_tick_flow",
                "symbol": SYMBOL,
                "previous_close": 10.0,
                "limit_up": 11.0,
                "limit_down": 9.0,
                "initial_l2_snapshot": {"bids": [], "asks": []},
            }
        },
    )
    return Chronos(repository=repository, publisher=InMemoryOfficialNewsPublisher())


def agent_profile(agent_id: str, *, can_post_forum: bool = True) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "agent_id": agent_id,
        "agent_type": "retail",
        "subscriptions": ["Market_Price", "Account_Snapshot:self", "Forum_Rumors"],
        "publish_permissions": {
            "order_action": True,
            "ui_audit": True,
            "forum_post": can_post_forum,
        },
        "official_news_scope": ["announcement", "news"],
    }


def open_accounts(house: ClearingHouse) -> None:
    house.open_account(agent_id="buyer", cash=20_000.0, mark_prices={SYMBOL: 10.0})
    house.open_account(
        agent_id="seller",
        cash=1_000.0,
        positions={SYMBOL: 1_000},
        mark_prices={SYMBOL: 10.0},
    )


def order_action(
    *,
    event_id: str,
    agent_id: str,
    side: str,
    quantity: int,
    price: float = 10.0,
    tick_id: str = TICK,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "tick_id": tick_id,
        "trace_id": TRACE,
        "producer": "meta_orchestrator",
        "visibility": "control_only",
        "agent_id": agent_id,
        "symbol": SYMBOL,
        "side": side,
        "order_type": "limit",
        "price": price,
        "quantity": quantity,
        "time_in_force": "day",
    }


def tick_context(
    *,
    agent_id: str,
    router: ChannelRouter,
    can_post_forum: bool = True,
) -> TickContext:
    inputs = router.build_agent_input_events(agent_id)
    return TickContext.from_dict(
        {
            "schema_version": SCHEMA_VERSION,
            "tick_id": TICK,
            "trace_id": TRACE,
            "agent_id": agent_id,
            "agent_role": "retail",
            "public_inputs": {
                "Market_Price": inputs.get("Market_Price", []),
                "Forum_Rumors": inputs.get("Forum_Rumors", []),
            },
            "private_inputs": {
                "Account_Snapshot": inputs.get("Account_Snapshot", []),
            },
            "constraints": {
                "allowed_actions": ["buy", "sell", "cancel", "hold", "post_forum"],
                "deadline_ms": 30000,
                "can_post_forum": can_post_forum,
            },
        }
    )


def split_agent_payload(
    payload: AgentPayload | Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Test-local contract shim for MetaOrchestrator.split_agent_payload."""

    parsed = payload if isinstance(payload, AgentPayload) else AgentPayload.from_dict(payload)
    order_inputs: list[dict[str, Any]] = []
    forum_rumors: list[dict[str, Any]] = []
    ui_audit: list[dict[str, Any]] = []

    action = parsed.action
    if action.action_type in {OrderActionType.BUY, OrderActionType.SELL}:
        order_inputs.append(
            OrderInputEvent.from_dict(
                {
                    "schema_version": SCHEMA_VERSION,
                    "event_id": f"order_{parsed.agent_id}_{parsed.tick_id.replace(':', '_')}",
                    "tick_id": parsed.tick_id,
                    "trace_id": parsed.trace_id,
                    "producer": "meta_orchestrator",
                    "visibility": "control_only",
                    "agent_id": parsed.agent_id,
                    "symbol": action.symbol,
                    "side": action.action_type.value,
                    "order_type": action.order_type.value if action.order_type else None,
                    "price": action.price,
                    "quantity": action.quantity,
                    "time_in_force": action.time_in_force.value if action.time_in_force else "day",
                    "client_order_id": action.client_order_id,
                }
            ).to_dict()
        )

    if parsed.forum_post is not None:
        forum_rumors.append(
            ForumRumorEvent.from_dict(
                {
                    "schema_version": SCHEMA_VERSION,
                    "event_id": f"forum_{parsed.forum_post.post_id}",
                    "tick_id": parsed.tick_id,
                    "trace_id": parsed.trace_id,
                    "producer": "meta_orchestrator",
                    "visibility": "public",
                    "post_id": parsed.forum_post.post_id,
                    "author_agent_id": parsed.forum_post.author_agent_id,
                    "author_type": "retail",
                    "text": parsed.forum_post.text,
                    "stance": parsed.forum_post.stance.value,
                    "created_tick_id": parsed.forum_post.tick_id,
                }
            ).to_dict()
        )

    ui_audit.append(
        {
            "schema_version": SCHEMA_VERSION,
            "event_id": f"ui_audit_{parsed.agent_id}_{parsed.tick_id.replace(':', '_')}",
            "tick_id": parsed.tick_id,
            "trace_id": parsed.trace_id,
            "producer": "meta_orchestrator",
            "visibility": "control_only",
            "agent_id": parsed.agent_id,
            "agent_type": "retail",
            "thought": parsed.thought or "hold/default decision",
            "belief_shift": 0.0,
            "belief_score": 0.5,
            "position_value": 0.0,
            "risk_state": "normal",
            "evidence_refs": list(parsed.evidence_refs),
            "public_reason": "公开输入触发决策审计。",
        }
    )

    public_text = repr({"orders": order_inputs, "forum": forum_rumors})
    if "thought" in public_text or (parsed.thought and parsed.thought in public_text):
        raise AssertionError("split_agent_payload leaked thought into public/order output")
    return {"order_inputs": order_inputs, "forum_rumors": forum_rumors, "ui_audit": ui_audit}


def timeout_default_hold(context: TickContext) -> AgentPayload:
    return AgentRuntime(default_actions={context.agent_id: {"action_type": "hold"}}).act(context)


def ws_event(seq: int, event_type: str, payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "seq": seq,
        "type": event_type,
        "session_id": SESSION_ID,
        "tick_id": TICK,
        "trace_id": TRACE,
        "server_time": "2024-01-02T14:02:01+08:00",
        "visibility": "public",
        "payload": dict(payload),
    }


class TickFlowIntegrationTests(unittest.TestCase):
    def test_minimal_tick_loop_commits_after_referee_publication(self) -> None:
        session_config, session_result = create_session()
        self.assertEqual(session_result.status, SessionStatus.CREATED)
        state_trace = [TickState.INIT_TICK]

        router = ChannelRouter(session_id=session_result.session_id)
        router.register_agent_permissions(agent_profile("buyer"))
        router.register_agent_permissions(agent_profile("seller"))
        house = ClearingHouse(ClearingConfig(commission_rate=0.001, stamp_tax_rate=0.001))
        open_accounts(house)
        engine = MatchingEngine(config=MatchingConfig(lot_size=100), order_ledger=house)
        market_data = MarketDataPublisher(router=router)
        layer0 = chronos()

        seed = layer0.build_initial_market_seed(session_config).to_dict()
        engine.initialize_market(seed)
        market_data.initialize_market(seed, tick_id=TICK, trace_id=TRACE)
        release_result = layer0.release_facts(
            {
                "schema_version": SCHEMA_VERSION,
                "command_id": "cmd_release_tick_flow",
                "tick_id": TICK,
                "trace_id": TRACE,
                "symbol": SYMBOL,
                "release_window": {
                    "from": "2024-01-02T14:00:00+08:00",
                    "to": TICK,
                },
            }
        )
        state_trace.append(TickState.RELEASE_FACTS)
        initial_market = market_data.publish_market_view(symbol=SYMBOL, tick_id=TICK, trace_id=TRACE)
        state_trace.append(TickState.PUBLISH_MARKET_VIEW)

        for agent_id in ("buyer", "seller"):
            router.publish(
                Channel.ACCOUNT_SNAPSHOT,
                house.account_snapshot(agent_id, tick_id=TICK, trace_id=TRACE),
                producer="clearing_house",
            )

        runtime = AgentRuntime(
            scripted_actions={
                "buyer": [
                    {
                        "schema_version": SCHEMA_VERSION,
                        "tick_id": TICK,
                        "trace_id": TRACE,
                        "agent_id": "buyer",
                        "thought": "private alpha must stay in UI audit",
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
                        "thought": "private sell rationale",
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
        )

        payloads = [
            runtime.act(tick_context(agent_id="buyer", router=router)),
            runtime.act(tick_context(agent_id="seller", router=router)),
        ]
        state_trace.append(TickState.AGENT_STEP)
        split_batches = [split_agent_payload(payload) for payload in payloads]
        order_inputs = [order for batch in split_batches for order in batch["order_inputs"]]
        ui_audit_events = [event for batch in split_batches for event in batch["ui_audit"]]
        state_trace.append(TickState.PAYLOAD_SPLIT)

        submit_result = engine.submit_orders(order_inputs, tick_id=TICK)
        self.assertEqual(submit_result.rejected_orders, [])
        trade_batch = engine.match_orders(TICK)
        settlement = house.settle_trade_batch(trade_batch)
        market_event = market_data.build_market_price(
            symbol=SYMBOL,
            tick_id=TICK,
            trade_batch=trade_batch,
            lob_view=engine.lob_view(SYMBOL),
        )
        state_trace.append(TickState.MATCH_AND_CLEAR)

        for snapshot in settlement.account_snapshots:
            router.publish(Channel.ACCOUNT_SNAPSHOT, snapshot, producer="clearing_house")
        audit_officer = UIAuditOfficer(router=router)
        audit_graph = audit_officer.publish_audit_graph(
            ui_audit_events,
            event_id="audit_graph_tick_flow",
            tick_id=TICK,
            trace_id=TRACE,
        )
        state_trace.append(TickState.REFEREE_PUBLICATION)
        house.commit_tick(TICK)
        state_trace.append(TickState.COMMIT_TICK)

        self.assertEqual(release_result.published_event_ids, ["news_tick_flow_001"])
        self.assertEqual(release_result.withheld_future_count, 1)
        self.assertEqual(initial_market.last_price, 10.0)
        self.assertEqual(len(trade_batch.trades), 1)
        self.assertEqual(market_event.last_price, 10.0)
        self.assertEqual(audit_graph.visibility, InternalVisibility.FRONTEND_ONLY)
        self.assertEqual(state_trace[-1], TickState.COMMIT_TICK)

    def test_visibility_contract_keeps_thought_private_and_routes_self_snapshots_only(self) -> None:
        _, session_result = create_session()
        router = ChannelRouter(session_id=session_result.session_id)
        router.register_agent_permissions(agent_profile("buyer"))
        router.register_agent_permissions(agent_profile("seller"))
        house = ClearingHouse()
        open_accounts(house)

        for agent_id in ("buyer", "seller"):
            router.publish(
                Channel.ACCOUNT_SNAPSHOT,
                house.account_snapshot(agent_id, tick_id=TICK, trace_id=TRACE),
                producer="clearing_house",
            )

        context = tick_context(agent_id="buyer", router=router)
        snapshots = context.private_inputs["Account_Snapshot"]
        self.assertEqual([item["agent_id"] for item in snapshots], ["buyer"])
        self.assertNotIn("seller", repr(context.to_dict()))

        payload = AgentRuntime(
            scripted_actions={
                "buyer": [
                    {
                        "schema_version": SCHEMA_VERSION,
                        "tick_id": TICK,
                        "trace_id": TRACE,
                        "agent_id": "buyer",
                        "thought": "private reasoning",
                        "action": {"action_type": "hold"},
                    }
                ]
            }
        ).act(context)
        split = split_agent_payload(payload)
        self.assertNotIn("thought", repr(split["order_inputs"]))
        self.assertNotIn("private reasoning", repr(split["forum_rumors"]))
        self.assertIn("private reasoning", repr(split["ui_audit"]))

        router.publish(
            Channel.UI_AUDIT,
            {
                key: split["ui_audit"][0][key]
                for key in (
                    "schema_version",
                    "event_id",
                    "tick_id",
                    "trace_id",
                    "producer",
                    "visibility",
                    "agent_id",
                    "thought",
                    "belief_shift",
                    "evidence_refs",
                )
            },
            producer="meta_orchestrator",
        )
        officer = SubscriberRef(
            subscriber_id="ui_audit_officer",
            role=SubscriberRole.UI_AUDIT_OFFICER,
        )
        self.assertEqual(
            router.replay_for_subscriber(Channel.UI_AUDIT, officer)[0]["thought"],
            "private reasoning",
        )
        agent = SubscriberRef(
            subscriber_id="buyer",
            role=SubscriberRole.AGENT_RUNTIME,
            agent_id="buyer",
        )
        with self.assertRaises(RoutingAccessError):
            router.replay_for_subscriber(Channel.UI_AUDIT, agent)

    def test_agent_failure_paths_default_hold_and_drop_unauthorized_forum_post(self) -> None:
        router = ChannelRouter(session_id=SESSION_ID)
        router.register_agent_permissions(agent_profile("buyer", can_post_forum=False))
        house = ClearingHouse()
        house.open_account(agent_id="buyer", cash=10_000.0, mark_prices={SYMBOL: 10.0})
        router.publish(
            Channel.ACCOUNT_SNAPSHOT,
            house.account_snapshot("buyer", tick_id=TICK, trace_id=TRACE),
            producer="clearing_house",
        )
        context = tick_context(agent_id="buyer", router=router, can_post_forum=False)

        self.assertEqual(timeout_default_hold(context).action.action_type, OrderActionType.HOLD)

        malformed_payload = AgentRuntime(scripted_actions={"buyer": ["{not-json"]}).act(context)
        self.assertEqual(malformed_payload.action.action_type, OrderActionType.HOLD)

        unauthorized = AgentRuntime(
            scripted_actions={
                "buyer": [
                    {
                        "schema_version": SCHEMA_VERSION,
                        "tick_id": TICK,
                        "trace_id": TRACE,
                        "agent_id": "buyer",
                        "action": {
                            "action_type": "buy",
                            "symbol": SYMBOL,
                            "order_type": "limit",
                            "price": 10.0,
                            "quantity": 100,
                            "time_in_force": "day",
                        },
                        "forum_post": {
                            "post_id": "forum_unauthorized",
                            "author_agent_id": "buyer",
                            "tick_id": TICK,
                            "text": "public but not permitted",
                            "stance": "bullish",
                            "visibility": "public",
                        },
                    }
                ]
            }
        ).act(context)
        split = split_agent_payload(unauthorized)
        self.assertEqual(unauthorized.action.action_type, OrderActionType.BUY)
        self.assertIsNone(unauthorized.forum_post)
        self.assertEqual(len(split["order_inputs"]), 1)
        self.assertEqual(split["forum_rumors"], [])

    def test_order_rejection_paths_cover_cash_t_plus_one_and_price_limits(self) -> None:
        house = ClearingHouse()
        house.open_account(agent_id="poor_buyer", cash=100.0, mark_prices={SYMBOL: 10.0})
        house.open_account(agent_id="buyer", cash=20_000.0, mark_prices={SYMBOL: 10.0})
        house.open_account(agent_id="seller", cash=1_000.0, positions={SYMBOL: 1_000}, mark_prices={SYMBOL: 10.0})
        engine = MatchingEngine(config=MatchingConfig(lot_size=100), order_ledger=house)
        seed = chronos().build_initial_market_seed(create_session()[0]).to_dict()
        engine.initialize_market(seed)

        initial = engine.submit_orders(
            [
                order_action(event_id="buy_for_t1", agent_id="buyer", side="buy", quantity=100),
                order_action(event_id="sell_to_t1", agent_id="seller", side="sell", quantity=100),
            ],
            tick_id=TICK,
        )
        self.assertEqual(initial.rejected_orders, [])
        house.settle_trade_batch(engine.match_orders(TICK))

        rejected = engine.submit_orders(
            [
                order_action(event_id="bad_cash", agent_id="poor_buyer", side="buy", quantity=100),
                order_action(event_id="bad_t1", agent_id="buyer", side="sell", quantity=100),
                order_action(event_id="bad_limit", agent_id="seller", side="sell", quantity=100, price=8.99),
            ],
            tick_id=TICK,
        )

        reasons = {event.order_event_id: event.reason_code for event in rejected.rejected_orders}
        self.assertEqual(reasons["bad_cash"], "insufficient_available_cash")
        self.assertEqual(reasons["bad_t1"], "t_plus_one_restricted")
        self.assertEqual(reasons["bad_limit"], "price_out_of_limit")
        for reject in rejected.rejected_orders:
            self.assertIsInstance(reject, OrderRejectEvent)
            self.assertFalse(reject.public)

    def test_forced_liquidation_enters_system_orders_with_priority(self) -> None:
        house = ClearingHouse(ClearingConfig(margin_call_drawdown_pct=50.0))
        house.open_account(agent_id="buyer_a", cash=20_000.0, mark_prices={SYMBOL: 10.0})
        house.open_account(agent_id="buyer_b", cash=20_000.0, mark_prices={SYMBOL: 10.0})
        house.open_account(agent_id="normal_seller", cash=1_000.0, positions={SYMBOL: 100}, mark_prices={SYMBOL: 10.0})
        house.open_account(agent_id="risk_seller", cash=0.0, positions={SYMBOL: 100}, mark_prices={SYMBOL: 10.0})
        house.settle_trade_batch(
            {
                "schema_version": SCHEMA_VERSION,
                "batch_id": "batch_mark_to_market",
                "tick_id": TICK,
                "trace_id": TRACE,
                "trades": [],
            },
            mark_prices={SYMBOL: 4.0},
        )
        risk = house.risk_result(
            "risk_seller",
            batch_id="batch_risk",
            tick_id=TICK,
            trace_id=TRACE,
        )
        self.assertEqual(risk.risk_state, RiskState.MARGIN_CALL)

        engine = MatchingEngine(config=MatchingConfig(lot_size=100), order_ledger=house)
        engine.initialize_market(chronos().build_initial_market_seed(create_session()[0]).to_dict())
        engine.submit_orders(
            [
                order_action(event_id="bid_a", agent_id="buyer_a", side="buy", quantity=100),
                order_action(event_id="bid_b", agent_id="buyer_b", side="buy", quantity=100),
            ],
            tick_id=TICK,
        )
        engine.match_orders(TICK)
        submit = engine.submit_orders(
            [
                order_action(event_id="normal_sell", agent_id="normal_seller", side="sell", quantity=100),
                {
                    **order_action(event_id="forced_sell", agent_id="risk_seller", side="sell", quantity=100),
                    "producer": "meta_orchestrator",
                    "order_type": "market",
                    "price": None,
                    "time_in_force": "ioc",
                    "order_kind": "forced_liquidation",
                    "reason_code": risk.reason_code,
                    "source_risk_state": risk.risk_state.value,
                },
            ],
            tick_id=TICK,
        )

        self.assertEqual(submit.rejected_orders, [])
        batch = engine.match_orders(TICK)
        self.assertEqual([trade.sell_order_id for trade in batch.trades], ["forced_sell", "normal_sell"])

    def test_frontend_disconnect_recovers_with_snapshot_and_from_seq(self) -> None:
        gateway = FrontendRealtimeGateway(replay_buffer_size=5)
        gateway.publish_event(SESSION_ID, ws_event(1, "market.price", {"symbol": SYMBOL, "last_price": 10.0}))
        gateway.publish_event(SESSION_ID, ws_event(2, "agent.account_snapshot", {"agent_id": "buyer", "cash": 10000}))
        gateway.connect(SESSION_ID, "client_a")
        gateway.handle_client_message(
            SESSION_ID,
            "client_a",
            {"type": "subscribe", "request_id": "req_sub_1", "topics": ["market", "agent"]},
        )
        gateway.disconnect(SESSION_ID, "client_a")

        snapshot = {"last_seq": 2, "market": {"symbol": SYMBOL, "last_price": 10.0}}
        gateway.publish_event(SESSION_ID, ws_event(3, "market.price", {"symbol": SYMBOL, "last_price": 10.1}))
        gateway.publish_event(SESSION_ID, ws_event(4, "runtime.tick_state", {"tick_state": "COMMIT_TICK"}))
        gateway.connect(SESSION_ID, "client_a", from_seq=snapshot["last_seq"])
        messages = gateway.handle_client_message(
            SESSION_ID,
            "client_a",
            {"type": "subscribe", "request_id": "req_sub_2", "topics": ["market", "runtime"]},
        )
        replayed = [message.body for message in messages if message.kind == "event"]
        self.assertEqual([event["seq"] for event in replayed], [3, 4])

        expired = FrontendRealtimeGateway(replay_buffer_size=1)
        expired.publish_event(SESSION_ID, ws_event(1, "market.price", {"symbol": SYMBOL, "last_price": 10.0}))
        expired.publish_event(SESSION_ID, ws_event(2, "market.price", {"symbol": SYMBOL, "last_price": 10.1}))
        with self.assertRaises(ControlRestError) as caught:
            expired.connect(SESSION_ID, "client_b", from_seq=0)
        self.assertEqual(caught.exception.code, ErrorCode.SNAPSHOT_REQUIRED)


if __name__ == "__main__":
    unittest.main()

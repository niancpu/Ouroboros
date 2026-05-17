from __future__ import annotations

import unittest

from Ouroboros.core.referee import (
    ExchangeBroadcaster,
    UIAuditOfficer,
    build_end_of_day,
    build_tape_alerts,
)
from Ouroboros.core.routing import Channel, ChannelRouter, RoutingAccessError, SubscriberRef, SubscriberRole
from Ouroboros.core.schemas import AuditGraphEvent, CausalChainEvent, SchemaValidationError, TapeAlertEvent


TICK = "2024-01-02T14:02:00+08:00"
TRACE = "trace_abc"


def market_output(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "schema_version": "v1",
        "event_id": "mkt_001",
        "tick_id": TICK,
        "trace_id": TRACE,
        "producer": "market_data_publisher",
        "visibility": "public",
        "symbol": "demo_stock",
        "last_price": 9.6,
        "previous_price": 10.0,
        "volume": 100000,
        "turnover": 960000.0,
        "limit_up": 11.0,
        "limit_down": 9.0,
        "limit_state": "normal",
        "level2": {"bids": [["9.5", 100]], "asks": [["9.7", 100]]},
        "active_sell_volume": 90000,
        "avg_sell_volume_5": 20000,
        "active_buy_volume": 10000,
        "avg_buy_volume_5": 9000,
    }
    data.update(overrides)
    return data


def dragon_tiger() -> dict[str, list[dict[str, object]]]:
    return {
        "buy_rank": [
            {
                "seat_name": "retail_cluster_a",
                "seat_type": "retail_cluster",
                "buy_amount": 5000000.0,
                "sell_amount": 1000000.0,
                "net_amount": 4000000.0,
            }
        ],
        "sell_rank": [
            {
                "seat_name": "institution_seat_a",
                "seat_type": "institution",
                "buy_amount": 1000000.0,
                "sell_amount": 3000000.0,
                "net_amount": -2000000.0,
            }
        ],
    }


def ui_audit() -> dict[str, object]:
    return {
        "schema_version": "v1",
        "event_id": "ui_audit_001",
        "tick_id": TICK,
        "trace_id": TRACE,
        "producer": "meta_orchestrator",
        "visibility": "control_only",
        "agent_id": "retail_b",
        "agent_type": "retail",
        "thought": "private alpha: sell before close",
        "belief_shift": 0.34,
        "belief_score": 0.42,
        "position_value": 152000.0,
        "risk_state": "normal",
        "evidence_refs": ["forum_post_123"],
        "public_reason": "公开股吧帖子影响散户信念。",
    }


def agent_profile(agent_id: str) -> dict[str, object]:
    return {
        "schema_version": "v1",
        "agent_id": agent_id,
        "agent_type": "retail",
        "subscriptions": ["Market_Price", "Tape_Alerts", "End_of_Day"],
        "publish_permissions": {
            "order_action": True,
            "ui_audit": True,
            "forum_post": True,
        },
        "official_news_scope": ["announcement", "news"],
    }


class RefereePublicationTests(unittest.TestCase):
    def test_tape_alerts_use_anonymous_market_output_without_private_leakage(self) -> None:
        with self.assertRaises(SchemaValidationError):
            build_tape_alerts(
                market_output(
                    thought="private alpha: sell before close",
                )
            )

        with self.assertRaises(SchemaValidationError):
            build_tape_alerts(market_output(agent_id="retail_b"))

        clean_alerts = build_tape_alerts(market_output())
        self.assertTrue(clean_alerts)
        self.assertIsInstance(clean_alerts[0], TapeAlertEvent)
        text = repr([event.to_dict() for event in clean_alerts])
        self.assertNotIn("agent_id", text)
        self.assertNotIn("thought", text)
        self.assertNotIn("private alpha", text)

    def test_end_of_day_requires_post_close_phase(self) -> None:
        with self.assertRaises(SchemaValidationError):
            build_end_of_day(
                market_output(close_price=9.6, dragon_tiger=dragon_tiger()),
                market_phase="continuous",
            )

        event = build_end_of_day(
            market_output(close_price=9.6, dragon_tiger=dragon_tiger()),
            market_phase="closed",
        )
        data = event.to_dict()
        self.assertEqual(data["producer"], "exchange_broadcaster")
        self.assertEqual(data["visibility"], "public")
        self.assertEqual(data["dragon_tiger"]["buy_rank"][0]["seat_name"], "retail_cluster_a")

    def test_frontend_only_events_cannot_enter_agent_subscription(self) -> None:
        router = ChannelRouter(session_id="sim_001")
        router.register_agent_permissions(agent_profile("retail_b"))
        officer = UIAuditOfficer(router=router)

        graph = officer.publish_audit_graph(
            [ui_audit()],
            event_id="audit_graph_001",
            tick_id=TICK,
            trace_id=TRACE,
        )
        chain = officer.publish_causal_chain(
            event_id="chain_001",
            tick_id=TICK,
            trace_id=TRACE,
            chain_id="chain_001",
            title="公开帖子影响散户信念",
            summary="公开事件与成交结果形成前端审计链路。",
            steps=[
                {
                    "step_id": "step_001",
                    "step_type": "public_message",
                    "tick_id": TICK,
                    "actor_id": "public_event",
                    "event_ref": "forum_post_123",
                    "public_text": "公开帖子被散户群体看到。",
                },
                {
                    "step_id": "step_002",
                    "step_type": "belief_shift",
                    "tick_id": TICK,
                    "actor_id": "retail_cluster",
                    "event_ref": "audit_graph_001",
                    "public_text": "散户群体信念发生变化。",
                },
            ],
            metrics={"confidence": 0.76},
        )

        self.assertIsInstance(graph, AuditGraphEvent)
        self.assertIsInstance(chain, CausalChainEvent)
        agent = SubscriberRef(
            subscriber_id="retail_b",
            role=SubscriberRole.AGENT_RUNTIME,
            agent_id="retail_b",
        )
        with self.assertRaises(RoutingAccessError):
            router.replay_for_subscriber(Channel.FRONTEND_AUDIT_GRAPH, agent)
        with self.assertRaises(RoutingAccessError):
            router.replay_for_subscriber(Channel.FRONTEND_CAUSAL_CHAIN, agent)
        self.assertEqual(
            router.build_agent_input_events("retail_b"),
            {"End_of_Day": [], "Market_Price": [], "Tape_Alerts": []},
        )

    def test_audit_graph_accepts_structured_belief_shift_without_private_leakage(self) -> None:
        officer = UIAuditOfficer()
        raw = {
            **ui_audit(),
            "belief_shift": {
                "confidence_delta": 0.3,
                "sentiment": "bullish",
                "risk_appetite_delta": 0.2,
            },
        }

        graph = officer.build_audit_graph(
            [raw],
            event_id="audit_graph_001",
            tick_id=TICK,
            trace_id=TRACE,
        )
        data = graph.to_dict()

        self.assertEqual(data["nodes"][0]["agent_id"], "retail_b")
        self.assertEqual(data["edges"][0]["source"], "public_event")
        self.assertEqual(data["edges"][0]["target"], "retail_b")
        self.assertGreater(data["edges"][0]["weight"], 0.3)
        rendered = repr(data)
        self.assertNotIn("thought", rendered)
        self.assertNotIn("private alpha", rendered)

    def test_exchange_broadcaster_publishes_only_agent_subscribable_public_channels(self) -> None:
        router = ChannelRouter(session_id="sim_001")
        router.register_agent_permissions(agent_profile("retail_b"))
        broadcaster = ExchangeBroadcaster(router=router)

        alerts = broadcaster.publish_tape_alerts(market_output())
        eod = broadcaster.publish_end_of_day(
            market_output(close_price=9.6),
            market_phase="closed",
            dragon_tiger=dragon_tiger(),
        )

        inputs = router.build_agent_input_events("retail_b")
        self.assertEqual(inputs["Tape_Alerts"], [event.to_dict() for event in alerts])
        self.assertEqual(inputs["End_of_Day"], [eod.to_dict()])

    def test_invalid_inputs_raise_errors(self) -> None:
        with self.assertRaises(SchemaValidationError):
            build_tape_alerts(market_output(active_sell_volume=-1))

        officer = UIAuditOfficer()
        with self.assertRaises(SchemaValidationError):
            officer.build_causal_chain(
                event_id="chain_001",
                tick_id=TICK,
                trace_id=TRACE,
                chain_id="chain_001",
                title="invalid",
                summary="invalid",
                steps=[
                    {
                        "step_id": "step_001",
                        "step_type": "belief_shift",
                        "tick_id": TICK,
                        "actor_id": "retail_b",
                        "event_ref": "ui_audit_001",
                        "public_text": "invalid",
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from Ouroboros.core.market_data import MarketDataConfig, MarketDataPublisher
from Ouroboros.core.matching import MatchingEngine
from Ouroboros.core.routing import Channel, ChannelRouter, SubscriberRef, SubscriberRole
from Ouroboros.core.schemas import MarketPriceEvent, SchemaValidationError


TICK = "2024-01-02T14:02:00+08:00"
TRACE = "trace_abc"


def seed() -> dict[str, object]:
    return {
        "schema_version": "v1",
        "seed_id": "seed_001",
        "symbol": "demo_stock",
        "previous_close": 10.0,
        "limit_up": 11.0,
        "limit_down": 9.0,
        "initial_l2_snapshot": {
            "bids": [["9.9", 100], ["9.8", 200]],
            "asks": [["10.1", 300], ["10.2", 400]],
        },
    }


def order(
    *,
    event_id: str,
    agent_id: str,
    side: str,
    quantity: int,
    price: float,
) -> dict[str, object]:
    return {
        "schema_version": "v1",
        "event_id": event_id,
        "tick_id": TICK,
        "trace_id": TRACE,
        "producer": "meta_orchestrator",
        "visibility": "control_only",
        "agent_id": agent_id,
        "symbol": "demo_stock",
        "side": side,
        "order_type": "limit",
        "price": price,
        "quantity": quantity,
        "time_in_force": "day",
        "client_order_id": f"client_{event_id}",
    }


def trade_batch(price: float = 10.1, quantity: int = 100) -> dict[str, object]:
    return {
        "schema_version": "v1",
        "batch_id": "batch_001",
        "tick_id": TICK,
        "trace_id": TRACE,
        "trades": [
            {
                "schema_version": "v1",
                "event_id": "trade_001",
                "tick_id": TICK,
                "trace_id": TRACE,
                "symbol": "demo_stock",
                "price": price,
                "quantity": quantity,
                "buy_order_id": "buy_001",
                "sell_order_id": "sell_001",
            }
        ],
    }


def agent_profile(agent_id: str) -> dict[str, object]:
    return {
        "schema_version": "v1",
        "agent_id": agent_id,
        "agent_type": "hot_money",
        "subscriptions": ["Market_Price"],
        "publish_permissions": {
            "order_action": True,
            "ui_audit": True,
            "forum_post": True,
        },
        "official_news_scope": ["announcement", "news", "regulatory_notice"],
    }


class MarketDataPublisherTests(unittest.TestCase):
    def test_initial_market_seed_generates_first_public_snapshot(self) -> None:
        publisher = MarketDataPublisher()

        event = publisher.initialize_market(seed(), tick_id=TICK, trace_id=TRACE)

        self.assertIsInstance(event, MarketPriceEvent)
        data = event.to_dict()
        self.assertEqual(data["producer"], "market_data_publisher")
        self.assertEqual(data["visibility"], "public")
        self.assertEqual(data["last_price"], 10.0)
        self.assertEqual(data["volume"], 0)
        self.assertEqual(data["turnover"], 0.0)
        self.assertEqual(data["limit_state"], "normal")
        self.assertEqual(data["level2"]["bids"], [["9.9", 100], ["9.8", 200]])

    def test_trade_batch_updates_last_price_volume_and_turnover(self) -> None:
        publisher = MarketDataPublisher()
        publisher.initialize_market(seed(), tick_id=TICK, trace_id=TRACE)

        event = publisher.build_market_price(
            symbol="demo_stock",
            tick_id=TICK,
            trade_batch=trade_batch(price=10.1, quantity=100),
        )
        second = publisher.build_market_price(
            symbol="demo_stock",
            tick_id=TICK,
            trade_batch=trade_batch(price=10.2, quantity=50),
        )

        self.assertEqual(event.last_price, 10.1)
        self.assertEqual(event.volume, 100)
        self.assertEqual(event.turnover, 1010.0)
        self.assertEqual(second.last_price, 10.2)
        self.assertEqual(second.volume, 150)
        self.assertEqual(second.turnover, 1520.0)

    def test_level2_depth_is_aggregated_sorted_and_clipped(self) -> None:
        publisher = MarketDataPublisher(config=MarketDataConfig(default_depth=2))
        publisher.initialize_market(
            {
                **seed(),
                "initial_l2_snapshot": {
                    "bids": [["9.7", 100], ["9.9", 100], ["9.9", 50], ["9.8", 200]],
                    "asks": [["10.3", 100], ["10.1", 100], ["10.1", 50], ["10.2", 200]],
                },
            },
            tick_id=TICK,
            trace_id=TRACE,
        )

        event = publisher.build_market_price(symbol="demo_stock", tick_id=TICK)

        self.assertEqual(event.to_dict()["level2"]["bids"], [["9.9", 150], ["9.8", 200]])
        self.assertEqual(event.to_dict()["level2"]["asks"], [["10.1", 150], ["10.2", 200]])

    def test_can_consume_matching_engine_lob_view_without_private_fields(self) -> None:
        engine = MatchingEngine()
        engine.initialize_market({**seed(), "initial_l2_snapshot": {"bids": [], "asks": []}})
        engine.submit_orders(
            [
                order(event_id="bid_1", agent_id="buyer_a", side="buy", quantity=100, price=9.9),
                order(event_id="bid_2", agent_id="buyer_b", side="buy", quantity=200, price=9.9),
                order(event_id="ask_1", agent_id="seller_a", side="sell", quantity=300, price=10.2),
            ]
        )
        engine.match_orders(TICK)
        publisher = MarketDataPublisher()
        publisher.initialize_market(seed(), tick_id=TICK, trace_id=TRACE)

        event = publisher.build_market_price(
            symbol="demo_stock",
            tick_id=TICK,
            lob_view=engine.lob_view("demo_stock"),
        )

        data = event.to_dict()
        self.assertEqual(data["level2"]["bids"], [["9.9", 300]])
        self.assertEqual(data["level2"]["asks"], [["10.2", 300]])
        self.assertNotIn("agent_id", repr(data))
        self.assertNotIn("client_order_id", repr(data))

    def test_limit_state_tracks_limit_up_down_and_halted(self) -> None:
        publisher = MarketDataPublisher()
        publisher.initialize_market(seed(), tick_id=TICK, trace_id=TRACE)

        up = publisher.build_market_price(
            symbol="demo_stock",
            tick_id=TICK,
            trade_batch=trade_batch(price=11.0, quantity=100),
        )
        down = publisher.build_market_price(
            symbol="demo_stock",
            tick_id=TICK,
            trade_batch=trade_batch(price=9.0, quantity=100),
        )
        publisher.set_halted("demo_stock")
        halted = publisher.build_market_price(symbol="demo_stock", tick_id=TICK)

        self.assertEqual(up.limit_state.value, "limit_up")
        self.assertEqual(down.limit_state.value, "limit_down")
        self.assertEqual(halted.limit_state.value, "halted")

    def test_publish_market_view_routes_to_channel_router(self) -> None:
        router = ChannelRouter(session_id="sim_001")
        router.register_agent_permissions(agent_profile("agent_a"))
        subscriber = SubscriberRef(
            subscriber_id="agent_a",
            role=SubscriberRole.AGENT_RUNTIME,
            agent_id="agent_a",
        )
        publisher = MarketDataPublisher(router=router)
        publisher.initialize_market(seed(), tick_id=TICK, trace_id=TRACE)

        event = publisher.publish_market_view(
            symbol="demo_stock",
            tick_id=TICK,
            trace_id=TRACE,
            trade_batch=trade_batch(price=10.1, quantity=100),
        )

        replayed = router.replay_for_subscriber(Channel.MARKET_PRICE, subscriber)
        self.assertEqual(replayed, [event.to_dict()])
        self.assertEqual(replayed[0]["producer"], "market_data_publisher")

    def test_forbidden_fields_never_appear_in_public_output(self) -> None:
        publisher = MarketDataPublisher()
        publisher.initialize_market(seed(), tick_id=TICK, trace_id=TRACE)

        event = publisher.build_market_price(
            symbol="demo_stock",
            tick_id=TICK,
            trade_batch=trade_batch(),
        )

        data_text = repr(event.to_dict())
        for field_name in (
            "buy_order_id",
            "sell_order_id",
            "order_id",
            "client_order_id",
            "agent_id",
            "thought",
            "reason",
        ):
            self.assertNotIn(field_name, data_text)

    def test_publish_without_router_is_explicit_error(self) -> None:
        publisher = MarketDataPublisher()
        publisher.initialize_market(seed(), tick_id=TICK, trace_id=TRACE)

        with self.assertRaises(SchemaValidationError):
            publisher.publish_market_view(symbol="demo_stock", tick_id=TICK)


if __name__ == "__main__":
    unittest.main()

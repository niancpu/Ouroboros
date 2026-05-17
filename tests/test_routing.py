from __future__ import annotations

import unittest

from Ouroboros.core.routing import (
    Channel,
    ChannelRouter,
    RedisBus,
    RoutingAccessError,
    SubscriberRef,
    SubscriberRole,
)
from Ouroboros.core.schemas import SchemaValidationError


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def agent_profile(
    agent_id: str,
    *,
    subscriptions: list[str],
    agent_type: str = "hot_money",
    official_news_scope: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "v1",
        "agent_id": agent_id,
        "agent_type": agent_type,
        "subscriptions": subscriptions,
        "publish_permissions": {
            "order_action": True,
            "ui_audit": True,
            "forum_post": True,
        },
        "official_news_scope": (
            ["announcement", "news", "regulatory_notice"]
            if official_news_scope is None
            else official_news_scope
        ),
    }


def market_price(event_id: str = "mkt_001") -> dict[str, object]:
    return {
        "schema_version": "v1",
        "event_id": event_id,
        "tick_id": "2024-01-02T14:02:00+08:00",
        "trace_id": "trace_abc",
        "producer": "market_data_publisher",
        "visibility": "public",
        "symbol": "demo_stock",
        "last_price": 15.2,
        "volume": 100000,
        "turnover": 1520000.0,
        "limit_up": 16.5,
        "limit_down": 13.5,
        "limit_state": "normal",
        "level2": {"bids": [["15.19", 12000]], "asks": [["15.21", 8000]]},
    }


def ui_audit(thought: str = "private audit text") -> dict[str, object]:
    return {
        "schema_version": "v1",
        "event_id": "audit_001",
        "tick_id": "2024-01-02T14:02:00+08:00",
        "trace_id": "trace_abc",
        "producer": "meta_orchestrator",
        "visibility": "control_only",
        "agent_id": "hot_money_a",
        "thought": thought,
        "belief_shift": 0.34,
        "evidence_refs": ["forum_post_123"],
    }


def account_snapshot(agent_id: str, event_id: str) -> dict[str, object]:
    return {
        "schema_version": "v1",
        "event_id": event_id,
        "tick_id": "2024-01-02T14:02:00+08:00",
        "trace_id": "trace_abc",
        "producer": "clearing_house",
        "visibility": "agent_private",
        "agent_id": agent_id,
        "cash": 1200000.0,
        "available_cash": 1200000.0,
        "positions": {"demo_stock": 300000},
        "available_shares": {"demo_stock": 0},
        "frozen_shares": {"demo_stock": 300000},
        "market_value": 4560000.0,
        "equity": 5760000.0,
        "risk_state": "normal",
        "source": "layer3_global_ledger",
    }


def official_news(
    event_id: str,
    *,
    source_type: str = "announcement",
    permission_tags: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "v1",
        "event_id": event_id,
        "tick_id": "2024-01-02T14:02:00+08:00",
        "trace_id": "trace_abc",
        "producer": "chronos",
        "visibility": "public",
        "created_at": "2024-01-02T14:02:00+08:00",
        "symbol": "demo_stock",
        "fact_time": "2024-01-02T14:00:00+08:00",
        "source_type": source_type,
        "source_name": "exchange",
        "fact_id": f"fact_{event_id}",
        "title": f"Official fact {event_id}",
        "summary": "Released official summary.",
        "confidence": "official",
        "permission_tags": ["hot_money"] if permission_tags is None else permission_tags,
    }


class RoutingTests(unittest.TestCase):
    def test_channel_names_are_session_scoped(self) -> None:
        shared_bus = RedisBus()
        session_a = ChannelRouter(session_id="sim_a", bus=shared_bus)
        session_b = ChannelRouter(session_id="sim_b", bus=shared_bus)
        session_a.register_agent_permissions(
            agent_profile("hot_money_a", subscriptions=["Market_Price"])
        )
        subscriber = SubscriberRef(
            subscriber_id="hot_money_a",
            role=SubscriberRole.AGENT_RUNTIME,
            agent_id="hot_money_a",
        )

        session_a.publish(Channel.MARKET_PRICE, market_price())

        self.assertEqual(
            session_a.namespaced_channel(Channel.MARKET_PRICE),
            "sim_a:Market_Price",
        )
        self.assertEqual(session_a.replay_for_subscriber(Channel.MARKET_PRICE, subscriber)[0]["event_id"], "mkt_001")
        session_b.register_agent_permissions(
            agent_profile("hot_money_a", subscriptions=["Market_Price"])
        )
        self.assertEqual(session_b.replay_for_subscriber(Channel.MARKET_PRICE, subscriber), [])

    def test_publish_subscribe_respects_channel_allowlists(self) -> None:
        router = ChannelRouter(session_id="sim_001")
        router.register_agent_permissions(
            agent_profile("hot_money_a", subscriptions=["Market_Price"])
        )
        received: list[dict[str, object]] = []
        agent = SubscriberRef(
            subscriber_id="hot_money_a",
            role=SubscriberRole.AGENT_RUNTIME,
            agent_id="hot_money_a",
        )

        router.subscribe(Channel.MARKET_PRICE, agent, received.append)
        router.publish(Channel.MARKET_PRICE, market_price())

        self.assertEqual([item["event_id"] for item in received], ["mkt_001"])
        with self.assertRaises(RoutingAccessError):
            router.subscribe(Channel.UI_AUDIT, agent, received.append)
        with self.assertRaises(RoutingAccessError):
            router.publish(
                Channel.MARKET_PRICE,
                {**market_price("mkt_bad"), "producer": "meta_orchestrator"},
            )

    def test_ttl_expiry_and_explicit_eviction_remove_buffered_events(self) -> None:
        clock = FakeClock()
        router = ChannelRouter(
            session_id="sim_001",
            bus=RedisBus(default_ttl_seconds=10, clock=clock),
        )
        router.register_agent_permissions(
            agent_profile("hot_money_a", subscriptions=["Market_Price"])
        )
        agent = SubscriberRef(
            subscriber_id="hot_money_a",
            role=SubscriberRole.AGENT_RUNTIME,
            agent_id="hot_money_a",
        )

        router.publish(Channel.MARKET_PRICE, market_price(), ttl_seconds=5)
        self.assertEqual(len(router.replay_for_subscriber(Channel.MARKET_PRICE, agent)), 1)
        clock.advance(5)
        self.assertEqual(router.evict_expired(), 1)
        self.assertEqual(router.replay_for_subscriber(Channel.MARKET_PRICE, agent), [])

        router.publish(Channel.MARKET_PRICE, market_price("mkt_002"))
        self.assertEqual(router.evict_channel(Channel.MARKET_PRICE), 1)
        self.assertEqual(router.replay_for_subscriber(Channel.MARKET_PRICE, agent), [])

    def test_private_fields_are_rejected_from_agent_subscribable_channels(self) -> None:
        router = ChannelRouter(session_id="sim_001")

        with self.assertRaises(SchemaValidationError):
            router.publish(
                Channel.MARKET_PRICE,
                {**market_price(), "thought": "must not leak"},
            )

    def test_ui_audit_thought_never_enters_agent_legal_inputs(self) -> None:
        router = ChannelRouter(session_id="sim_001")
        router.register_agent_permissions(
            agent_profile(
                "hot_money_a",
                subscriptions=[
                    "Official_News",
                    "Market_Price",
                    "Account_Snapshot:self",
                    "Tape_Alerts",
                    "End_of_Day",
                    "Forum_Rumors",
                ],
            )
        )

        router.publish(Channel.UI_AUDIT, ui_audit("secret thought"))
        inputs = router.build_agent_input_events("hot_money_a")

        self.assertNotIn("UI_Audit", inputs)
        self.assertNotIn("secret thought", repr(inputs))

    def test_account_snapshot_is_only_visible_to_owning_agent(self) -> None:
        router = ChannelRouter(session_id="sim_001")
        router.register_agent_permissions(
            agent_profile("agent_a", subscriptions=["Account_Snapshot:self"])
        )
        router.register_agent_permissions(
            agent_profile("agent_b", subscriptions=["Account_Snapshot:self"])
        )
        agent_a = SubscriberRef(
            subscriber_id="agent_a",
            role=SubscriberRole.AGENT_RUNTIME,
            agent_id="agent_a",
        )
        agent_b = SubscriberRef(
            subscriber_id="agent_b",
            role=SubscriberRole.AGENT_RUNTIME,
            agent_id="agent_b",
        )

        router.publish(Channel.ACCOUNT_SNAPSHOT, account_snapshot("agent_a", "acct_a"))
        router.publish(Channel.ACCOUNT_SNAPSHOT, account_snapshot("agent_b", "acct_b"))

        self.assertEqual(
            [item["event_id"] for item in router.replay_for_subscriber(Channel.ACCOUNT_SNAPSHOT, agent_a)],
            ["acct_a"],
        )
        self.assertEqual(
            [item["event_id"] for item in router.replay_for_subscriber(Channel.ACCOUNT_SNAPSHOT, agent_b)],
            ["acct_b"],
        )

    def test_official_news_scope_filters_source_types_per_agent(self) -> None:
        router = ChannelRouter(session_id="sim_001")
        router.register_agent_permissions(
            agent_profile(
                "narrow",
                subscriptions=["Official_News"],
                official_news_scope=["announcement"],
            )
        )
        router.register_agent_permissions(
            agent_profile(
                "wide",
                subscriptions=["Official_News"],
                official_news_scope=["announcement", "news"],
            )
        )

        router.publish(Channel.OFFICIAL_NEWS, official_news("news_announcement"))
        router.publish(Channel.OFFICIAL_NEWS, official_news("news_wire", source_type="news"))

        narrow_inputs = router.build_agent_input_events("narrow")["Official_News"]
        wide_inputs = router.build_agent_input_events("wide")["Official_News"]

        self.assertEqual([item["event_id"] for item in narrow_inputs], ["news_announcement"])
        self.assertEqual(
            [item["event_id"] for item in wide_inputs],
            ["news_announcement", "news_wire"],
        )

    def test_official_news_permission_tags_filter_by_agent_type(self) -> None:
        router = ChannelRouter(session_id="sim_001")
        router.register_agent_permissions(
            agent_profile(
                "retail_a",
                subscriptions=["Official_News"],
                agent_type="retail",
                official_news_scope=["announcement", "news"],
            )
        )
        router.register_agent_permissions(
            agent_profile(
                "hot_money_a",
                subscriptions=["Official_News"],
                agent_type="hot_money",
                official_news_scope=["announcement", "news"],
            )
        )

        router.publish(
            Channel.OFFICIAL_NEWS,
            official_news("news_hot_money_only", permission_tags=["hot_money"]),
        )
        router.publish(
            Channel.OFFICIAL_NEWS,
            official_news("news_retail_only", permission_tags=["retail"]),
        )

        self.assertEqual(
            [
                item["event_id"]
                for item in router.build_agent_input_events("retail_a")["Official_News"]
            ],
            ["news_retail_only"],
        )
        self.assertEqual(
            [
                item["event_id"]
                for item in router.build_agent_input_events("hot_money_a")["Official_News"]
            ],
            ["news_hot_money_only"],
        )

    def test_empty_official_news_scope_blocks_official_news(self) -> None:
        router = ChannelRouter(session_id="sim_001")
        router.register_agent_permissions(
            agent_profile(
                "hot_money_a",
                subscriptions=["Official_News"],
                official_news_scope=[],
            )
        )
        subscriber = SubscriberRef(
            subscriber_id="hot_money_a",
            role=SubscriberRole.AGENT_RUNTIME,
            agent_id="hot_money_a",
        )

        router.publish(Channel.OFFICIAL_NEWS, official_news("news_hidden"))

        self.assertEqual(router.build_agent_input_events("hot_money_a")["Official_News"], [])
        self.assertEqual(router.replay_for_subscriber(Channel.OFFICIAL_NEWS, subscriber), [])


if __name__ == "__main__":
    unittest.main()

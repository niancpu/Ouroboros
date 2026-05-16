from __future__ import annotations

import unittest

from Ouroboros.core.chronos import (
    Chronos,
    InMemoryChronosRepository,
    InMemoryOfficialNewsPublisher,
)
from Ouroboros.core.schemas import InternalVisibility, SchemaValidationError


def build_chronos() -> tuple[Chronos, InMemoryOfficialNewsPublisher]:
    publisher = InMemoryOfficialNewsPublisher()
    repository = InMemoryChronosRepository.from_dicts(
        facts=[
            {
                "fact_id": "official_001",
                "event_id": "news_001",
                "symbol": "demo_stock",
                "fact_time": "2024-01-02T14:00:00+08:00",
                "source_type": "announcement",
                "source_name": "exchange",
                "title": "Public announcement",
                "summary": "Visible public summary.",
                "confidence": "official",
                "permission_tags": ["institutional", "hot_money"],
            },
            {
                "fact_id": "future_001",
                "event_id": "news_future_001",
                "symbol": "demo_stock",
                "fact_time": "2024-01-02T14:10:00+08:00",
                "source_type": "news",
                "source_name": "wire",
                "title": "Future market moving news",
                "summary": "This must not leak before 14:10.",
                "confidence": "official",
                "permission_tags": ["institutional"],
            },
        ],
        initial_market_seeds={
            "demo_stock": {
                "schema_version": "v1",
                "seed_id": "seed_001",
                "symbol": "demo_stock",
                "previous_close": 15.0,
                "limit_up": 16.5,
                "limit_down": 13.5,
                "initial_l2_snapshot": {
                    "bids": [["14.99", 10000]],
                    "asks": [["15.01", 8000]],
                },
            }
        },
    )
    return Chronos(repository=repository, publisher=publisher), publisher


class ChronosTests(unittest.TestCase):
    def test_release_facts_publishes_only_current_window_official_news(self) -> None:
        chronos, publisher = build_chronos()

        result = chronos.release_facts(
            {
                "schema_version": "v1",
                "command_id": "cmd_release_001",
                "tick_id": "2024-01-02T14:02:00+08:00",
                "trace_id": "trace_abc",
                "symbol": "demo_stock",
                "release_window": {
                    "from": "2024-01-02T13:57:00+08:00",
                    "to": "2024-01-02T14:02:00+08:00",
                },
            }
        )

        self.assertEqual(result.published_event_ids, ["news_001"])
        self.assertEqual(result.withheld_future_count, 1)
        self.assertEqual(len(publisher.published_events), 1)
        event = publisher.published_events[0]
        self.assertEqual(event.visibility, InternalVisibility.PUBLIC)
        self.assertEqual(event.producer, "chronos")
        self.assertNotIn("withheld_future_count", event.to_dict())

    def test_release_facts_rejects_window_later_than_tick(self) -> None:
        chronos, _publisher = build_chronos()

        with self.assertRaises(SchemaValidationError):
            chronos.release_facts(
                {
                    "schema_version": "v1",
                    "command_id": "cmd_release_001",
                    "tick_id": "2024-01-02T14:02:00+08:00",
                    "trace_id": "trace_abc",
                    "symbol": "demo_stock",
                    "release_window": {
                        "from": "2024-01-02T13:57:00+08:00",
                        "to": "2024-01-02T14:03:00+08:00",
                    },
                }
            )

    def test_search_visible_events_is_cut_off_by_tick(self) -> None:
        chronos, _publisher = build_chronos()

        results = chronos.search_visible_events(
            tick_id="2024-01-02T14:02:00+08:00",
            query="news",
            symbol="demo_stock",
        )

        self.assertEqual([item.fact_id for item in results], [])

        results = chronos.search_visible_events(
            tick_id="2024-01-02T14:12:00+08:00",
            query="news",
            symbol="demo_stock",
        )
        self.assertEqual([item.fact_id for item in results], ["future_001"])
        self.assertEqual(
            set(results[0].to_dict().keys()),
            {"fact_id", "summary", "source_type", "fact_time"},
        )

    def test_build_initial_market_seed_returns_seed_without_broadcasting(self) -> None:
        chronos, publisher = build_chronos()

        seed = chronos.build_initial_market_seed(
            {
                "schema_version": "v1",
                "command_id": "cmd_create_001",
                "scenario_id": "scenario_001",
                "symbol": "demo_stock",
                "agent_profile_set": "default_agents",
                "start_tick_id": "2024-01-02T09:30:00+08:00",
                "end_tick_id": "2024-01-02T15:00:00+08:00",
                "tick_interval": "5m",
            }
        )

        self.assertEqual(seed.seed_id, "seed_001")
        self.assertEqual(seed.initial_l2_snapshot.bids, [("14.99", 10000)])
        self.assertEqual(publisher.published_events, [])


if __name__ == "__main__":
    unittest.main()

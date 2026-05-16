from __future__ import annotations

import unittest

from Ouroboros.core.schemas import (
    CommonEventHeader,
    InternalVisibility,
    MarketPriceEvent,
    OrderInputEvent,
    SchemaValidationError,
    WebVisibility,
    WebEventEnvelope,
    map_internal_visibility_to_web,
)


class CoreSchemaTests(unittest.TestCase):
    def test_common_event_header_accepts_required_fields(self) -> None:
        header = CommonEventHeader.from_dict(
            {
                "schema_version": "v1",
                "event_id": "evt_001",
                "tick_id": "2024-01-02T14:02:00+08:00",
                "trace_id": "trace_abc",
                "visibility": "public",
            }
        )

        self.assertEqual(header.visibility, InternalVisibility.PUBLIC)
        self.assertEqual(header.to_dict()["schema_version"], "v1")

    def test_internal_visibility_maps_to_web_visibility(self) -> None:
        self.assertEqual(
            map_internal_visibility_to_web(InternalVisibility.PUBLIC),
            WebVisibility.PUBLIC,
        )
        self.assertEqual(
            map_internal_visibility_to_web("agent_private"),
            WebVisibility.AGENT_PRIVATE_SNAPSHOT,
        )

    def test_order_input_accepts_valid_limit_order(self) -> None:
        event = OrderInputEvent.from_dict(
            {
                "schema_version": "v1",
                "event_id": "order_001",
                "tick_id": "2024-01-02T14:02:00+08:00",
                "trace_id": "trace_abc",
                "producer": "meta_orchestrator",
                "visibility": "control_only",
                "agent_id": "mutual_fund_a",
                "symbol": "demo_stock",
                "side": "sell",
                "order_type": "limit",
                "price": 15.2,
                "quantity": 500000,
                "time_in_force": "day",
                "client_order_id": "agent_order_001",
            }
        )

        self.assertEqual(event.to_dict()["visibility"], "control_only")
        self.assertEqual(event.to_dict()["side"], "sell")

    def test_order_input_rejects_private_reasoning_fields(self) -> None:
        with self.assertRaises(SchemaValidationError):
            OrderInputEvent.from_dict(
                {
                    "schema_version": "v1",
                    "event_id": "order_001",
                    "tick_id": "2024-01-02T14:02:00+08:00",
                    "trace_id": "trace_abc",
                    "producer": "meta_orchestrator",
                    "visibility": "control_only",
                    "agent_id": "retail_b",
                    "symbol": "demo_stock",
                    "side": "buy",
                    "order_type": "market",
                    "quantity": 1000,
                    "thought": "private audit text",
                }
            )

    def test_market_price_accepts_public_level2_snapshot(self) -> None:
        event = MarketPriceEvent.from_dict(
            {
                "schema_version": "v1",
                "event_id": "mkt_001",
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
                "level2": {
                    "bids": [["15.19", 12000]],
                    "asks": [["15.21", 8000]],
                },
            }
        )

        self.assertEqual(event.to_dict()["level2"]["bids"], [["15.19", 12000]])

    def test_web_event_rejects_internal_or_private_fields(self) -> None:
        with self.assertRaises(SchemaValidationError):
            WebEventEnvelope.from_dict(
                {
                    "schema_version": "v1",
                    "seq": 1024,
                    "type": "market.price",
                    "session_id": "sim_001",
                    "tick_id": "2024-01-02T14:02:00+08:00",
                    "trace_id": "trace_abc",
                    "server_time": "2024-01-02T14:02:01+08:00",
                    "visibility": "public",
                    "payload": {
                        "symbol": "demo_stock",
                        "last_price": 15.2,
                        "thought": "leaked private text",
                    },
                }
            )


if __name__ == "__main__":
    unittest.main()

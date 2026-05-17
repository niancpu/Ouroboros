from __future__ import annotations

import json
import unittest

from Ouroboros.core.schemas import ErrorCode, RestErrorResponse, WebEventEnvelope
from Ouroboros.core.web_api.realtime_ws import FrontendRealtimeGateway


class FrontendRealtimeGatewayTests(unittest.TestCase):
    def test_subscribe_receives_only_matching_topic_events(self) -> None:
        gateway = FrontendRealtimeGateway()
        gateway.connect("sim_001", "client_a")

        messages = gateway.handle_client_message(
            "sim_001",
            "client_a",
            {"type": "subscribe", "request_id": "req_sub", "topics": ["market"]},
        )
        self.assertEqual(messages[0].kind, "subscribed")

        outbound = gateway.publish_event("sim_001", _event(seq=1, event_type="market.price"))

        self.assertEqual(list(outbound), ["client_a"])
        body = outbound["client_a"][0].body
        parsed = WebEventEnvelope.from_dict(body)
        self.assertEqual(parsed.type, "market.price")

    def test_ack_updates_connection_state(self) -> None:
        gateway = FrontendRealtimeGateway()
        gateway.connect("sim_001", "client_a")

        messages = gateway.handle_client_message(
            "sim_001",
            "client_a",
            {"type": "ack", "request_id": "req_ack", "last_seq": 7},
        )

        self.assertEqual(messages[0].kind, "ack")
        self.assertEqual(messages[0].body["data"]["last_seq"], 7)
        self.assertEqual(gateway.connection_state("sim_001", "client_a").last_ack_seq, 7)

    def test_ping_returns_pong_without_business_write(self) -> None:
        gateway = FrontendRealtimeGateway()
        gateway.connect("sim_001", "client_a")

        messages = gateway.handle_client_message(
            "sim_001",
            "client_a",
            {
                "type": "ping",
                "request_id": "req_ping",
                "client_time": "2024-01-02T14:02:01+08:00",
            },
        )

        self.assertEqual(messages[0].kind, "pong")
        self.assertEqual(messages[0].body["request_id"], "req_ping")

    def test_from_seq_replays_buffer_after_subscribe(self) -> None:
        gateway = FrontendRealtimeGateway()
        gateway.publish_event("sim_001", _event(seq=1, event_type="market.price"))
        gateway.publish_event("sim_001", _event(seq=2, event_type="market.tape_alert"))
        gateway.publish_event("sim_001", _event(seq=3, event_type="runtime.tick_state"))
        gateway.connect("sim_001", "client_a", from_seq=1)

        messages = gateway.handle_client_message(
            "sim_001",
            "client_a",
            {"type": "subscribe", "request_id": "req_sub", "topics": ["market"]},
        )

        replay_events = [message.body for message in messages if message.kind == "event"]
        self.assertEqual([event["seq"] for event in replay_events], [2])

    def test_expired_replay_buffer_returns_snapshot_required_error(self) -> None:
        gateway = FrontendRealtimeGateway(replay_buffer_size=2)
        gateway.publish_event("sim_001", _event(seq=1, event_type="market.price"))
        gateway.publish_event("sim_001", _event(seq=2, event_type="market.price"))
        gateway.publish_event("sim_001", _event(seq=3, event_type="market.price"))

        with self.assertRaises(Exception) as caught:
            gateway.connect("sim_001", "client_a", from_seq=0)

        self.assertEqual(getattr(caught.exception, "code"), ErrorCode.SNAPSHOT_REQUIRED)

    def test_illegal_topic_and_event_are_rejected(self) -> None:
        gateway = FrontendRealtimeGateway()
        gateway.connect("sim_001", "client_a")

        messages = gateway.handle_client_message(
            "sim_001",
            "client_a",
            {"type": "subscribe", "request_id": "req_sub", "topics": ["UI_Audit"]},
        )
        self.assertEqual(messages[0].kind, "error")
        parsed = RestErrorResponse.from_dict(_rest_error_shape(messages[0].body))
        self.assertEqual(parsed.error.code, ErrorCode.BAD_REQUEST)

        with self.assertRaises(Exception):
            gateway.publish_event("sim_001", _event(seq=1, event_type="UI_Audit"))

    def test_sensitive_fields_are_filtered_before_publish(self) -> None:
        gateway = FrontendRealtimeGateway()
        gateway.connect("sim_001", "client_a")
        gateway.handle_client_message(
            "sim_001",
            "client_a",
            {"type": "subscribe", "request_id": "req_sub", "topics": ["audit"]},
        )

        outbound = gateway.publish_event(
            "sim_001",
            _event(
                seq=1,
                event_type="audit.causal_chain",
                visibility="frontend_only",
                payload={
                    "summary": "public sanitized summary",
                    "thought": "must-not-leak",
                    "thought_summary": "must-not-leak",
                    "UI_Audit": {"thought": "must-not-leak"},
                    "raw_agent_payload": {"prompt": "must-not-leak"},
                    "steps": [{"public_text": "safe", "private_memory": "must-not-leak"}],
                },
            ),
        )

        body = outbound["client_a"][0].body
        WebEventEnvelope.from_dict(body)
        rendered = json.dumps(body, ensure_ascii=False, sort_keys=True)
        for fragment in [
            "thought",
            "thought_summary",
            "UI_Audit",
            "raw_agent_payload",
            "private_memory",
            "prompt",
            "must-not-leak",
        ]:
            self.assertNotIn(fragment, rendered)
        self.assertIn("public sanitized summary", rendered)


def _event(
    *,
    seq: int,
    event_type: str,
    visibility: str = "public",
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "v1",
        "seq": seq,
        "type": event_type,
        "session_id": "sim_001",
        "tick_id": "2024-01-02T14:02:00+08:00",
        "trace_id": "trace_abc",
        "server_time": "2024-01-02T14:02:01+08:00",
        "visibility": visibility,
        "payload": payload or {"symbol": "demo_stock", "last_price": 15.2},
    }


def _rest_error_shape(body: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": body["schema_version"],
        "request_id": body["request_id"],
        "trace_id": "trace_ws",
        "server_time": body["server_time"],
        "error": body["error"],
    }


if __name__ == "__main__":
    unittest.main()

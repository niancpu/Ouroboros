from __future__ import annotations

import json
import unittest

from Ouroboros.core.llm import LLMGateway
from Ouroboros.core.schemas import LLMRequest, SchemaValidationError


def llm_request(
    agent_id: str = "agent_a",
    *,
    request_id: str = "llm_req_001",
    content: str = "Only use this agent context.",
) -> dict[str, object]:
    return {
        "schema_version": "v1",
        "request_id": request_id,
        "agent_id": agent_id,
        "tick_id": "2024-01-02T14:02:00+08:00",
        "prompt_profile_id": "retail_default",
        "messages": [{"role": "user", "content": content}],
        "output_schema_ref": "agent_payload.v1",
        "deadline_ms": 30000,
    }


class MutableClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class LLMGatewayTests(unittest.TestCase):
    def test_complete_returns_schema_shaped_mock_output(self) -> None:
        gateway = LLMGateway()

        output = gateway.complete(LLMRequest.from_dict(llm_request()))

        self.assertEqual(output["schema_version"], "v1")
        self.assertEqual(output["agent_id"], "agent_a")
        candidate = output["candidates"][0]
        content = json.loads(candidate["content"])
        self.assertEqual(content["action"]["action_type"], "hold")
        self.assertEqual(content["agent_id"], "agent_a")

    def test_rate_limit_is_deterministic_and_resets_by_window(self) -> None:
        clock = MutableClock()
        gateway = LLMGateway(max_requests=2, window_seconds=10.0, clock=clock)

        gateway.complete(llm_request(request_id="llm_req_001"))
        gateway.complete(llm_request(request_id="llm_req_002"))
        with self.assertRaisesRegex(SchemaValidationError, "rate_limited"):
            gateway.complete(llm_request(request_id="llm_req_003"))

        clock.now += 10.0
        output = gateway.complete(llm_request(request_id="llm_req_004"))
        self.assertEqual(output["request_id"], "llm_req_004")

    def test_precheck_accepts_json_string_and_does_not_apply_permissions(self) -> None:
        gateway = LLMGateway()
        raw_output = json.dumps(
            {
                "schema_version": "v1",
                "request_id": "llm_req_001",
                "agent_id": "agent_a",
                "tick_id": "2024-01-02T14:02:00+08:00",
                "provider": "deterministic_mock",
                "output_schema_ref": "agent_payload.v1",
                "candidates": [
                    {
                        "content": json.dumps(
                            {
                                "schema_version": "v1",
                                "agent_id": "agent_a",
                                "tick_id": "2024-01-02T14:02:00+08:00",
                                "action": {"action_type": "post_forum"},
                            }
                        ),
                        "finish_reason": "stop",
                    }
                ],
            }
        )

        output = gateway.precheck_structured_output(raw_output)

        candidate_content = json.loads(output["candidates"][0]["content"])
        self.assertEqual(candidate_content["action"]["action_type"], "post_forum")

    def test_precheck_rejects_illegal_top_level_and_candidate_fields(self) -> None:
        gateway = LLMGateway()
        output = gateway.complete(llm_request())

        with self.assertRaisesRegex(SchemaValidationError, "unknown field"):
            gateway.precheck_structured_output({**output, "other_agent_context": {}})

        bad_candidate = dict(output)
        bad_candidate["candidates"] = [
            {**output["candidates"][0], "permission_granted": True}
        ]
        with self.assertRaisesRegex(SchemaValidationError, "unknown field"):
            gateway.precheck_structured_output(bad_candidate)

    def test_complete_does_not_swallow_or_merge_other_agent_context(self) -> None:
        gateway = LLMGateway()
        request = llm_request(
            "agent_a",
            content=(
                "agent_a private context. other_agent_context="
                "{'agent_id': 'agent_b', 'secret': 'must_not_be_merged'}"
            ),
        )

        output = gateway.complete(request)

        self.assertEqual(output["agent_id"], "agent_a")
        self.assertNotIn("agent_b", json.dumps(output, sort_keys=True))
        self.assertNotIn("must_not_be_merged", json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    unittest.main()

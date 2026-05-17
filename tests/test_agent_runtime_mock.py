from __future__ import annotations

import unittest
import json

from Ouroboros.core.agents import AgentRuntime
from Ouroboros.core.agents.runtime import PromptProfileConfigurationError
from Ouroboros.core.schemas import (
    AgentPayload,
    MemoryReadRequest,
    MemoryWriteRequest,
    OrderActionType,
    SchemaValidationError,
    TickContext,
)


PROMPT_PROFILES = {
    "prompt_retail_v1": {
        "schema_version": "v1",
        "prompt_profile_id": "prompt_retail_v1",
        "agent_type": "retail",
        "system_role": "Retail agent role.",
        "behavior_rules": ["Use public retail-visible inputs."],
        "risk_rules": ["Keep position risk bounded."],
        "output_schema_ref": "agent_payload.v1",
        "forbidden_claims": ["I can read hidden channels."],
    },
    "prompt_hot_money_v1": {
        "schema_version": "v1",
        "prompt_profile_id": "prompt_hot_money_v1",
        "agent_type": "hot_money",
        "system_role": "Hot money agent role.",
        "behavior_rules": ["Use visible momentum and forum signals."],
        "risk_rules": ["Do not claim private market access."],
        "output_schema_ref": "agent_payload.v1",
        "forbidden_claims": ["I can expand allowed actions."],
    },
}

AGENT_PROFILES = {
    "agent_a": {
        "agent_id": "agent_a",
        "agent_type": "retail",
        "display_name": "Agent A",
        "seat_alias": None,
        "strategy_bias": {"style": "mixed"},
        "risk_profile": {"risk_appetite": "medium"},
        "prompt_profile_ref": "prompt_retail_v1",
        "memory_namespace": "mem_agent_a",
        "permission_profile_ref": "perm_retail_default",
        "initial_asset_plan_ref": "asset_agent_a",
    },
    "agent_b": {
        "agent_id": "agent_b",
        "agent_type": "hot_money",
        "display_name": "Agent B",
        "seat_alias": None,
        "strategy_bias": {"style": "momentum"},
        "risk_profile": {"risk_appetite": "high"},
        "prompt_profile_ref": "prompt_hot_money_v1",
        "memory_namespace": "mem_agent_b",
        "permission_profile_ref": "perm_hot_money_default",
        "initial_asset_plan_ref": "asset_agent_b",
    },
}


def tick_context(
    agent_id: str = "agent_a",
    *,
    tick_id: str = "2024-01-02T14:02:00+08:00",
    agent_role: str = "retail",
    can_post_forum: bool = False,
    allowed_actions: list[str] | None = None,
) -> TickContext:
    return TickContext.from_dict(
        {
            "schema_version": "v1",
            "tick_id": tick_id,
            "trace_id": "trace_abc",
            "agent_id": agent_id,
            "agent_role": agent_role,
            "public_inputs": {
                "market_price": {"symbol": "demo_stock", "last_price": 15.2},
                "UI_Audit": {"thought": "must not leak"},
            },
            "private_inputs": {
                "account_snapshot": {"agent_id": agent_id, "cash": 10000},
                "other_agent_snapshot": {"agent_id": "agent_b", "cash": 999999},
                "memory_refs": [{"summary": "private input stays input only"}],
            },
            "constraints": {
                "allowed_actions": allowed_actions
                or ["buy", "sell", "cancel", "hold", "post_forum"],
                "deadline_ms": 30000,
                "can_post_forum": can_post_forum,
            },
        }
    )


class AgentRuntimeMockTests(unittest.TestCase):
    def test_default_action_is_safe_hold_payload(self) -> None:
        runtime = AgentRuntime(default_actions={"agent_a": {"action_type": "hold"}})

        payload = runtime.act(tick_context("agent_a"))

        self.assertEqual(payload.action.action_type, OrderActionType.HOLD)
        self.assertEqual(payload.agent_id, "agent_a")
        self.assertEqual(payload.tick_id, "2024-01-02T14:02:00+08:00")
        AgentPayload.from_dict(payload.to_dict())

    def test_scripted_buy_and_sell_payloads_are_schema_valid(self) -> None:
        runtime = AgentRuntime(
            scripted_actions={
                "agent_a": [
                    {
                        "action_type": "buy",
                        "symbol": "demo_stock",
                        "order_type": "limit",
                        "price": 15.2,
                        "quantity": 100,
                        "time_in_force": "day",
                    },
                    {
                        "action_type": "sell",
                        "symbol": "demo_stock",
                        "order_type": "market",
                        "quantity": 50,
                    },
                ]
            }
        )

        buy = runtime.act(tick_context("agent_a"))
        sell = runtime.act(tick_context("agent_a"))

        self.assertEqual(buy.action.action_type, OrderActionType.BUY)
        self.assertEqual(sell.action.action_type, OrderActionType.SELL)
        AgentPayload.from_dict(buy.to_dict())
        AgentPayload.from_dict(sell.to_dict())

    def test_exhausted_scripted_agent_falls_back_to_safe_hold(self) -> None:
        runtime = AgentRuntime(
            scripted_actions={
                "agent_a": [
                    {
                        "action_type": "buy",
                        "symbol": "demo_stock",
                        "order_type": "limit",
                        "price": 15.2,
                        "quantity": 100,
                        "time_in_force": "day",
                    }
                ]
            }
        )

        first = runtime.act(tick_context("agent_a"))
        second = runtime.act(
            tick_context("agent_a", tick_id="2024-01-02T14:07:00+08:00")
        )

        self.assertEqual(first.action.action_type, OrderActionType.BUY)
        self.assertEqual(second.action.action_type, OrderActionType.HOLD)
        self.assertEqual(second.tick_id, "2024-01-02T14:07:00+08:00")

    def test_payload_template_default_fills_runtime_identity(self) -> None:
        runtime = AgentRuntime(
            default_actions={
                "agent_a": {
                    "action": {"action_type": "hold"},
                    "belief_shift": {
                        "confidence_delta": 0.2,
                        "sentiment": "neutral",
                        "risk_appetite_delta": 0.0,
                    },
                    "evidence_refs": ["forum_post_123"],
                }
            }
        )

        payload = runtime.act(tick_context("agent_a"))

        self.assertEqual(payload.agent_id, "agent_a")
        self.assertEqual(payload.tick_id, "2024-01-02T14:02:00+08:00")
        self.assertEqual(payload.trace_id, "trace_abc")
        self.assertIsNotNone(payload.belief_shift)
        self.assertEqual(payload.evidence_refs, ["forum_post_123"])

    def test_scripted_payload_identity_mismatch_becomes_safe_hold(self) -> None:
        runtime = AgentRuntime(
            scripted_actions={
                "agent_a": [
                    {
                        "schema_version": "v1",
                        "tick_id": "wrong_tick",
                        "trace_id": "trace_abc",
                        "agent_id": "agent_a",
                        "action": {
                            "action_type": "buy",
                            "symbol": "demo_stock",
                            "order_type": "market",
                            "quantity": 1,
                        },
                    },
                    {
                        "schema_version": "v1",
                        "tick_id": "2024-01-02T14:02:00+08:00",
                        "trace_id": "trace_abc",
                        "agent_id": "agent_b",
                        "action": {
                            "action_type": "sell",
                            "symbol": "demo_stock",
                            "order_type": "market",
                            "quantity": 1,
                        },
                    },
                ]
            }
        )

        wrong_tick = runtime.act(tick_context("agent_a"))
        wrong_agent = runtime.act(tick_context("agent_a"))

        self.assertEqual(wrong_tick.action.action_type, OrderActionType.HOLD)
        self.assertEqual(wrong_agent.action.action_type, OrderActionType.HOLD)

    def test_unauthorized_forum_post_is_dropped_but_legal_action_remains(self) -> None:
        runtime = AgentRuntime(
            scripted_actions={
                "agent_a": [
                    {
                        "schema_version": "v1",
                        "tick_id": "2024-01-02T14:02:00+08:00",
                        "trace_id": "trace_abc",
                        "agent_id": "agent_a",
                        "action": {
                            "action_type": "buy",
                            "symbol": "demo_stock",
                            "order_type": "market",
                            "quantity": 10,
                        },
                        "forum_post": {
                            "post_id": "forum_post_001",
                            "author_agent_id": "agent_a",
                            "tick_id": "2024-01-02T14:02:00+08:00",
                            "text": "public view",
                            "stance": "bullish",
                            "visibility": "public",
                        },
                    }
                ]
            }
        )

        payload = runtime.act(tick_context("agent_a", can_post_forum=False))

        self.assertEqual(payload.action.action_type, OrderActionType.BUY)
        self.assertIsNone(payload.forum_post)

    def test_unauthorized_post_forum_action_becomes_safe_hold(self) -> None:
        runtime = AgentRuntime(
            scripted_actions={
                "agent_a": [
                    {
                        "action_type": "post_forum",
                    }
                ]
            }
        )

        payload = runtime.act(tick_context("agent_a", can_post_forum=False))

        self.assertEqual(payload.action.action_type, OrderActionType.HOLD)

    def test_authorized_forum_post_is_kept(self) -> None:
        runtime = AgentRuntime(
            scripted_actions={
                "agent_a": [
                    {
                        "schema_version": "v1",
                        "tick_id": "2024-01-02T14:02:00+08:00",
                        "trace_id": "trace_abc",
                        "agent_id": "agent_a",
                        "action": {"action_type": "post_forum"},
                        "forum_post": {
                            "post_id": "forum_post_001",
                            "author_agent_id": "agent_a",
                            "tick_id": "2024-01-02T14:02:00+08:00",
                            "text": "public view",
                            "stance": "bullish",
                            "visibility": "public",
                        },
                    }
                ]
            }
        )

        payload = runtime.act(tick_context("agent_a", can_post_forum=True))

        self.assertEqual(payload.action.action_type, OrderActionType.POST_FORUM)
        self.assertIsNotNone(payload.forum_post)

    def test_memory_namespace_isolation(self) -> None:
        runtime = AgentRuntime(memory_namespaces={"agent_a": "mem_a", "agent_b": "mem_b"})
        runtime.memory_write(
            MemoryWriteRequest(
                schema_version="v1",
                agent_id="agent_a",
                memory_namespace="mem_a",
                tick_id="tick_1",
                memory_type="decision_trace",
                summary="agent a private memory",
                source_refs=["forum_post_001"],
            )
        )

        agent_a_read = runtime.memory_read(
            MemoryReadRequest(
                schema_version="v1",
                agent_id="agent_a",
                memory_namespace="mem_a",
                tick_id="tick_2",
                query="private",
                limit=5,
            )
        )

        self.assertEqual(len(agent_a_read.memory_refs), 1)
        self.assertEqual(agent_a_read.memory_refs[0].summary, "agent a private memory")
        with self.assertRaises(SchemaValidationError):
            runtime.memory_read(
                MemoryReadRequest(
                    schema_version="v1",
                    agent_id="agent_b",
                    memory_namespace="mem_a",
                    tick_id="tick_2",
                    query="private",
                    limit=5,
                )
            )

    def test_output_does_not_include_ui_audit_or_other_agent_private_fields(self) -> None:
        runtime = AgentRuntime(default_actions={"agent_a": {"action_type": "hold"}})

        payload = runtime.act(tick_context("agent_a"))
        payload_data = payload.to_dict()

        self.assertNotIn("UI_Audit", repr(payload_data))
        self.assertNotIn("must not leak", repr(payload_data))
        self.assertNotIn("other_agent_snapshot", repr(payload_data))
        self.assertNotIn("agent_b", repr(payload_data))

    def test_memory_update_writes_only_current_agent_private_memory(self) -> None:
        runtime = AgentRuntime(memory_namespaces={"agent_a": "mem_a", "agent_b": "mem_b"})
        runtime_with_update = AgentRuntime(
            memory_namespaces={"agent_a": "mem_a", "agent_b": "mem_b"},
            scripted_actions={
                "agent_a": [
                    {
                        "schema_version": "v1",
                        "tick_id": "2024-01-02T14:02:00+08:00",
                        "trace_id": "trace_abc",
                        "agent_id": "agent_a",
                        "action": {"action_type": "hold"},
                        "evidence_refs": ["forum_post_001"],
                        "memory_update": {
                            "should_write": True,
                            "summary": "agent a decision trace",
                        },
                    }
                ]
            },
        )

        runtime_with_update.act(tick_context("agent_a"))
        own_memory = runtime_with_update.memory_read(
            {
                "schema_version": "v1",
                "agent_id": "agent_a",
                "memory_namespace": "mem_a",
                "tick_id": "tick_2",
                "query": "decision",
                "limit": 5,
            }
        )

        self.assertEqual(own_memory.memory_refs[0].summary, "agent a decision trace")
        with self.assertRaises(SchemaValidationError):
            runtime.memory_read(
                {
                    "schema_version": "v1",
                    "agent_id": "agent_b",
                    "memory_namespace": "mem_a",
                    "tick_id": "tick_2",
                    "query": "decision",
                    "limit": 5,
                }
            )

    def test_llm_malformed_json_records_payload_parse_error_and_holds(self) -> None:
        runtime = AgentRuntime(
            llm_gateway=MalformedGateway(),
            allow_prompt_profile_fallback=True,
        )

        payload = runtime.act(tick_context("agent_a"))

        self.assertEqual(payload.action.action_type, OrderActionType.HOLD)
        self.assertEqual(runtime.last_errors["agent_a"], "payload_parse_error")

    def test_llm_provider_error_raises_when_strict_llm_mode_is_enabled(self) -> None:
        runtime = AgentRuntime(
            llm_gateway=FailingGateway(),
            allow_prompt_profile_fallback=True,
            raise_llm_errors=True,
        )

        with self.assertRaisesRegex(SchemaValidationError, "llm_provider_error"):
            runtime.act(tick_context("agent_a"))
        self.assertEqual(runtime.last_errors["agent_a"], "llm_provider_error")

    def test_llm_json_payload_is_parsed_into_agent_payload(self) -> None:
        runtime = AgentRuntime(
            llm_gateway=PayloadGateway(),
            allow_prompt_profile_fallback=True,
        )

        payload = runtime.act(tick_context("agent_a"))

        self.assertEqual(payload.action.action_type, OrderActionType.BUY)
        self.assertEqual(payload.action.quantity, 100)

    def test_llm_request_uses_agent_specific_prompt_profile(self) -> None:
        runtime = AgentRuntime(
            agent_profiles=AGENT_PROFILES,
            prompt_profiles=PROMPT_PROFILES,
        )

        retail_request = runtime._llm_request(tick_context("agent_a", agent_role="retail"))
        hot_money_request = runtime._llm_request(
            tick_context("agent_b", agent_role="hot_money")
        )

        self.assertEqual(retail_request["prompt_profile_id"], "prompt_retail_v1")
        self.assertEqual(hot_money_request["prompt_profile_id"], "prompt_hot_money_v1")
        retail_developer = json.loads(retail_request["messages"][1]["content"])
        hot_money_developer = json.loads(hot_money_request["messages"][1]["content"])
        self.assertEqual(
            retail_developer["prompt_profile"]["system_role"],
            "Retail agent role.",
        )
        self.assertEqual(
            hot_money_developer["prompt_profile"]["system_role"],
            "Hot money agent role.",
        )

    def test_prompt_profile_does_not_expand_permissions_or_channels(self) -> None:
        runtime = AgentRuntime(
            agent_profiles=AGENT_PROFILES,
            prompt_profiles=PROMPT_PROFILES,
        )
        context = tick_context(
            "agent_b",
            agent_role="hot_money",
            can_post_forum=False,
            allowed_actions=["hold"],
        )

        request = runtime._llm_request(context)
        developer_payload = json.loads(request["messages"][1]["content"])
        serialized_prompt = json.dumps(developer_payload, sort_keys=True)

        self.assertEqual(
            developer_payload["permission_boundary"]["allowed_actions"],
            ["hold"],
        )
        self.assertFalse(developer_payload["permission_boundary"]["can_post_forum"])
        self.assertNotIn("subscriptions", serialized_prompt)
        self.assertNotIn("input_channels", serialized_prompt)
        self.assertNotIn("Official_News", serialized_prompt)

    def test_missing_prompt_profile_fails_fast_in_llm_mode(self) -> None:
        runtime = AgentRuntime(llm_gateway=PayloadGateway())

        with self.assertRaisesRegex(PromptProfileConfigurationError, "missing prompt profile"):
            runtime.act(tick_context("agent_a"))


class MalformedGateway:
    def complete(self, _: object) -> dict[str, object]:
        return {
            "candidates": [
                {
                    "content": "{not-json",
                    "finish_reason": "stop",
                }
            ]
        }


class FailingGateway:
    def complete(self, _: object) -> dict[str, object]:
        raise SchemaValidationError("llm_provider_error")


class PayloadGateway:
    def complete(self, _: object) -> dict[str, object]:
        return {
            "candidates": [
                {
                    "content": json.dumps(
                        {
                            "schema_version": "v1",
                            "tick_id": "2024-01-02T14:02:00+08:00",
                            "trace_id": "trace_abc",
                            "agent_id": "agent_a",
                            "action": {
                                "action_type": "buy",
                                "symbol": "demo_stock",
                                "order_type": "limit",
                                "price": 15.2,
                                "quantity": 100,
                                "time_in_force": "day",
                            },
                        }
                    ),
                    "finish_reason": "stop",
                }
            ]
        }


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from Ouroboros.core.agents import AgentRuntime
from Ouroboros.core.schemas import (
    AgentPayload,
    MemoryReadRequest,
    MemoryWriteRequest,
    OrderActionType,
    SchemaValidationError,
    TickContext,
)


def tick_context(
    agent_id: str = "agent_a",
    *,
    tick_id: str = "2024-01-02T14:02:00+08:00",
    can_post_forum: bool = False,
) -> TickContext:
    return TickContext.from_dict(
        {
            "schema_version": "v1",
            "tick_id": tick_id,
            "trace_id": "trace_abc",
            "agent_id": agent_id,
            "agent_role": "retail",
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
                "allowed_actions": ["buy", "sell", "cancel", "hold", "post_forum"],
                "deadline_ms": 30000,
                "can_post_forum": can_post_forum,
            },
        }
    )


class AgentRuntimeMockTests(unittest.TestCase):
    def test_default_action_is_safe_hold_payload(self) -> None:
        runtime = AgentRuntime()

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
        runtime = AgentRuntime()

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


if __name__ == "__main__":
    unittest.main()

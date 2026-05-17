"""Deterministic in-process mock AgentRuntime."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import replace
from typing import Any, Iterable, Mapping

from Ouroboros.core.schemas import (
    AgentAction,
    AgentPayload,
    MemoryReadRequest,
    MemoryReadResponse,
    MemoryWriteRequest,
    PrivateMemoryRef,
    SCHEMA_VERSION,
    SchemaValidationError,
    TickContext,
)
from Ouroboros.core.schemas.common import OrderActionType


ActionSpec = AgentAction | AgentPayload | Mapping[str, Any]


class AgentRuntime:
    """Deterministic mock runtime for Layer 1 agent tests.

    The runtime has no bus, LOB, ledger, or LLM dependencies. It only consumes
    the supplied TickContext plus its per-agent private memory store.
    """

    def __init__(
        self,
        *,
        default_actions: Mapping[str, ActionSpec] | None = None,
        scripted_actions: Mapping[str, Iterable[ActionSpec]] | None = None,
        memory_namespaces: Mapping[str, str] | None = None,
    ) -> None:
        self._default_actions = dict(default_actions or {})
        self._scripted_actions = {
            agent_id: deque(actions) for agent_id, actions in (scripted_actions or {}).items()
        }
        self._memory: dict[tuple[str, str], list[PrivateMemoryRef]] = defaultdict(list)
        self._namespace_owner: dict[str, str] = dict(
            (namespace, agent_id) for agent_id, namespace in (memory_namespaces or {}).items()
        )
        self._memory_sequence = 0

    def act(self, tick_context: TickContext | Mapping[str, Any]) -> AgentPayload:
        """Return a schema-valid AgentPayload for one TickContext."""

        context = self._coerce_tick_context(tick_context)
        spec = self._next_action_spec(context.agent_id)
        if spec is None:
            return self._hold_payload(context)

        try:
            payload = self._payload_from_spec(context, spec)
        except (SchemaValidationError, ValueError, TypeError):
            return self._hold_payload(context)

        if payload.tick_id != context.tick_id or payload.agent_id != context.agent_id:
            return self._hold_payload(context)
        if payload.trace_id != context.trace_id:
            return self._hold_payload(context)
        if payload.action.action_type not in context.constraints.allowed_actions:
            return self._hold_payload(context)
        if (
            payload.action.action_type == OrderActionType.POST_FORUM
            and not context.constraints.can_post_forum
        ):
            return self._hold_payload(context)

        payload = self._enforce_forum_permissions(context, payload)
        self._write_memory_update(context, payload)
        return AgentPayload.from_dict(payload.to_dict())

    def memory_read(
        self,
        request: MemoryReadRequest | Mapping[str, Any],
    ) -> MemoryReadResponse:
        """Read only the requesting agent's private memory namespace."""

        read_request = self._coerce_memory_read_request(request)
        self._ensure_namespace_access(
            read_request.agent_id,
            read_request.memory_namespace,
            allow_unclaimed=True,
        )
        refs = list(self._memory[(read_request.agent_id, read_request.memory_namespace)])
        return MemoryReadResponse(
            schema_version=SCHEMA_VERSION,
            agent_id=read_request.agent_id,
            tick_id=read_request.tick_id,
            memory_refs=refs[: read_request.limit],
        )

    def memory_write(
        self,
        request: MemoryWriteRequest | Mapping[str, Any],
    ) -> PrivateMemoryRef:
        """Write to the requesting agent's private memory namespace."""

        write_request = self._coerce_memory_write_request(request)
        self._ensure_namespace_access(
            write_request.agent_id,
            write_request.memory_namespace,
            allow_unclaimed=True,
        )
        memory_ref = PrivateMemoryRef(
            memory_id=self._next_memory_id(write_request.agent_id),
            memory_type=write_request.memory_type,
            summary=write_request.summary,
            source_refs=list(write_request.source_refs),
            created_tick_id=write_request.tick_id,
        )
        self._memory[(write_request.agent_id, write_request.memory_namespace)].append(
            memory_ref
        )
        return memory_ref

    def _next_action_spec(self, agent_id: str) -> ActionSpec | None:
        scripted = self._scripted_actions.get(agent_id)
        if scripted:
            return scripted.popleft()
        return self._default_actions.get(agent_id)

    def _payload_from_spec(self, context: TickContext, spec: ActionSpec) -> AgentPayload:
        if isinstance(spec, AgentPayload):
            return spec
        if isinstance(spec, AgentAction):
            return self._payload_from_action(context, spec)
        if not isinstance(spec, Mapping):
            raise SchemaValidationError("action spec must be a mapping or schema object")
        if "action" in spec:
            return AgentPayload.from_dict(spec)
        return self._payload_from_action(context, AgentAction.from_dict(spec))

    def _payload_from_action(self, context: TickContext, action: AgentAction) -> AgentPayload:
        return AgentPayload(
            schema_version=SCHEMA_VERSION,
            tick_id=context.tick_id,
            trace_id=context.trace_id,
            agent_id=context.agent_id,
            action=action,
        )

    def _hold_payload(self, context: TickContext) -> AgentPayload:
        return self._payload_from_action(
            context,
            AgentAction(action_type=OrderActionType.HOLD),
        )

    def _enforce_forum_permissions(
        self, context: TickContext, payload: AgentPayload
    ) -> AgentPayload:
        forum_post = payload.forum_post
        if forum_post is None:
            return payload

        allowed = (
            context.constraints.can_post_forum
            and OrderActionType.POST_FORUM in context.constraints.allowed_actions
            and forum_post.author_agent_id == context.agent_id
            and forum_post.tick_id == context.tick_id
            and forum_post.text != payload.thought
        )
        if allowed:
            return payload
        if payload.action.action_type == OrderActionType.POST_FORUM:
            return self._hold_payload(context)
        return replace(payload, forum_post=None)

    def _write_memory_update(self, context: TickContext, payload: AgentPayload) -> None:
        update = payload.memory_update
        if update is None or not update.should_write or update.summary is None:
            return
        namespace = self._default_namespace(context.agent_id)
        self.memory_write(
            MemoryWriteRequest(
                schema_version=SCHEMA_VERSION,
                agent_id=context.agent_id,
                memory_namespace=namespace,
                tick_id=context.tick_id,
                memory_type="decision_trace",
                summary=update.summary,
                source_refs=list(payload.evidence_refs),
            )
        )

    def _default_namespace(self, agent_id: str) -> str:
        for namespace, owner_agent_id in self._namespace_owner.items():
            if owner_agent_id == agent_id:
                return namespace
        namespace = f"mem_{agent_id}"
        self._namespace_owner[namespace] = agent_id
        return namespace

    def _ensure_namespace_access(
        self,
        agent_id: str,
        memory_namespace: str,
        *,
        allow_unclaimed: bool,
    ) -> None:
        owner = self._namespace_owner.get(memory_namespace)
        if owner is None and allow_unclaimed:
            self._namespace_owner[memory_namespace] = agent_id
            return
        if owner != agent_id:
            raise SchemaValidationError("memory_namespace is not owned by agent_id")

    def _next_memory_id(self, agent_id: str) -> str:
        self._memory_sequence += 1
        return f"mem_{agent_id}_{self._memory_sequence:06d}"

    def _coerce_tick_context(self, value: TickContext | Mapping[str, Any]) -> TickContext:
        if isinstance(value, TickContext):
            return value
        return TickContext.from_dict(value)

    def _coerce_memory_read_request(
        self, value: MemoryReadRequest | Mapping[str, Any]
    ) -> MemoryReadRequest:
        if isinstance(value, MemoryReadRequest):
            return value
        return MemoryReadRequest.from_dict(value)

    def _coerce_memory_write_request(
        self, value: MemoryWriteRequest | Mapping[str, Any]
    ) -> MemoryWriteRequest:
        if isinstance(value, MemoryWriteRequest):
            return value
        return MemoryWriteRequest.from_dict(value)

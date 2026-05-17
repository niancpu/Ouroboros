"""AgentRuntime boundary for turning TickContext into AgentPayload."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import replace
from typing import Any, Iterable, Mapping

from Ouroboros.core.llm import LLMGateway
from Ouroboros.core.schemas import (
    AgentAction,
    AgentPayload,
    AgentProfile,
    MemoryReadRequest,
    MemoryReadResponse,
    MemoryWriteRequest,
    PrivateMemoryRef,
    PromptProfile,
    SCHEMA_VERSION,
    SchemaValidationError,
    TickContext,
)
from Ouroboros.core.schemas.common import OrderActionType


ActionSpec = AgentAction | AgentPayload | Mapping[str, Any]


class PromptProfileConfigurationError(RuntimeError):
    """Raised when an LLM-backed agent lacks a usable prompt profile."""


class AgentRuntime:
    """Layer 1 runtime that calls LLMGateway unless scripted test actions exist.

    The runtime has no bus, LOB, or ledger dependency. It only consumes the
    supplied TickContext plus its per-agent private memory store.
    """

    def __init__(
        self,
        *,
        default_actions: Mapping[str, ActionSpec] | None = None,
        scripted_actions: Mapping[str, Iterable[ActionSpec]] | None = None,
        memory_namespaces: Mapping[str, str] | None = None,
        agent_profiles: Mapping[str, AgentProfile | Mapping[str, Any]] | None = None,
        prompt_profiles: Mapping[str, PromptProfile | Mapping[str, Any]] | None = None,
        allow_prompt_profile_fallback: bool = False,
        llm_gateway: LLMGateway | None = None,
        raise_llm_errors: bool = False,
    ) -> None:
        self._default_actions = dict(default_actions or {})
        self._scripted_actions = {
            agent_id: deque(actions) for agent_id, actions in (scripted_actions or {}).items()
        }
        self._llm_gateway = llm_gateway or LLMGateway()
        self._agent_profiles = {
            agent_id: _coerce_agent_profile(profile)
            for agent_id, profile in (agent_profiles or {}).items()
        }
        self._prompt_profiles = {
            profile_id: _coerce_prompt_profile(profile)
            for profile_id, profile in (prompt_profiles or {}).items()
        }
        self._allow_prompt_profile_fallback = allow_prompt_profile_fallback
        self._raise_llm_errors = raise_llm_errors
        self._memory: dict[tuple[str, str], list[PrivateMemoryRef]] = defaultdict(list)
        self._namespace_owner: dict[str, str] = dict(
            (namespace, agent_id) for agent_id, namespace in (memory_namespaces or {}).items()
        )
        for agent_id, profile in self._agent_profiles.items():
            self._namespace_owner.setdefault(profile.memory_namespace, agent_id)
        self._memory_sequence = 0
        self._last_errors: dict[str, str] = {}

    @property
    def last_errors(self) -> Mapping[str, str]:
        return dict(self._last_errors)

    @property
    def raises_llm_errors(self) -> bool:
        return self._raise_llm_errors

    def act(self, tick_context: TickContext | Mapping[str, Any]) -> AgentPayload:
        """Return a schema-valid AgentPayload for one TickContext."""

        context = self._coerce_tick_context(tick_context)
        spec = self._next_action_spec(context.agent_id)
        try:
            payload = (
                self._payload_from_llm(context)
                if spec is None
                else self._payload_from_spec(context, spec)
            )
        except (SchemaValidationError, ValueError, TypeError):
            if self._raise_llm_errors and spec is None:
                raise
            return self._hold_payload(context)

        if payload.tick_id != context.tick_id or payload.agent_id != context.agent_id:
            self._last_errors[context.agent_id] = "payload_identity_mismatch"
            if self._raise_llm_errors and spec is None:
                raise SchemaValidationError("payload_identity_mismatch")
            return self._hold_payload(context)
        if payload.trace_id != context.trace_id:
            self._last_errors[context.agent_id] = "payload_trace_mismatch"
            if self._raise_llm_errors and spec is None:
                raise SchemaValidationError("payload_trace_mismatch")
            return self._hold_payload(context)
        if payload.action.action_type not in context.constraints.allowed_actions:
            self._last_errors[context.agent_id] = "payload_action_not_allowed"
            if self._raise_llm_errors and spec is None:
                raise SchemaValidationError("payload_action_not_allowed")
            return self._hold_payload(context)
        if (
            payload.action.action_type == OrderActionType.POST_FORUM
            and not context.constraints.can_post_forum
        ):
            self._last_errors[context.agent_id] = "payload_forum_not_allowed"
            if self._raise_llm_errors and spec is None:
                raise SchemaValidationError("payload_forum_not_allowed")
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
            data = dict(spec)
            data.setdefault("schema_version", SCHEMA_VERSION)
            data.setdefault("tick_id", context.tick_id)
            data.setdefault("trace_id", context.trace_id)
            data.setdefault("agent_id", context.agent_id)
            return AgentPayload.from_dict(data)
        return self._payload_from_action(context, AgentAction.from_dict(spec))

    def _payload_from_llm(self, context: TickContext) -> AgentPayload:
        request = self._llm_request(context)
        try:
            output = self._llm_gateway.complete(request)
            content = output["candidates"][0]["content"]
            payload_data = json.loads(content)
        except json.JSONDecodeError as exc:
            self._last_errors[context.agent_id] = "payload_parse_error"
            if self._raise_llm_errors:
                raise SchemaValidationError("payload_parse_error") from exc
            return self._hold_payload(context)
        except (KeyError, IndexError, TypeError) as exc:
            self._last_errors[context.agent_id] = "payload_parse_error"
            raise SchemaValidationError("payload_parse_error") from exc
        except SchemaValidationError as exc:
            message = str(exc)
            if "content must be JSON" in message or "payload_parse_error" in message:
                self._last_errors[context.agent_id] = "payload_parse_error"
                if self._raise_llm_errors:
                    raise SchemaValidationError("payload_parse_error") from exc
                return self._hold_payload(context)
            self._last_errors[context.agent_id] = message or "llm_error"
            if self._raise_llm_errors:
                raise
            return self._hold_payload(context)

        if not isinstance(payload_data, Mapping):
            self._last_errors[context.agent_id] = "payload_parse_error"
            if self._raise_llm_errors:
                raise SchemaValidationError("payload_parse_error")
            return self._hold_payload(context)

        payload_data = dict(payload_data)
        payload_data.setdefault("schema_version", SCHEMA_VERSION)
        payload_data.setdefault("tick_id", context.tick_id)
        payload_data.setdefault("trace_id", context.trace_id)
        payload_data.setdefault("agent_id", context.agent_id)
        try:
            return AgentPayload.from_dict(payload_data)
        except (SchemaValidationError, ValueError, TypeError) as exc:
            self._last_errors[context.agent_id] = "payload_parse_error"
            raise SchemaValidationError("payload_parse_error") from exc

    def _llm_request(self, context: TickContext) -> dict[str, Any]:
        agent_profile, prompt_profile = self._resolve_prompt_profile(context)
        prompt_profile_data = prompt_profile.to_dict()
        agent_profile_data = agent_profile.to_dict() if agent_profile is not None else None
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": f"llm_{_stable_id(context.agent_id)}_{_stable_id(context.tick_id)}",
            "agent_id": context.agent_id,
            "tick_id": context.tick_id,
            "prompt_profile_id": prompt_profile.prompt_profile_id,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return exactly one JSON object matching AgentPayload. "
                        "Do not include settlement, cash mutation, or hidden fields."
                    ),
                },
                {
                    "role": "developer",
                    "content": json.dumps(
                        {
                            "prompt_profile": {
                                "prompt_profile_id": prompt_profile_data[
                                    "prompt_profile_id"
                                ],
                                "agent_type": prompt_profile_data["agent_type"],
                                "system_role": prompt_profile_data["system_role"],
                                "behavior_rules": prompt_profile_data["behavior_rules"],
                                "risk_rules": prompt_profile_data["risk_rules"],
                                "output_schema_ref": prompt_profile_data[
                                    "output_schema_ref"
                                ],
                                "forbidden_claims": prompt_profile_data[
                                    "forbidden_claims"
                                ],
                            },
                            "agent_profile": _agent_profile_prompt_view(
                                agent_profile_data
                            ),
                            "permission_boundary": {
                                "source": "tick_context.constraints",
                                "allowed_actions": [
                                    action.value
                                    for action in context.constraints.allowed_actions
                                ],
                                "can_post_forum": context.constraints.can_post_forum,
                                "rule": (
                                    "Prompt profile changes style only. It cannot add "
                                    "actions, input channels, data visibility, cash, "
                                    "positions, or settlement authority."
                                ),
                            },
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(context.to_dict(), ensure_ascii=False, sort_keys=True),
                },
            ],
            "output_schema_ref": prompt_profile.output_schema_ref,
            "deadline_ms": context.constraints.deadline_ms,
        }

    def _resolve_prompt_profile(
        self, context: TickContext
    ) -> tuple[AgentProfile | None, PromptProfile]:
        agent_profile = self._agent_profiles.get(context.agent_id)
        prompt_profile_id = (
            agent_profile.prompt_profile_ref
            if agent_profile is not None
            else _context_prompt_profile_id(context)
        )
        if prompt_profile_id is None and self._allow_prompt_profile_fallback:
            prompt_profile_id = "runtime_test_fallback"
        if prompt_profile_id is None:
            raise PromptProfileConfigurationError(
                f"missing prompt profile for agent_id={context.agent_id}"
            )
        prompt_profile = self._prompt_profiles.get(prompt_profile_id)
        if prompt_profile is None and self._allow_prompt_profile_fallback:
            prompt_profile = _fallback_prompt_profile(context, prompt_profile_id)
        if prompt_profile is None:
            raise PromptProfileConfigurationError(
                f"unknown prompt profile {prompt_profile_id!r} for agent_id={context.agent_id}"
            )
        if prompt_profile.agent_type.value != context.agent_role:
            raise PromptProfileConfigurationError(
                "prompt profile agent_type does not match tick_context.agent_role"
            )
        if agent_profile is not None and agent_profile.agent_type != prompt_profile.agent_type:
            raise PromptProfileConfigurationError(
                "agent profile agent_type does not match prompt profile agent_type"
            )
        return agent_profile, prompt_profile

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


def _stable_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_") or "unknown"


def _coerce_agent_profile(value: AgentProfile | Mapping[str, Any]) -> AgentProfile:
    if isinstance(value, AgentProfile):
        return value
    return AgentProfile.from_dict(value)


def _coerce_prompt_profile(value: PromptProfile | Mapping[str, Any]) -> PromptProfile:
    if isinstance(value, PromptProfile):
        return value
    return PromptProfile.from_dict(value)


def _context_prompt_profile_id(context: TickContext) -> str | None:
    value = context.private_inputs.get("prompt_profile_id") or context.public_inputs.get(
        "prompt_profile_id"
    )
    return str(value) if value is not None else None


def _fallback_prompt_profile(context: TickContext, prompt_profile_id: str) -> PromptProfile:
    return PromptProfile.from_dict(
        {
            "schema_version": SCHEMA_VERSION,
            "prompt_profile_id": prompt_profile_id,
            "agent_type": context.agent_role,
            "system_role": "Test fallback agent profile.",
            "behavior_rules": ["Use only the supplied tick_context."],
            "risk_rules": ["Do not infer permissions outside tick_context.constraints."],
            "output_schema_ref": "agent_payload.v1",
            "forbidden_claims": [],
        }
    )


def _agent_profile_prompt_view(data: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    return {
        "agent_id": data["agent_id"],
        "agent_type": data["agent_type"],
        "display_name": data["display_name"],
        "seat_alias": data.get("seat_alias"),
        "strategy_bias": data["strategy_bias"],
        "risk_profile": data["risk_profile"],
        "prompt_profile_ref": data["prompt_profile_ref"],
        "memory_namespace": data["memory_namespace"],
    }

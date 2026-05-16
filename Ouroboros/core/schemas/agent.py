"""Agent-facing input and output payload schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .common import (
    AgentType,
    InternalVisibility,
    OrderActionType,
    OrderType,
    PRIVATE_FIELD_NAMES,
    SCHEMA_VERSION,
    Sentiment,
    Stance,
    TimeInForce,
    coerce_enum,
    ensure_no_forbidden_keys,
    ensure_schema_version,
    optional_str,
    reject_unknown_keys,
    require_int,
    require_mapping,
    require_non_empty_str,
    require_number,
    require_str_list,
    to_plain_data,
)


@dataclass(frozen=True)
class AgentAction:
    action_type: OrderActionType
    symbol: str | None = None
    order_type: OrderType | None = None
    price: float | None = None
    quantity: int | None = None
    time_in_force: TimeInForce | None = None
    client_order_id: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentAction":
        data = require_mapping(data, "action")
        ensure_no_forbidden_keys(data, PRIVATE_FIELD_NAMES, "AgentAction")
        reject_unknown_keys(
            data,
            {
                "action_type",
                "symbol",
                "order_type",
                "price",
                "quantity",
                "time_in_force",
                "client_order_id",
            },
            "AgentAction",
        )
        action_type = coerce_enum(OrderActionType, data.get("action_type"), "action_type")
        symbol = optional_str(data.get("symbol"), "symbol")
        order_type = (
            coerce_enum(OrderType, data["order_type"], "order_type")
            if data.get("order_type") is not None
            else None
        )
        price = (
            require_number(data["price"], "price", minimum=0)
            if data.get("price") is not None
            else None
        )
        quantity = (
            require_int(data["quantity"], "quantity", minimum=1)
            if data.get("quantity") is not None
            else None
        )
        time_in_force = (
            coerce_enum(TimeInForce, data["time_in_force"], "time_in_force")
            if data.get("time_in_force") is not None
            else None
        )
        client_order_id = optional_str(data.get("client_order_id"), "client_order_id")

        action = cls(
            action_type=action_type,
            symbol=symbol,
            order_type=order_type,
            price=price,
            quantity=quantity,
            time_in_force=time_in_force,
            client_order_id=client_order_id,
        )
        action.validate()
        return action

    def validate(self) -> None:
        if self.action_type in {OrderActionType.BUY, OrderActionType.SELL}:
            require_non_empty_str(self.symbol, "symbol")
            if self.order_type is None:
                raise ValueError("order_type is required for buy/sell actions")
            if self.quantity is None:
                raise ValueError("quantity is required for buy/sell actions")
            require_int(self.quantity, "quantity", minimum=1)
            if self.order_type == OrderType.LIMIT and self.price is None:
                raise ValueError("price is required for limit orders")

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class BeliefShift:
    confidence_delta: float
    sentiment: Sentiment
    risk_appetite_delta: float

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BeliefShift":
        data = require_mapping(data, "belief_shift")
        reject_unknown_keys(
            data,
            {"confidence_delta", "sentiment", "risk_appetite_delta"},
            "BeliefShift",
        )
        return cls(
            confidence_delta=require_number(data.get("confidence_delta"), "confidence_delta"),
            sentiment=coerce_enum(Sentiment, data.get("sentiment"), "sentiment"),
            risk_appetite_delta=require_number(
                data.get("risk_appetite_delta"), "risk_appetite_delta"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class ForumPost:
    post_id: str
    author_agent_id: str
    tick_id: str
    text: str
    stance: Stance
    visibility: InternalVisibility = InternalVisibility.PUBLIC

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ForumPost":
        data = require_mapping(data, "forum_post")
        ensure_no_forbidden_keys(data, PRIVATE_FIELD_NAMES, "ForumPost")
        reject_unknown_keys(
            data,
            {"post_id", "author_agent_id", "tick_id", "text", "stance", "visibility"},
            "ForumPost",
        )
        visibility = coerce_enum(
            InternalVisibility, data.get("visibility", "public"), "visibility"
        )
        if visibility != InternalVisibility.PUBLIC:
            raise ValueError("forum_post visibility must be public")
        return cls(
            post_id=require_non_empty_str(data.get("post_id"), "post_id"),
            author_agent_id=require_non_empty_str(
                data.get("author_agent_id"), "author_agent_id"
            ),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            text=require_non_empty_str(data.get("text"), "text"),
            stance=coerce_enum(Stance, data.get("stance"), "stance"),
            visibility=visibility,
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class MemoryUpdate:
    should_write: bool
    summary: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryUpdate":
        data = require_mapping(data, "memory_update")
        reject_unknown_keys(data, {"should_write", "summary"}, "MemoryUpdate")
        should_write = data.get("should_write")
        if not isinstance(should_write, bool):
            raise ValueError("should_write must be a boolean")
        summary = optional_str(data.get("summary"), "summary")
        if should_write and summary is None:
            raise ValueError("summary is required when should_write is true")
        return cls(should_write=should_write, summary=summary)

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class MemoryWindow:
    lookback_ticks: int
    retrieved_memory_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryWindow":
        data = require_mapping(data, "memory_window")
        reject_unknown_keys(data, {"lookback_ticks", "retrieved_memory_ids"}, "MemoryWindow")
        return cls(
            lookback_ticks=require_int(data.get("lookback_ticks"), "lookback_ticks", minimum=0),
            retrieved_memory_ids=require_str_list(
                data.get("retrieved_memory_ids", []), "retrieved_memory_ids"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class PrivateMemoryRef:
    memory_id: str
    memory_type: str
    summary: str
    source_refs: list[str]
    created_tick_id: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PrivateMemoryRef":
        data = require_mapping(data, "PrivateMemoryRef")
        reject_unknown_keys(
            data,
            {"memory_id", "memory_type", "summary", "source_refs", "created_tick_id"},
            "PrivateMemoryRef",
        )
        return cls(
            memory_id=require_non_empty_str(data.get("memory_id"), "memory_id"),
            memory_type=require_non_empty_str(data.get("memory_type"), "memory_type"),
            summary=require_non_empty_str(data.get("summary"), "summary"),
            source_refs=require_str_list(data.get("source_refs", []), "source_refs"),
            created_tick_id=require_non_empty_str(data.get("created_tick_id"), "created_tick_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class PublishPermissions:
    order_action: bool
    ui_audit: bool
    forum_post: bool

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PublishPermissions":
        data = require_mapping(data, "publish_permissions")
        reject_unknown_keys(
            data, {"order_action", "ui_audit", "forum_post"}, "PublishPermissions"
        )
        values = {
            "order_action": data.get("order_action"),
            "ui_audit": data.get("ui_audit"),
            "forum_post": data.get("forum_post"),
        }
        for key, value in values.items():
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be a boolean")
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class AgentPermissionProfile:
    schema_version: str
    agent_id: str
    agent_type: AgentType
    subscriptions: list[str]
    publish_permissions: PublishPermissions
    official_news_scope: list[str]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentPermissionProfile":
        data = require_mapping(data, "AgentPermissionProfile")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            agent_type=coerce_enum(AgentType, data.get("agent_type"), "agent_type"),
            subscriptions=require_str_list(data.get("subscriptions", []), "subscriptions"),
            publish_permissions=PublishPermissions.from_dict(
                data.get("publish_permissions")
            ),
            official_news_scope=require_str_list(
                data.get("official_news_scope", []), "official_news_scope"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class AgentProfile:
    agent_id: str
    agent_type: AgentType
    display_name: str
    seat_alias: str | None
    strategy_bias: dict[str, Any]
    risk_profile: dict[str, Any]
    prompt_profile_ref: str
    memory_namespace: str
    permission_profile_ref: str
    initial_asset_plan_ref: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentProfile":
        data = require_mapping(data, "AgentProfile")
        return cls(
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            agent_type=coerce_enum(AgentType, data.get("agent_type"), "agent_type"),
            display_name=require_non_empty_str(data.get("display_name"), "display_name"),
            seat_alias=optional_str(data.get("seat_alias"), "seat_alias"),
            strategy_bias=dict(require_mapping(data.get("strategy_bias", {}), "strategy_bias")),
            risk_profile=dict(require_mapping(data.get("risk_profile", {}), "risk_profile")),
            prompt_profile_ref=require_non_empty_str(
                data.get("prompt_profile_ref"), "prompt_profile_ref"
            ),
            memory_namespace=require_non_empty_str(
                data.get("memory_namespace"), "memory_namespace"
            ),
            permission_profile_ref=require_non_empty_str(
                data.get("permission_profile_ref"), "permission_profile_ref"
            ),
            initial_asset_plan_ref=require_non_empty_str(
                data.get("initial_asset_plan_ref"), "initial_asset_plan_ref"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class AgentProfileSet:
    schema_version: str
    profile_set_id: str
    agents: list[AgentProfile]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentProfileSet":
        data = require_mapping(data, "AgentProfileSet")
        ensure_schema_version(data)
        agents = data.get("agents", [])
        if not isinstance(agents, list):
            raise ValueError("agents must be a list")
        return cls(
            schema_version=SCHEMA_VERSION,
            profile_set_id=require_non_empty_str(data.get("profile_set_id"), "profile_set_id"),
            agents=[AgentProfile.from_dict(item) for item in agents],
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class PromptProfile:
    schema_version: str
    prompt_profile_id: str
    agent_type: AgentType
    system_role: str
    behavior_rules: list[str]
    risk_rules: list[str]
    output_schema_ref: str
    forbidden_claims: list[str]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PromptProfile":
        data = require_mapping(data, "PromptProfile")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            prompt_profile_id=require_non_empty_str(
                data.get("prompt_profile_id"), "prompt_profile_id"
            ),
            agent_type=coerce_enum(AgentType, data.get("agent_type"), "agent_type"),
            system_role=require_non_empty_str(data.get("system_role"), "system_role"),
            behavior_rules=require_str_list(data.get("behavior_rules", []), "behavior_rules"),
            risk_rules=require_str_list(data.get("risk_rules", []), "risk_rules"),
            output_schema_ref=require_non_empty_str(
                data.get("output_schema_ref"), "output_schema_ref"
            ),
            forbidden_claims=require_str_list(
                data.get("forbidden_claims", []), "forbidden_claims"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class MemoryReadRequest:
    schema_version: str
    agent_id: str
    memory_namespace: str
    tick_id: str
    query: str
    limit: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryReadRequest":
        data = require_mapping(data, "MemoryReadRequest")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            memory_namespace=require_non_empty_str(
                data.get("memory_namespace"), "memory_namespace"
            ),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            query=require_non_empty_str(data.get("query"), "query"),
            limit=require_int(data.get("limit"), "limit", minimum=1),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class MemoryReadResponse:
    schema_version: str
    agent_id: str
    tick_id: str
    memory_refs: list[PrivateMemoryRef]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryReadResponse":
        data = require_mapping(data, "MemoryReadResponse")
        ensure_schema_version(data)
        refs = data.get("memory_refs", [])
        if not isinstance(refs, list):
            raise ValueError("memory_refs must be a list")
        return cls(
            schema_version=SCHEMA_VERSION,
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            memory_refs=[PrivateMemoryRef.from_dict(item) for item in refs],
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class MemoryWriteRequest:
    schema_version: str
    agent_id: str
    memory_namespace: str
    tick_id: str
    memory_type: str
    summary: str
    source_refs: list[str]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryWriteRequest":
        data = require_mapping(data, "MemoryWriteRequest")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            memory_namespace=require_non_empty_str(
                data.get("memory_namespace"), "memory_namespace"
            ),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            memory_type=require_non_empty_str(data.get("memory_type"), "memory_type"),
            summary=require_non_empty_str(data.get("summary"), "summary"),
            source_refs=require_str_list(data.get("source_refs", []), "source_refs"),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LLMMessage":
        data = require_mapping(data, "LLMMessage")
        return cls(
            role=require_non_empty_str(data.get("role"), "role"),
            content=require_non_empty_str(data.get("content"), "content"),
        )


@dataclass(frozen=True)
class LLMRequest:
    schema_version: str
    request_id: str
    agent_id: str
    tick_id: str
    prompt_profile_id: str
    messages: list[LLMMessage]
    output_schema_ref: str
    deadline_ms: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LLMRequest":
        data = require_mapping(data, "LLMRequest")
        ensure_schema_version(data)
        messages = data.get("messages", [])
        if not isinstance(messages, list):
            raise ValueError("messages must be a list")
        return cls(
            schema_version=SCHEMA_VERSION,
            request_id=require_non_empty_str(data.get("request_id"), "request_id"),
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            prompt_profile_id=require_non_empty_str(
                data.get("prompt_profile_id"), "prompt_profile_id"
            ),
            messages=[LLMMessage.from_dict(item) for item in messages],
            output_schema_ref=require_non_empty_str(
                data.get("output_schema_ref"), "output_schema_ref"
            ),
            deadline_ms=require_int(data.get("deadline_ms"), "deadline_ms", minimum=1),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class AgentConstraints:
    allowed_actions: list[OrderActionType]
    deadline_ms: int
    can_post_forum: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentConstraints":
        data = require_mapping(data, "constraints")
        reject_unknown_keys(
            data, {"allowed_actions", "deadline_ms", "can_post_forum"}, "AgentConstraints"
        )
        allowed = data.get("allowed_actions")
        if not isinstance(allowed, list):
            raise ValueError("allowed_actions must be a list")
        can_post_forum = data.get("can_post_forum", False)
        if not isinstance(can_post_forum, bool):
            raise ValueError("can_post_forum must be a boolean")
        return cls(
            allowed_actions=[
                coerce_enum(OrderActionType, item, "allowed_actions[]") for item in allowed
            ],
            deadline_ms=require_int(data.get("deadline_ms"), "deadline_ms", minimum=1),
            can_post_forum=can_post_forum,
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class TickContext:
    schema_version: str
    tick_id: str
    trace_id: str
    agent_id: str
    agent_role: str
    public_inputs: dict[str, Any]
    private_inputs: dict[str, Any]
    constraints: AgentConstraints

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TickContext":
        data = require_mapping(data, "TickContext")
        ensure_schema_version(data)
        reject_unknown_keys(
            data,
            {
                "schema_version",
                "tick_id",
                "trace_id",
                "agent_id",
                "agent_role",
                "public_inputs",
                "private_inputs",
                "constraints",
            },
            "TickContext",
        )
        public_inputs = dict(require_mapping(data.get("public_inputs"), "public_inputs"))
        private_inputs = dict(require_mapping(data.get("private_inputs"), "private_inputs"))
        return cls(
            schema_version=SCHEMA_VERSION,
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            agent_role=require_non_empty_str(data.get("agent_role"), "agent_role"),
            public_inputs=public_inputs,
            private_inputs=private_inputs,
            constraints=AgentConstraints.from_dict(data.get("constraints")),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class AgentPayload:
    schema_version: str
    tick_id: str
    trace_id: str
    agent_id: str
    action: AgentAction
    thought: str | None = None
    belief_shift: BeliefShift | None = None
    evidence_refs: list[str] = field(default_factory=list)
    forum_post: ForumPost | None = None
    memory_update: MemoryUpdate | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentPayload":
        data = require_mapping(data, "AgentPayload")
        ensure_schema_version(data)
        reject_unknown_keys(
            data,
            {
                "schema_version",
                "tick_id",
                "trace_id",
                "agent_id",
                "action",
                "thought",
                "belief_shift",
                "evidence_refs",
                "forum_post",
                "memory_update",
            },
            "AgentPayload",
        )
        return cls(
            schema_version=SCHEMA_VERSION,
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            action=AgentAction.from_dict(data.get("action")),
            thought=optional_str(data.get("thought"), "thought"),
            belief_shift=(
                BeliefShift.from_dict(data["belief_shift"])
                if data.get("belief_shift") is not None
                else None
            ),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "evidence_refs"),
            forum_post=(
                ForumPost.from_dict(data["forum_post"])
                if data.get("forum_post") is not None
                else None
            ),
            memory_update=(
                MemoryUpdate.from_dict(data["memory_update"])
                if data.get("memory_update") is not None
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)

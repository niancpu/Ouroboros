"""Layer 2 channel routing and access control."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable, Mapping
import copy

from Ouroboros.core.schemas.agent import AgentPermissionProfile
from Ouroboros.core.schemas.common import (
    PRIVATE_FIELD_NAMES,
    SCHEMA_VERSION,
    AgentType,
    InternalVisibility,
    SchemaValidationError,
    coerce_enum,
    ensure_no_forbidden_keys,
    ensure_schema_version,
    require_mapping,
    require_non_empty_str,
    require_number,
    require_str_list,
)
from Ouroboros.core.schemas.market import (
    AccountSnapshotEvent,
    AuditGraphEvent,
    CausalChainEvent,
    EndOfDayEvent,
    ForumRumorEvent,
    MarketPriceEvent,
    OfficialNewsEvent,
    OrderInputEvent,
    TapeAlertEvent,
)

from .bus import BufferedEvent, RedisBus


class Channel(StrEnum):
    ORDER_INPUT = "Order_Input"
    UI_AUDIT = "UI_Audit"
    OFFICIAL_NEWS = "Official_News"
    MARKET_PRICE = "Market_Price"
    ACCOUNT_SNAPSHOT = "Account_Snapshot"
    TAPE_ALERTS = "Tape_Alerts"
    END_OF_DAY = "End_of_Day"
    FORUM_RUMORS = "Forum_Rumors"
    FRONTEND_AUDIT_GRAPH = "Frontend_Audit_Graph"
    FRONTEND_CAUSAL_CHAIN = "Frontend_Causal_Chain"
    FORUM_RUMORS_INTERNAL = "Forum_Rumors_Internal"


class SubscriberRole(StrEnum):
    AGENT_RUNTIME = "agent_runtime"
    FRONTEND_GATEWAY = "frontend_gateway"
    MATCHING_ENGINE = "matching_engine"
    UI_AUDIT_OFFICER = "ui_audit_officer"
    INTERNAL_VALIDATOR = "internal_validator"


class RoutingAccessError(PermissionError):
    """Raised when a publisher or subscriber is not allowed for a channel."""


@dataclass(frozen=True)
class SubscriberRef:
    subscriber_id: str
    role: SubscriberRole | str
    agent_id: str | None = None

    def normalized_role(self) -> SubscriberRole:
        return coerce_enum(SubscriberRole, self.role, "subscriber.role")


@dataclass(frozen=True)
class ChannelPolicy:
    publishers: frozenset[str]
    subscriber_roles: frozenset[SubscriberRole]
    validator: Callable[[Mapping[str, Any]], dict[str, Any]]
    agent_input_channel: bool = False
    agent_self_only: bool = False


def _typed_validator(schema_cls: Any) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    def validate(payload: Mapping[str, Any]) -> dict[str, Any]:
        return schema_cls.from_dict(payload).to_dict()

    return validate


def _validate_ui_audit(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(require_mapping(payload, "UIAuditEvent"))
    ensure_schema_version(data)
    forbidden = PRIVATE_FIELD_NAMES - frozenset({"thought", "belief_shift"})
    ensure_no_forbidden_keys(data, forbidden, "UIAuditEvent")
    allowed = {
        "schema_version",
        "event_id",
        "tick_id",
        "trace_id",
        "producer",
        "visibility",
        "created_at",
        "agent_id",
        "thought",
        "belief_shift",
        "evidence_refs",
    }
    unknown = sorted(str(key) for key in data if key not in allowed)
    if unknown:
        raise SchemaValidationError(
            f"UIAuditEvent has unknown field(s): {', '.join(unknown)}"
        )
    for field_name in ("event_id", "tick_id", "trace_id", "producer", "agent_id"):
        require_non_empty_str(data.get(field_name), field_name)
    if data.get("schema_version") != SCHEMA_VERSION:
        raise SchemaValidationError(
            f"schema_version must be {SCHEMA_VERSION!r}; got {data.get('schema_version')!r}"
        )
    visibility = coerce_enum(InternalVisibility, data.get("visibility"), "visibility")
    if visibility != InternalVisibility.CONTROL_ONLY:
        raise SchemaValidationError("UIAuditEvent visibility must be control_only")
    if data.get("thought") is not None:
        require_non_empty_str(data.get("thought"), "thought")
    if data.get("belief_shift") is not None:
        if isinstance(data["belief_shift"], Mapping):
            dict(data["belief_shift"])
        else:
            require_number(data["belief_shift"], "belief_shift")
    require_str_list(data.get("evidence_refs", []), "evidence_refs")
    data["schema_version"] = SCHEMA_VERSION
    data["visibility"] = visibility.value
    data["evidence_refs"] = list(data.get("evidence_refs", []))
    return copy.deepcopy(data)


def _validate_forum_rumors_internal(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(require_mapping(payload, "ForumRumorsInternalEvent"))
    ensure_schema_version(data)
    ensure_no_forbidden_keys(data, PRIVATE_FIELD_NAMES, "ForumRumorsInternalEvent")
    for field_name in ("event_id", "tick_id", "trace_id", "producer", "post_id"):
        require_non_empty_str(data.get(field_name), field_name)
    visibility = coerce_enum(InternalVisibility, data.get("visibility"), "visibility")
    if visibility != InternalVisibility.CONTROL_ONLY:
        raise SchemaValidationError("ForumRumorsInternalEvent visibility must be control_only")
    data["visibility"] = visibility.value
    return copy.deepcopy(data)


CHANNEL_POLICIES: dict[Channel, ChannelPolicy] = {
    Channel.ORDER_INPUT: ChannelPolicy(
        publishers=frozenset({"meta_orchestrator"}),
        subscriber_roles=frozenset({SubscriberRole.MATCHING_ENGINE}),
        validator=_typed_validator(OrderInputEvent),
    ),
    Channel.UI_AUDIT: ChannelPolicy(
        publishers=frozenset({"meta_orchestrator"}),
        subscriber_roles=frozenset({SubscriberRole.UI_AUDIT_OFFICER}),
        validator=_validate_ui_audit,
    ),
    Channel.OFFICIAL_NEWS: ChannelPolicy(
        publishers=frozenset({"chronos", "layer0"}),
        subscriber_roles=frozenset({SubscriberRole.AGENT_RUNTIME, SubscriberRole.FRONTEND_GATEWAY}),
        validator=_typed_validator(OfficialNewsEvent),
        agent_input_channel=True,
    ),
    Channel.MARKET_PRICE: ChannelPolicy(
        publishers=frozenset({"market_data_publisher"}),
        subscriber_roles=frozenset({SubscriberRole.AGENT_RUNTIME, SubscriberRole.FRONTEND_GATEWAY}),
        validator=_typed_validator(MarketPriceEvent),
        agent_input_channel=True,
    ),
    Channel.ACCOUNT_SNAPSHOT: ChannelPolicy(
        publishers=frozenset({"clearing_house"}),
        subscriber_roles=frozenset({SubscriberRole.AGENT_RUNTIME, SubscriberRole.FRONTEND_GATEWAY}),
        validator=_typed_validator(AccountSnapshotEvent),
        agent_input_channel=True,
        agent_self_only=True,
    ),
    Channel.TAPE_ALERTS: ChannelPolicy(
        publishers=frozenset({"exchange_broadcaster"}),
        subscriber_roles=frozenset({SubscriberRole.AGENT_RUNTIME, SubscriberRole.FRONTEND_GATEWAY}),
        validator=_typed_validator(TapeAlertEvent),
        agent_input_channel=True,
    ),
    Channel.END_OF_DAY: ChannelPolicy(
        publishers=frozenset({"exchange_broadcaster"}),
        subscriber_roles=frozenset({SubscriberRole.AGENT_RUNTIME, SubscriberRole.FRONTEND_GATEWAY}),
        validator=_typed_validator(EndOfDayEvent),
        agent_input_channel=True,
    ),
    Channel.FORUM_RUMORS: ChannelPolicy(
        publishers=frozenset({"meta_orchestrator"}),
        subscriber_roles=frozenset({SubscriberRole.AGENT_RUNTIME, SubscriberRole.FRONTEND_GATEWAY}),
        validator=_typed_validator(ForumRumorEvent),
        agent_input_channel=True,
    ),
    Channel.FRONTEND_AUDIT_GRAPH: ChannelPolicy(
        publishers=frozenset({"ui_audit_officer"}),
        subscriber_roles=frozenset({SubscriberRole.FRONTEND_GATEWAY}),
        validator=_typed_validator(AuditGraphEvent),
    ),
    Channel.FRONTEND_CAUSAL_CHAIN: ChannelPolicy(
        publishers=frozenset({"ui_audit_officer"}),
        subscriber_roles=frozenset({SubscriberRole.FRONTEND_GATEWAY}),
        validator=_typed_validator(CausalChainEvent),
    ),
    Channel.FORUM_RUMORS_INTERNAL: ChannelPolicy(
        publishers=frozenset({"meta_orchestrator"}),
        subscriber_roles=frozenset({SubscriberRole.INTERNAL_VALIDATOR}),
        validator=_validate_forum_rumors_internal,
    ),
}


class ChannelRouter:
    """Policy-enforcing facade over the in-process bus."""

    def __init__(
        self,
        *,
        session_id: str,
        bus: RedisBus | None = None,
        default_ttl_seconds: float = 60.0,
    ) -> None:
        require_non_empty_str(session_id, "session_id")
        self.session_id = session_id
        self.bus = bus or RedisBus(default_ttl_seconds=default_ttl_seconds)
        self._agent_subscriptions: dict[str, frozenset[str]] = {}
        self._agent_types: dict[str, AgentType] = {}

    def namespaced_channel(self, channel: Channel | str) -> str:
        return self.bus.namespaced_channel(self.session_id, self._coerce_channel(channel).value)

    def register_agent_permissions(
        self, profile: AgentPermissionProfile | Mapping[str, Any]
    ) -> AgentPermissionProfile:
        parsed = (
            profile
            if isinstance(profile, AgentPermissionProfile)
            else AgentPermissionProfile.from_dict(profile)
        )
        self._agent_subscriptions[parsed.agent_id] = frozenset(parsed.subscriptions)
        self._agent_types[parsed.agent_id] = parsed.agent_type
        return parsed

    def publish(
        self,
        channel: Channel | str,
        payload: Mapping[str, Any] | Any,
        *,
        producer: str | None = None,
        ttl_seconds: float | None = None,
    ) -> BufferedEvent:
        channel_enum = self._coerce_channel(channel)
        policy = CHANNEL_POLICIES[channel_enum]
        payload_data = self._payload_to_mapping(payload)
        validated = policy.validator(payload_data)
        actual_producer = producer or str(validated.get("producer", ""))
        if producer is not None and validated.get("producer") != producer:
            raise RoutingAccessError("producer argument must match payload producer")
        if actual_producer not in policy.publishers:
            raise RoutingAccessError(
                f"{actual_producer!r} cannot publish to {channel_enum.value}"
            )
        if policy.agent_input_channel:
            ensure_no_forbidden_keys(validated, PRIVATE_FIELD_NAMES, channel_enum.value)

        return self.bus.publish(
            self.namespaced_channel(channel_enum),
            validated,
            ttl_seconds=ttl_seconds,
        )

    def subscribe(
        self,
        channel: Channel | str,
        subscriber: SubscriberRef,
        handler: Callable[[dict[str, Any]], None],
    ) -> int:
        channel_enum = self._coerce_channel(channel)
        self._assert_subscription_allowed(channel_enum, subscriber)

        def guarded_handler(payload: dict[str, Any]) -> None:
            if self._event_visible_to_subscriber(channel_enum, subscriber, payload):
                handler(copy.deepcopy(payload))

        return self.bus.subscribe(self.namespaced_channel(channel_enum), guarded_handler)

    def replay_for_subscriber(
        self, channel: Channel | str, subscriber: SubscriberRef
    ) -> list[dict[str, Any]]:
        channel_enum = self._coerce_channel(channel)
        self._assert_subscription_allowed(channel_enum, subscriber)
        events = self.bus.replay(self.namespaced_channel(channel_enum))
        return [
            event
            for event in events
            if self._event_visible_to_subscriber(channel_enum, subscriber, event)
        ]

    def build_agent_input_events(self, agent_id: str) -> dict[str, list[dict[str, Any]]]:
        require_non_empty_str(agent_id, "agent_id")
        if agent_id not in self._agent_subscriptions:
            raise RoutingAccessError(f"agent {agent_id!r} has no registered permissions")
        subscriber = SubscriberRef(
            subscriber_id=agent_id,
            role=SubscriberRole.AGENT_RUNTIME,
            agent_id=agent_id,
        )
        inputs: dict[str, list[dict[str, Any]]] = {}
        for subscription in sorted(self._agent_subscriptions[agent_id]):
            channel_name = subscription.removesuffix(":self")
            try:
                channel = self._coerce_channel(channel_name)
            except ValueError:
                continue
            policy = CHANNEL_POLICIES[channel]
            if not policy.agent_input_channel:
                continue
            inputs[channel.value] = self.replay_for_subscriber(channel, subscriber)
        return inputs

    def evict_expired(self) -> int:
        return self.bus.evict_expired()

    def evict_channel(self, channel: Channel | str) -> int:
        return self.bus.evict_channel(self.namespaced_channel(channel))

    @staticmethod
    def _payload_to_mapping(payload: Mapping[str, Any] | Any) -> Mapping[str, Any]:
        if isinstance(payload, Mapping):
            return payload
        if hasattr(payload, "to_dict"):
            data = payload.to_dict()
            return require_mapping(data, payload.__class__.__name__)
        return require_mapping(payload, "payload")

    @staticmethod
    def _coerce_channel(channel: Channel | str) -> Channel:
        return coerce_enum(Channel, channel, "channel")

    def _assert_subscription_allowed(
        self, channel: Channel, subscriber: SubscriberRef
    ) -> None:
        policy = CHANNEL_POLICIES[channel]
        role = subscriber.normalized_role()
        if role not in policy.subscriber_roles:
            raise RoutingAccessError(
                f"{role.value!r} cannot subscribe to {channel.value}"
            )
        if role == SubscriberRole.AGENT_RUNTIME:
            self._assert_agent_subscription_allowed(channel, subscriber)

    def _assert_agent_subscription_allowed(
        self, channel: Channel, subscriber: SubscriberRef
    ) -> None:
        if not subscriber.agent_id:
            raise RoutingAccessError("agent_runtime subscriber requires agent_id")
        subscriptions = self._agent_subscriptions.get(subscriber.agent_id)
        if subscriptions is None:
            raise RoutingAccessError(
                f"agent {subscriber.agent_id!r} has no registered permissions"
            )
        required = f"{channel.value}:self" if CHANNEL_POLICIES[channel].agent_self_only else channel.value
        if required not in subscriptions and channel.value not in subscriptions:
            raise RoutingAccessError(
                f"agent {subscriber.agent_id!r} cannot subscribe to {channel.value}"
            )

    def _event_visible_to_subscriber(
        self,
        channel: Channel,
        subscriber: SubscriberRef,
        payload: Mapping[str, Any],
    ) -> bool:
        if subscriber.normalized_role() != SubscriberRole.AGENT_RUNTIME:
            return True
        policy = CHANNEL_POLICIES[channel]
        if policy.agent_self_only:
            return payload.get("agent_id") == subscriber.agent_id
        return True

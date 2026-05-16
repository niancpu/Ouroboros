"""Schemas for REST and WebSocket protocol boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .common import (
    ErrorCode,
    PRIVATE_FIELD_NAMES,
    SCHEMA_VERSION,
    WebVisibility,
    coerce_enum,
    ensure_no_forbidden_keys,
    ensure_schema_version,
    reject_unknown_keys,
    require_int,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    to_plain_data,
)


WS_TOPICS = frozenset({"runtime", "market", "agent", "audit"})
WS_CLIENT_MESSAGE_TYPES = frozenset({"subscribe", "ack", "ping"})
WS_EVENT_TYPES = frozenset(
    {
        "runtime.tick_state",
        "runtime.agent_lifecycle",
        "market.price",
        "market.tape_alert",
        "market.end_of_day",
        "forum.post",
        "agent.account_snapshot",
        "audit.graph",
        "audit.causal_chain",
        "system.error",
    }
)
WEB_API_FORBIDDEN_FIELDS = PRIVATE_FIELD_NAMES | frozenset(
    {
        "ui_audit",
        "order_input",
        "raw_agent_payload",
        "private_memory",
        "lob",
        "future_fact",
    }
)


@dataclass(frozen=True)
class SubscribeMessage:
    type: str
    request_id: str
    topics: list[str]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SubscribeMessage":
        data = require_mapping(data, "SubscribeMessage")
        reject_unknown_keys(data, {"type", "request_id", "topics"}, "SubscribeMessage")
        if data.get("type") != "subscribe":
            raise ValueError("SubscribeMessage type must be subscribe")
        topics = require_str_list(data.get("topics"), "topics")
        unknown = sorted(topic for topic in topics if topic not in WS_TOPICS)
        if unknown:
            raise ValueError(f"unsupported topic(s): {', '.join(unknown)}")
        return cls(
            type="subscribe",
            request_id=require_non_empty_str(data.get("request_id"), "request_id"),
            topics=topics,
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class AckMessage:
    type: str
    request_id: str
    last_seq: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AckMessage":
        data = require_mapping(data, "AckMessage")
        reject_unknown_keys(data, {"type", "request_id", "last_seq"}, "AckMessage")
        if data.get("type") != "ack":
            raise ValueError("AckMessage type must be ack")
        return cls(
            type="ack",
            request_id=require_non_empty_str(data.get("request_id"), "request_id"),
            last_seq=require_int(data.get("last_seq"), "last_seq", minimum=0),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class PingMessage:
    type: str
    request_id: str
    client_time: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PingMessage":
        data = require_mapping(data, "PingMessage")
        reject_unknown_keys(data, {"type", "request_id", "client_time"}, "PingMessage")
        if data.get("type") != "ping":
            raise ValueError("PingMessage type must be ping")
        return cls(
            type="ping",
            request_id=require_non_empty_str(data.get("request_id"), "request_id"),
            client_time=require_non_empty_str(data.get("client_time"), "client_time"),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


def parse_client_message(data: Mapping[str, Any]) -> SubscribeMessage | AckMessage | PingMessage:
    data = require_mapping(data, "client_message")
    msg_type = require_non_empty_str(data.get("type"), "type")
    if msg_type not in WS_CLIENT_MESSAGE_TYPES:
        raise ValueError(f"unsupported WebSocket client message type: {msg_type}")
    if msg_type == "subscribe":
        return SubscribeMessage.from_dict(data)
    if msg_type == "ack":
        return AckMessage.from_dict(data)
    return PingMessage.from_dict(data)


@dataclass(frozen=True)
class WebEventEnvelope:
    schema_version: str
    seq: int
    type: str
    session_id: str
    tick_id: str
    trace_id: str
    server_time: str
    visibility: WebVisibility
    payload: dict[str, Any]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebEventEnvelope":
        data = require_mapping(data, "WebEventEnvelope")
        ensure_schema_version(data)
        reject_unknown_keys(
            data,
            {
                "schema_version",
                "seq",
                "type",
                "session_id",
                "tick_id",
                "trace_id",
                "server_time",
                "visibility",
                "payload",
            },
            "WebEventEnvelope",
        )
        event_type = require_non_empty_str(data.get("type"), "type")
        if event_type not in WS_EVENT_TYPES:
            raise ValueError(f"unsupported WebSocket event type: {event_type}")
        payload = dict(require_mapping(data.get("payload"), "payload"))
        ensure_no_forbidden_keys(payload, WEB_API_FORBIDDEN_FIELDS, "WebEventEnvelope.payload")
        return cls(
            schema_version=SCHEMA_VERSION,
            seq=require_int(data.get("seq"), "seq", minimum=0),
            type=event_type,
            session_id=require_non_empty_str(data.get("session_id"), "session_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            server_time=require_non_empty_str(data.get("server_time"), "server_time"),
            visibility=coerce_enum(WebVisibility, data.get("visibility"), "visibility"),
            payload=payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class ErrorPayload:
    code: ErrorCode
    message: str
    retryable: bool
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ErrorPayload":
        data = require_mapping(data, "ErrorPayload")
        retryable = data.get("retryable")
        if not isinstance(retryable, bool):
            raise ValueError("retryable must be a boolean")
        details = dict(require_mapping(data.get("details", {}), "details"))
        ensure_no_forbidden_keys(details, WEB_API_FORBIDDEN_FIELDS, "ErrorPayload.details")
        return cls(
            code=coerce_enum(ErrorCode, data.get("code"), "code"),
            message=require_non_empty_str(data.get("message"), "message"),
            retryable=retryable,
            details=details,
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class RestSuccessResponse:
    schema_version: str
    request_id: str
    session_id: str
    trace_id: str
    server_time: str
    data: dict[str, Any]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RestSuccessResponse":
        data = require_mapping(data, "RestSuccessResponse")
        ensure_schema_version(data)
        payload = dict(require_mapping(data.get("data"), "data"))
        ensure_no_forbidden_keys(payload, WEB_API_FORBIDDEN_FIELDS, "RestSuccessResponse.data")
        return cls(
            schema_version=SCHEMA_VERSION,
            request_id=require_non_empty_str(data.get("request_id"), "request_id"),
            session_id=require_non_empty_str(data.get("session_id"), "session_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            server_time=require_non_empty_str(data.get("server_time"), "server_time"),
            data=payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class RestErrorResponse:
    schema_version: str
    request_id: str
    trace_id: str
    server_time: str
    error: ErrorPayload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RestErrorResponse":
        data = require_mapping(data, "RestErrorResponse")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            request_id=require_non_empty_str(data.get("request_id"), "request_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            server_time=require_non_empty_str(data.get("server_time"), "server_time"),
            error=ErrorPayload.from_dict(data.get("error")),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


"""Control-plane command and status schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .common import (
    AgentType,
    InternalVisibility,
    LifecycleState,
    RunMode,
    SCHEMA_VERSION,
    SessionStatus,
    TickState,
    coerce_enum,
    ensure_schema_version,
    optional_str,
    reject_unknown_keys,
    require_int,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    to_plain_data,
)


@dataclass(frozen=True)
class CreateSessionCommand:
    schema_version: str
    command_id: str
    scenario_id: str
    symbol: str
    agent_profile_set: str
    start_tick_id: str
    end_tick_id: str
    tick_interval: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CreateSessionCommand":
        data = require_mapping(data, "CreateSessionCommand")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            command_id=require_non_empty_str(data.get("command_id"), "command_id"),
            scenario_id=require_non_empty_str(data.get("scenario_id"), "scenario_id"),
            symbol=require_non_empty_str(data.get("symbol"), "symbol"),
            agent_profile_set=require_non_empty_str(
                data.get("agent_profile_set"), "agent_profile_set"
            ),
            start_tick_id=require_non_empty_str(data.get("start_tick_id"), "start_tick_id"),
            end_tick_id=require_non_empty_str(data.get("end_tick_id"), "end_tick_id"),
            tick_interval=require_non_empty_str(data.get("tick_interval"), "tick_interval"),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class CreateSessionResult:
    schema_version: str
    command_id: str
    session_id: str
    status: SessionStatus
    current_tick_id: str
    agent_count: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CreateSessionResult":
        data = require_mapping(data, "CreateSessionResult")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            command_id=require_non_empty_str(data.get("command_id"), "command_id"),
            session_id=require_non_empty_str(data.get("session_id"), "session_id"),
            status=coerce_enum(SessionStatus, data.get("status"), "status"),
            current_tick_id=require_non_empty_str(data.get("current_tick_id"), "current_tick_id"),
            agent_count=require_int(data.get("agent_count"), "agent_count", minimum=0),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class RunTickCommand:
    schema_version: str
    command_id: str
    session_id: str
    tick_id: str
    trace_id: str
    mode: RunMode

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunTickCommand":
        data = require_mapping(data, "RunTickCommand")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            command_id=require_non_empty_str(data.get("command_id"), "command_id"),
            session_id=require_non_empty_str(data.get("session_id"), "session_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            mode=coerce_enum(RunMode, data.get("mode"), "mode"),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class AgentResults:
    completed: int
    timeout: int
    failed: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentResults":
        data = require_mapping(data, "agent_results")
        return cls(
            completed=require_int(data.get("completed"), "completed", minimum=0),
            timeout=require_int(data.get("timeout"), "timeout", minimum=0),
            failed=require_int(data.get("failed"), "failed", minimum=0),
        )


@dataclass(frozen=True)
class RunTickResult:
    schema_version: str
    command_id: str
    session_id: str
    tick_id: str
    status: str
    next_tick_id: str
    agent_results: AgentResults
    published_event_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunTickResult":
        data = require_mapping(data, "RunTickResult")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            command_id=require_non_empty_str(data.get("command_id"), "command_id"),
            session_id=require_non_empty_str(data.get("session_id"), "session_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            status=require_non_empty_str(data.get("status"), "status"),
            next_tick_id=require_non_empty_str(data.get("next_tick_id"), "next_tick_id"),
            agent_results=AgentResults.from_dict(data.get("agent_results")),
            published_event_ids=require_str_list(
                data.get("published_event_ids", []), "published_event_ids"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class AgentStepCommand:
    schema_version: str
    command_id: str
    session_id: str
    tick_id: str
    trace_id: str
    agent_id: str
    deadline_ms: int
    tick_context_ref: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentStepCommand":
        data = require_mapping(data, "AgentStepCommand")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            command_id=require_non_empty_str(data.get("command_id"), "command_id"),
            session_id=require_non_empty_str(data.get("session_id"), "session_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            deadline_ms=require_int(data.get("deadline_ms"), "deadline_ms", minimum=1),
            tick_context_ref=require_non_empty_str(
                data.get("tick_context_ref"), "tick_context_ref"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class RouteRef:
    target: str
    event_id: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RouteRef":
        data = require_mapping(data, "RouteRef")
        return cls(
            target=require_non_empty_str(data.get("target"), "target"),
            event_id=require_non_empty_str(data.get("event_id"), "event_id"),
        )


@dataclass(frozen=True)
class SplitAgentPayloadResult:
    schema_version: str
    tick_id: str
    trace_id: str
    agent_id: str
    routes: list[RouteRef]
    dropped_fields: list[str]
    validation_status: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SplitAgentPayloadResult":
        data = require_mapping(data, "SplitAgentPayloadResult")
        ensure_schema_version(data)
        routes = data.get("routes", [])
        if not isinstance(routes, list):
            raise ValueError("routes must be a list")
        return cls(
            schema_version=SCHEMA_VERSION,
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            routes=[RouteRef.from_dict(item) for item in routes],
            dropped_fields=require_str_list(data.get("dropped_fields", []), "dropped_fields"),
            validation_status=require_non_empty_str(
                data.get("validation_status"), "validation_status"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class RuntimeTickStateEvent:
    schema_version: str
    event_id: str
    session_id: str
    tick_id: str
    trace_id: str
    producer: str
    visibility: InternalVisibility
    state: TickState
    active_agent_count: int
    completed_agent_count: int
    timeout_agent_count: int
    failed_agent_count: int = 0
    previous_state: TickState | None = None
    can_advance: bool | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RuntimeTickStateEvent":
        data = require_mapping(data, "RuntimeTickStateEvent")
        ensure_schema_version(data)
        reject_unknown_keys(
            data,
            {
                "schema_version",
                "event_id",
                "session_id",
                "tick_id",
                "trace_id",
                "producer",
                "visibility",
                "state",
                "previous_state",
                "active_agent_count",
                "completed_agent_count",
                "timeout_agent_count",
                "failed_agent_count",
                "can_advance",
            },
            "RuntimeTickStateEvent",
        )
        visibility = coerce_enum(InternalVisibility, data.get("visibility"), "visibility")
        if visibility != InternalVisibility.CONTROL_ONLY:
            raise ValueError("RuntimeTickStateEvent visibility must be control_only")
        can_advance = data.get("can_advance")
        if can_advance is not None and not isinstance(can_advance, bool):
            raise ValueError("can_advance must be a boolean")
        return cls(
            schema_version=SCHEMA_VERSION,
            event_id=require_non_empty_str(data.get("event_id"), "event_id"),
            session_id=require_non_empty_str(data.get("session_id"), "session_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            producer=require_non_empty_str(data.get("producer"), "producer"),
            visibility=visibility,
            state=coerce_enum(TickState, data.get("state"), "state"),
            previous_state=(
                coerce_enum(TickState, data["previous_state"], "previous_state")
                if data.get("previous_state") is not None
                else None
            ),
            active_agent_count=require_int(
                data.get("active_agent_count"), "active_agent_count", minimum=0
            ),
            completed_agent_count=require_int(
                data.get("completed_agent_count"), "completed_agent_count", minimum=0
            ),
            timeout_agent_count=require_int(
                data.get("timeout_agent_count"), "timeout_agent_count", minimum=0
            ),
            failed_agent_count=require_int(
                data.get("failed_agent_count", 0), "failed_agent_count", minimum=0
            ),
            can_advance=can_advance,
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class RuntimeAgentLifecycleEvent:
    agent_id: str
    agent_type: AgentType
    lifecycle_state: LifecycleState
    reason_code: str
    public_label: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RuntimeAgentLifecycleEvent":
        data = require_mapping(data, "RuntimeAgentLifecycleEvent")
        return cls(
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            agent_type=coerce_enum(AgentType, data.get("agent_type"), "agent_type"),
            lifecycle_state=coerce_enum(
                LifecycleState, data.get("lifecycle_state"), "lifecycle_state"
            ),
            reason_code=require_non_empty_str(data.get("reason_code"), "reason_code"),
            public_label=require_non_empty_str(data.get("public_label"), "public_label"),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)

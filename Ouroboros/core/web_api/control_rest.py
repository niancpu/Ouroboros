"""Framework-free Control REST boundary adapter.

This module intentionally owns only HTTP-ish request routing, Web API schema
translation, state-conflict checks, and response filtering. Runtime behavior is
delegated to a single control-plane protocol implementation supplied by the
caller.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from Ouroboros.core.schemas.common import (
    ErrorCode,
    RunMode,
    SCHEMA_VERSION,
    SchemaValidationError,
    SessionStatus,
    coerce_enum,
    ensure_no_forbidden_keys,
    reject_unknown_keys,
    require_int,
    require_mapping,
    require_non_empty_str,
)
from Ouroboros.core.schemas.control import CreateSessionCommand, CreateSessionResult
from Ouroboros.core.schemas.web_api import (
    ErrorPayload,
    RestErrorResponse,
    RestSuccessResponse,
    WEB_API_FORBIDDEN_FIELDS,
    WS_EVENT_TYPES,
)


DEFAULT_EVENT_LIMIT = 500
MAX_EVENT_LIMIT = 500

ERROR_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.BAD_REQUEST: 400,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.SESSION_NOT_FOUND: 404,
    ErrorCode.SESSION_STATE_CONFLICT: 409,
    ErrorCode.SCHEMA_VERSION_UNSUPPORTED: 422,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.ORCHESTRATOR_BUSY: 503,
    ErrorCode.SNAPSHOT_REQUIRED: 409,
    ErrorCode.WS_BACKPRESSURE: 429,
    ErrorCode.INTERNAL_ERROR: 500,
}

ERROR_RETRYABLE: dict[ErrorCode, bool] = {
    ErrorCode.BAD_REQUEST: False,
    ErrorCode.UNAUTHORIZED: False,
    ErrorCode.FORBIDDEN: False,
    ErrorCode.SESSION_NOT_FOUND: False,
    ErrorCode.SESSION_STATE_CONFLICT: True,
    ErrorCode.SCHEMA_VERSION_UNSUPPORTED: False,
    ErrorCode.RATE_LIMITED: True,
    ErrorCode.ORCHESTRATOR_BUSY: True,
    ErrorCode.SNAPSHOT_REQUIRED: True,
    ErrorCode.WS_BACKPRESSURE: True,
    ErrorCode.INTERNAL_ERROR: True,
}

CONTROL_ACTION_ALLOWED_STATES: dict[str, frozenset[SessionStatus]] = {
    "start": frozenset({SessionStatus.CREATED, SessionStatus.PAUSED}),
    "pause": frozenset({SessionStatus.RUNNING}),
    "step": frozenset({SessionStatus.CREATED, SessionStatus.PAUSED}),
    "stop": frozenset(
        {SessionStatus.CREATED, SessionStatus.RUNNING, SessionStatus.PAUSED}
    ),
}

_FORBIDDEN_FIELD_NAMES_LOWER = frozenset(
    field_name.lower() for field_name in WEB_API_FORBIDDEN_FIELDS
) | frozenset(
    {
        "agent_private_channel",
        "internal_channel_payload",
        "thought_summary",
    }
)


@dataclass(frozen=True)
class RestHttpRequest:
    """In-process HTTP request shape used by the gateway adapter."""

    method: str
    path: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: Mapping[str, Any] | None = None
    query: Mapping[str, str | int | list[str] | tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class RestHttpResponse:
    """Framework-neutral response shape returned by the adapter."""

    status_code: int
    body: dict[str, Any]
    headers: dict[str, str] = field(
        default_factory=lambda: {"Content-Type": "application/json"}
    )


class ControlRestError(Exception):
    """Error raised by the Web API boundary or a control-plane implementation."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = ERROR_RETRYABLE[code] if retryable is None else retryable
        self.details = dict(details or {})


@runtime_checkable
class ControlPlaneProtocol(Protocol):
    """Single protocol Web API may call for control-plane operations."""

    def create_session(self, command: CreateSessionCommand) -> CreateSessionResult | Mapping[str, Any]:
        """Create a control-plane session without advancing ticks."""

    def get_session(
        self, session_id: str, *, request_id: str, trace_id: str
    ) -> Mapping[str, Any]:
        """Return frontend-safe session status data."""

    def start_session(
        self, session_id: str, *, mode: RunMode, command_id: str, trace_id: str
    ) -> Mapping[str, Any]:
        """Switch a created or paused session into continuous running."""

    def pause_session(
        self, session_id: str, *, reason: str, command_id: str, trace_id: str
    ) -> Mapping[str, Any]:
        """Request pause at the next safe point."""

    def step_session(
        self, session_id: str, *, ticks: int, command_id: str, trace_id: str
    ) -> Mapping[str, Any]:
        """Schedule a single tick from a created or paused session."""

    def get_frontend_snapshot(
        self, session_id: str, *, request_id: str, trace_id: str
    ) -> Mapping[str, Any]:
        """Return only frontend-safe snapshot data."""

    def get_frontend_events(
        self,
        session_id: str,
        *,
        from_seq: int,
        limit: int,
        request_id: str,
        trace_id: str,
    ) -> Mapping[str, Any]:
        """Return only frontend-safe replay events."""

    def stop_session(
        self, session_id: str, *, reason: str, command_id: str, trace_id: str
    ) -> Mapping[str, Any]:
        """Request stop at the next safe point."""


class ControlRestApi:
    """REST route adapter for session control endpoints."""

    def __init__(
        self,
        control_plane: ControlPlaneProtocol,
        *,
        base_path: str = "/api/v1",
        max_event_limit: int = MAX_EVENT_LIMIT,
    ) -> None:
        self._control_plane = control_plane
        self._base_path = _normalize_path(base_path)
        self._max_event_limit = max_event_limit

    def handle(self, request: RestHttpRequest) -> RestHttpResponse:
        request_id = _optional_request_id(request.headers) or "missing_request_id"
        trace_id = _trace_id(request.headers)
        try:
            request_id = _request_id(request.headers)
            return self._handle_checked(request, request_id=request_id, trace_id=trace_id)
        except ControlRestError as exc:
            return self._error_response(
                request_id=request_id,
                trace_id=trace_id,
                error=exc,
            )
        except SchemaValidationError as exc:
            code = (
                ErrorCode.SCHEMA_VERSION_UNSUPPORTED
                if "schema_version" in str(exc)
                else ErrorCode.BAD_REQUEST
            )
            return self._error_response(
                request_id=request_id,
                trace_id=trace_id,
                error=ControlRestError(code, str(exc)),
            )
        except ValueError as exc:
            return self._error_response(
                request_id=request_id,
                trace_id=trace_id,
                error=ControlRestError(ErrorCode.BAD_REQUEST, str(exc)),
            )
        except Exception:
            return self._error_response(
                request_id=request_id,
                trace_id=trace_id,
                error=ControlRestError(
                    ErrorCode.INTERNAL_ERROR,
                    "internal server error",
                ),
            )

    def _handle_checked(
        self, request: RestHttpRequest, *, request_id: str, trace_id: str
    ) -> RestHttpResponse:
        _require_json_content_type(request)
        method = request.method.upper()
        segments = self._route_segments(request.path)

        if method == "POST" and segments == ["sessions"]:
            return self._create_session(request, request_id=request_id, trace_id=trace_id)

        if len(segments) < 2 or segments[0] != "sessions":
            raise ControlRestError(ErrorCode.BAD_REQUEST, "unsupported Control REST route")

        session_id = require_non_empty_str(segments[1], "session_id")
        tail = segments[2:]

        if method == "GET" and not tail:
            return self._get_session(session_id, request_id=request_id, trace_id=trace_id)
        if method == "POST" and tail == ["start"]:
            return self._start_session(request, session_id, request_id=request_id, trace_id=trace_id)
        if method == "POST" and tail == ["pause"]:
            return self._pause_session(request, session_id, request_id=request_id, trace_id=trace_id)
        if method == "POST" and tail == ["step"]:
            return self._step_session(request, session_id, request_id=request_id, trace_id=trace_id)
        if method == "GET" and tail == ["snapshot"]:
            return self._snapshot(session_id, request_id=request_id, trace_id=trace_id)
        if method == "GET" and tail == ["events"]:
            return self._events(request, session_id, request_id=request_id, trace_id=trace_id)
        if method == "POST" and tail == ["stop"]:
            return self._stop_session(request, session_id, request_id=request_id, trace_id=trace_id)

        raise ControlRestError(ErrorCode.BAD_REQUEST, "unsupported Control REST route")

    def _create_session(
        self, request: RestHttpRequest, *, request_id: str, trace_id: str
    ) -> RestHttpResponse:
        payload = _body(request)
        reject_unknown_keys(
            payload,
            {
                "scenario_id",
                "symbol",
                "agent_profile_set",
                "start_tick_id",
                "end_tick_id",
                "tick_interval",
            },
            "CreateSessionRequest",
        )
        command = CreateSessionCommand.from_dict(
            {
                "schema_version": SCHEMA_VERSION,
                "command_id": _command_id(request_id, "create"),
                **dict(payload),
            }
        )
        result = self._control_plane.create_session(command)
        result_data = _mapping_from_result(result)
        data = {
            "session_id": require_non_empty_str(result_data.get("session_id"), "session_id"),
            "status": _session_status_value(result_data.get("status")),
            "current_tick_id": require_non_empty_str(
                result_data.get("current_tick_id"), "current_tick_id"
            ),
            "websocket_url": f"{self._base_path}/sessions/{result_data['session_id']}/ws",
        }
        return self._success_response(
            request_id=request_id,
            trace_id=trace_id,
            session_id=data["session_id"],
            data=data,
        )

    def _get_session(
        self, session_id: str, *, request_id: str, trace_id: str
    ) -> RestHttpResponse:
        data = self._session_data(session_id, request_id=request_id, trace_id=trace_id)
        return self._success_response(
            request_id=request_id,
            trace_id=trace_id,
            session_id=session_id,
            data=data,
        )

    def _start_session(
        self,
        request: RestHttpRequest,
        session_id: str,
        *,
        request_id: str,
        trace_id: str,
    ) -> RestHttpResponse:
        payload = _body(request)
        reject_unknown_keys(payload, {"mode"}, "StartSessionRequest")
        mode = coerce_enum(RunMode, payload.get("mode", RunMode.CONTINUOUS), "mode")
        if mode != RunMode.CONTINUOUS:
            raise ControlRestError(ErrorCode.BAD_REQUEST, "start mode must be continuous")
        self._ensure_allowed_state(
            "start", session_id, request_id=request_id, trace_id=trace_id
        )
        data = self._control_plane.start_session(
            session_id,
            mode=mode,
            command_id=_command_id(request_id, "start"),
            trace_id=trace_id,
        )
        response_data = _response_mapping(data)
        response_data.setdefault("session_id", session_id)
        response_data.setdefault("status", SessionStatus.RUNNING.value)
        response_data.setdefault("accepted", True)
        return self._success_response(
            request_id=request_id,
            trace_id=trace_id,
            session_id=session_id,
            data=response_data,
        )

    def _pause_session(
        self,
        request: RestHttpRequest,
        session_id: str,
        *,
        request_id: str,
        trace_id: str,
    ) -> RestHttpResponse:
        payload = _body(request)
        reject_unknown_keys(payload, {"reason"}, "PauseSessionRequest")
        reason = _optional_reason(payload, "operator_pause")
        self._ensure_allowed_state(
            "pause", session_id, request_id=request_id, trace_id=trace_id
        )
        data = self._control_plane.pause_session(
            session_id,
            reason=reason,
            command_id=_command_id(request_id, "pause"),
            trace_id=trace_id,
        )
        response_data = _response_mapping(data)
        response_data.setdefault("session_id", session_id)
        response_data.setdefault("status", SessionStatus.PAUSED.value)
        response_data.setdefault("pause_after_state", "COMMIT_TICK")
        return self._success_response(
            request_id=request_id,
            trace_id=trace_id,
            session_id=session_id,
            data=response_data,
        )

    def _step_session(
        self,
        request: RestHttpRequest,
        session_id: str,
        *,
        request_id: str,
        trace_id: str,
    ) -> RestHttpResponse:
        payload = _body(request)
        reject_unknown_keys(payload, {"ticks"}, "StepSessionRequest")
        ticks = require_int(payload.get("ticks", 1), "ticks", minimum=1)
        if ticks != 1:
            raise ControlRestError(ErrorCode.BAD_REQUEST, "ticks must be 1")
        self._ensure_allowed_state(
            "step", session_id, request_id=request_id, trace_id=trace_id
        )
        data = self._control_plane.step_session(
            session_id,
            ticks=ticks,
            command_id=_command_id(request_id, "step"),
            trace_id=trace_id,
        )
        response_data = _response_mapping(data)
        response_data.setdefault("session_id", session_id)
        response_data.setdefault("status", SessionStatus.RUNNING.value)
        response_data.setdefault("scheduled_ticks", ticks)
        return self._success_response(
            request_id=request_id,
            trace_id=trace_id,
            session_id=session_id,
            data=response_data,
        )

    def _snapshot(
        self, session_id: str, *, request_id: str, trace_id: str
    ) -> RestHttpResponse:
        self._session_data(session_id, request_id=request_id, trace_id=trace_id)
        data = self._control_plane.get_frontend_snapshot(
            session_id,
            request_id=request_id,
            trace_id=trace_id,
        )
        response_data = _response_mapping(data)
        response_data.setdefault("session_id", session_id)
        response_data.setdefault("status", SessionStatus.COMPLETED.value)
        return self._success_response(
            request_id=request_id,
            trace_id=trace_id,
            session_id=session_id,
            data=response_data,
        )

    def _events(
        self,
        request: RestHttpRequest,
        session_id: str,
        *,
        request_id: str,
        trace_id: str,
    ) -> RestHttpResponse:
        self._session_data(session_id, request_id=request_id, trace_id=trace_id)
        from_seq = _query_int(request.query, "from_seq", default=0, minimum=0)
        limit = _query_int(
            request.query,
            "limit",
            default=min(DEFAULT_EVENT_LIMIT, self._max_event_limit),
            minimum=1,
        )
        limit = min(limit, self._max_event_limit)
        data = self._control_plane.get_frontend_events(
            session_id,
            from_seq=from_seq,
            limit=limit,
            request_id=request_id,
            trace_id=trace_id,
        )
        response_data = _response_mapping(data)
        response_data["events"] = _filter_frontend_events(
            response_data.get("events", [])
        )
        return self._success_response(
            request_id=request_id,
            trace_id=trace_id,
            session_id=session_id,
            data=response_data,
        )

    def _stop_session(
        self,
        request: RestHttpRequest,
        session_id: str,
        *,
        request_id: str,
        trace_id: str,
    ) -> RestHttpResponse:
        payload = _body(request)
        reject_unknown_keys(payload, {"reason"}, "StopSessionRequest")
        reason = _optional_reason(payload, "operator_stop")
        self._ensure_allowed_state(
            "stop", session_id, request_id=request_id, trace_id=trace_id
        )
        data = self._control_plane.stop_session(
            session_id,
            reason=reason,
            command_id=_command_id(request_id, "stop"),
            trace_id=trace_id,
        )
        response_data = _response_mapping(data)
        response_data.setdefault("session_id", session_id)
        if "completion_reason" not in response_data and "reason" in response_data:
            response_data["completion_reason"] = response_data.pop("reason")
        response_data.setdefault("completion_reason", reason)
        return self._success_response(
            request_id=request_id,
            trace_id=trace_id,
            session_id=session_id,
            data=response_data,
        )

    def _ensure_allowed_state(
        self, action: str, session_id: str, *, request_id: str, trace_id: str
    ) -> None:
        data = self._session_data(session_id, request_id=request_id, trace_id=trace_id)
        status = coerce_enum(SessionStatus, data.get("status"), "status")
        allowed = CONTROL_ACTION_ALLOWED_STATES[action]
        if status not in allowed:
            allowed_values = ", ".join(sorted(item.value for item in allowed))
            raise ControlRestError(
                ErrorCode.SESSION_STATE_CONFLICT,
                f"{action} is not allowed while session is {status.value}",
                details={
                    "status": status.value,
                    "allowed_statuses": sorted(item.value for item in allowed),
                },
            )

    def _session_data(
        self, session_id: str, *, request_id: str, trace_id: str
    ) -> dict[str, Any]:
        try:
            return _response_mapping(
                self._control_plane.get_session(
                    session_id,
                    request_id=request_id,
                    trace_id=trace_id,
                )
            )
        except ControlRestError:
            raise
        except KeyError as exc:
            raise ControlRestError(
                ErrorCode.SESSION_NOT_FOUND,
                "session does not exist",
            ) from exc

    def _success_response(
        self,
        *,
        request_id: str,
        trace_id: str,
        session_id: str,
        data: Mapping[str, Any],
    ) -> RestHttpResponse:
        safe_data = filter_web_api_payload(dict(data))
        response = RestSuccessResponse(
            schema_version=SCHEMA_VERSION,
            request_id=request_id,
            session_id=session_id,
            trace_id=trace_id,
            server_time=_server_time(),
            data=safe_data,
        )
        return RestHttpResponse(status_code=200, body=response.to_dict())

    def _error_response(
        self, *, request_id: str, trace_id: str, error: ControlRestError
    ) -> RestHttpResponse:
        details = filter_web_api_payload(dict(error.details))
        response = RestErrorResponse(
            schema_version=SCHEMA_VERSION,
            request_id=request_id,
            trace_id=trace_id,
            server_time=_server_time(),
            error=ErrorPayload(
                code=error.code,
                message=error.message,
                retryable=error.retryable,
                details=details,
            ),
        )
        return RestHttpResponse(status_code=ERROR_HTTP_STATUS[error.code], body=response.to_dict())

    def _route_segments(self, path: str) -> list[str]:
        normalized = _normalize_path(path)
        if normalized == self._base_path:
            return []
        prefix = f"{self._base_path}/"
        if not normalized.startswith(prefix):
            raise ControlRestError(ErrorCode.BAD_REQUEST, "unsupported Control REST base path")
        return [segment for segment in normalized[len(prefix) :].split("/") if segment]


def filter_web_api_payload(value: Any) -> Any:
    """Drop fields forbidden by Web API visibility rules from nested data."""

    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_FIELD_NAMES_LOWER:
                continue
            result[key] = filter_web_api_payload(item)
        return result
    if isinstance(value, list):
        return [filter_web_api_payload(item) for item in value]
    if isinstance(value, tuple):
        return [filter_web_api_payload(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    return value


def _filter_frontend_events(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        raise SchemaValidationError("events must be a list")
    safe_events: list[dict[str, Any]] = []
    for event in events:
        data = filter_web_api_payload(event)
        if not isinstance(data, Mapping):
            continue
        event_type = data.get("type")
        if event_type not in WS_EVENT_TYPES:
            continue
        safe_events.append(dict(data))
    return safe_events


def _response_mapping(value: Mapping[str, Any] | Any) -> dict[str, Any]:
    data = _mapping_from_result(value)
    safe_data = filter_web_api_payload(data)
    ensure_no_forbidden_keys(safe_data, WEB_API_FORBIDDEN_FIELDS, "Control REST response")
    return safe_data


def _mapping_from_result(value: Mapping[str, Any] | Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    data = require_mapping(value, "control_plane_result")
    return dict(data)


def _optional_request_id(headers: Mapping[str, str]) -> str | None:
    request_id = _header(headers, "X-Request-Id")
    if request_id is None or not request_id.strip():
        return None
    return request_id


def _request_id(headers: Mapping[str, str]) -> str:
    request_id = _header(headers, "X-Request-Id")
    if request_id is None:
        raise ControlRestError(ErrorCode.BAD_REQUEST, "X-Request-Id header is required")
    return require_non_empty_str(request_id, "X-Request-Id")


def _trace_id(headers: Mapping[str, str]) -> str:
    return _header(headers, "X-Trace-Id") or f"trace_{uuid4().hex}"


def _header(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def _require_json_content_type(request: RestHttpRequest) -> None:
    if request.method.upper() == "GET":
        return
    content_type = _header(request.headers, "Content-Type")
    if content_type is None or content_type.split(";", 1)[0].strip().lower() != "application/json":
        raise ControlRestError(
            ErrorCode.BAD_REQUEST,
            "Content-Type must be application/json",
        )


def _body(request: RestHttpRequest) -> Mapping[str, Any]:
    if request.body is None:
        return {}
    return require_mapping(request.body, "request body")


def _optional_reason(payload: Mapping[str, Any], default: str) -> str:
    reason = payload.get("reason", default)
    return require_non_empty_str(reason, "reason")


def _query_int(
    query: Mapping[str, str | int | list[str] | tuple[str, ...]],
    name: str,
    *,
    default: int,
    minimum: int,
) -> int:
    raw = query.get(name, default)
    if isinstance(raw, (list, tuple)):
        if len(raw) != 1:
            raise SchemaValidationError(f"{name} must appear once")
        raw = raw[0]
    if isinstance(raw, str):
        if not raw.strip():
            raise SchemaValidationError(f"{name} must be an integer")
        try:
            raw = int(raw)
        except ValueError as exc:
            raise SchemaValidationError(f"{name} must be an integer") from exc
    return require_int(raw, name, minimum=minimum)


def _command_id(request_id: str, action: str) -> str:
    return f"cmd_{action}_{request_id}"


def _session_status_value(value: Any) -> str:
    return coerce_enum(SessionStatus, value, "status").value


def _server_time() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise ControlRestError(ErrorCode.BAD_REQUEST, "path must be non-empty")
    normalized = "/" + path.split("?", 1)[0].strip().strip("/")
    return normalized if normalized != "/" else "/"

"""Framework-free realtime WebSocket boundary adapter.

The adapter owns session/client subscription state, ack tracking, replay
buffers, and Web API visibility filtering. It intentionally does not implement
or depend on an actual WebSocket server.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from Ouroboros.core.schemas.common import (
    ErrorCode,
    SCHEMA_VERSION,
    SchemaValidationError,
    WebVisibility,
    ensure_no_forbidden_keys,
    require_int,
    require_mapping,
    require_non_empty_str,
)
from Ouroboros.core.schemas.web_api import (
    ErrorPayload,
    PingMessage,
    SubscribeMessage,
    WEB_API_FORBIDDEN_FIELDS,
    WS_EVENT_TYPES,
    WebEventEnvelope,
    parse_client_message,
)
from Ouroboros.core.web_api.control_rest import (
    ERROR_RETRYABLE,
    ControlRestError,
    filter_web_api_payload,
)


EVENT_TOPIC_BY_TYPE: dict[str, str] = {
    "runtime.tick_state": "runtime",
    "runtime.agent_lifecycle": "runtime",
    "market.price": "market",
    "market.tape_alert": "market",
    "market.end_of_day": "market",
    "forum.post": "market",
    "agent.account_snapshot": "agent",
    "audit.graph": "audit",
    "audit.causal_chain": "audit",
    "system.error": "runtime",
}

DEFAULT_REPLAY_BUFFER_SIZE = 500


@dataclass(frozen=True)
class FrontendWsMessage:
    """Framework-neutral message emitted by the realtime gateway."""

    kind: str
    body: dict[str, Any]


@dataclass(frozen=True)
class FrontendConnectionState:
    """Session/client state tracked by the realtime gateway."""

    session_id: str
    client_id: str
    subscribed_topics: frozenset[str] = frozenset()
    last_ack_seq: int = 0
    replay_from_seq: int | None = None


@dataclass
class _SessionState:
    next_seq: int = 1
    events: deque[WebEventEnvelope] = field(default_factory=deque)
    clients: dict[str, FrontendConnectionState] = field(default_factory=dict)


class FrontendRealtimeGateway:
    """In-process adapter for the documented frontend realtime protocol."""

    def __init__(self, *, replay_buffer_size: int = DEFAULT_REPLAY_BUFFER_SIZE) -> None:
        if replay_buffer_size < 1:
            raise ValueError("replay_buffer_size must be >= 1")
        self._replay_buffer_size = replay_buffer_size
        self._sessions: dict[str, _SessionState] = {}

    def connect(
        self,
        session_id: str,
        client_id: str,
        *,
        from_seq: int | None = None,
    ) -> list[FrontendWsMessage]:
        """Register a frontend connection and optionally prepare replay."""

        session_id = require_non_empty_str(session_id, "session_id")
        client_id = require_non_empty_str(client_id, "client_id")
        replay_from_seq = None
        if from_seq is not None:
            replay_from_seq = require_int(from_seq, "from_seq", minimum=0)
            self._ensure_replay_available(session_id, replay_from_seq)
        state = self._session(session_id)
        current = state.clients.get(client_id)
        state.clients[client_id] = FrontendConnectionState(
            session_id=session_id,
            client_id=client_id,
            subscribed_topics=current.subscribed_topics if current else frozenset(),
            last_ack_seq=current.last_ack_seq if current else 0,
            replay_from_seq=replay_from_seq,
        )
        return []

    def disconnect(self, session_id: str, client_id: str) -> None:
        """Forget a frontend connection without touching replay history."""

        session = self._sessions.get(session_id)
        if session is not None:
            session.clients.pop(client_id, None)

    def handle_client_message(
        self, session_id: str, client_id: str, message: Mapping[str, Any]
    ) -> list[FrontendWsMessage]:
        """Handle a subscribe/ack/ping message from the frontend."""

        request_id = _message_request_id(message)
        try:
            parsed = parse_client_message(message)
            state = self._require_client(session_id, client_id)
            if isinstance(parsed, SubscribeMessage):
                return self._subscribe(state, parsed)
            if isinstance(parsed, PingMessage):
                return [self._control_message("pong", request_id=parsed.request_id, data=parsed.to_dict())]
            return self._ack(state, parsed.last_seq, request_id=parsed.request_id)
        except ControlRestError as exc:
            return [self._error_message(request_id=request_id, error=exc)]
        except (SchemaValidationError, ValueError) as exc:
            return [
                self._error_message(
                    request_id=request_id,
                    error=ControlRestError(ErrorCode.BAD_REQUEST, str(exc)),
                )
            ]

    def publish_event(
        self, session_id: str, event: Mapping[str, Any] | WebEventEnvelope
    ) -> dict[str, list[FrontendWsMessage]]:
        """Validate, filter, buffer, and fan out one frontend-visible event."""

        try:
            envelope = self._frontend_event(session_id, event)
        except (SchemaValidationError, ValueError) as exc:
            raise ControlRestError(ErrorCode.BAD_REQUEST, str(exc)) from exc

        state = self._session(envelope.session_id)
        if envelope.seq >= state.next_seq:
            state.next_seq = envelope.seq + 1
        state.events.append(envelope)
        while len(state.events) > self._replay_buffer_size:
            state.events.popleft()

        topic = EVENT_TOPIC_BY_TYPE[envelope.type]
        outbound: dict[str, list[FrontendWsMessage]] = {}
        for client_id, client in state.clients.items():
            if topic in client.subscribed_topics:
                outbound[client_id] = [self._event_message(envelope)]
        return outbound

    def replay(
        self, session_id: str, client_id: str, *, from_seq: int | None = None
    ) -> list[FrontendWsMessage]:
        """Return buffered events after from_seq for the client's subscriptions."""

        client = self._require_client(session_id, client_id)
        start_seq = client.replay_from_seq if from_seq is None else from_seq
        if start_seq is None:
            start_seq = client.last_ack_seq
        start_seq = require_int(start_seq, "from_seq", minimum=0)
        self._ensure_replay_available(session_id, start_seq)
        session = self._session(session_id)
        topics = client.subscribed_topics
        return [
            self._event_message(event)
            for event in session.events
            if event.seq > start_seq and EVENT_TOPIC_BY_TYPE[event.type] in topics
        ]

    def connection_state(self, session_id: str, client_id: str) -> FrontendConnectionState:
        """Return a snapshot of tracked state for deterministic tests/adapters."""

        return self._require_client(session_id, client_id)

    def _subscribe(
        self, client: FrontendConnectionState, message: SubscribeMessage
    ) -> list[FrontendWsMessage]:
        session = self._session(client.session_id)
        updated = FrontendConnectionState(
            session_id=client.session_id,
            client_id=client.client_id,
            subscribed_topics=frozenset(message.topics),
            last_ack_seq=client.last_ack_seq,
            replay_from_seq=client.replay_from_seq,
        )
        session.clients[client.client_id] = updated
        replay_messages = self.replay(client.session_id, client.client_id)
        subscribed = self._control_message(
            "subscribed",
            request_id=message.request_id,
            data={"topics": sorted(updated.subscribed_topics)},
        )
        return [subscribed, *replay_messages]

    def _ack(
        self, client: FrontendConnectionState, last_seq: int, *, request_id: str
    ) -> list[FrontendWsMessage]:
        session = self._session(client.session_id)
        updated = FrontendConnectionState(
            session_id=client.session_id,
            client_id=client.client_id,
            subscribed_topics=client.subscribed_topics,
            last_ack_seq=last_seq,
            replay_from_seq=client.replay_from_seq,
        )
        session.clients[client.client_id] = updated
        return [
            self._control_message(
                "ack",
                request_id=request_id,
                data={"last_seq": last_seq},
            )
        ]

    def _frontend_event(
        self, session_id: str, event: Mapping[str, Any] | WebEventEnvelope
    ) -> WebEventEnvelope:
        if isinstance(event, WebEventEnvelope):
            data = event.to_dict()
        else:
            data = dict(require_mapping(event, "event"))
        data = filter_web_api_payload(data)
        data["schema_version"] = SCHEMA_VERSION
        data["session_id"] = require_non_empty_str(data.get("session_id", session_id), "session_id")
        if data["session_id"] != session_id:
            raise SchemaValidationError("event session_id must match publish session_id")
        event_type = require_non_empty_str(data.get("type"), "type")
        if event_type not in WS_EVENT_TYPES:
            raise SchemaValidationError(f"unsupported WebSocket event type: {event_type}")
        if event_type not in EVENT_TOPIC_BY_TYPE:
            raise SchemaValidationError(f"unsupported WebSocket event topic for type: {event_type}")
        data.setdefault("seq", self._session(session_id).next_seq)
        data.setdefault("tick_id", "system")
        data.setdefault("trace_id", "trace_ws")
        data.setdefault("server_time", _server_time())
        data.setdefault("visibility", _default_visibility(event_type).value)
        payload = dict(require_mapping(data.get("payload", {}), "payload"))
        payload = filter_web_api_payload(payload)
        ensure_no_forbidden_keys(payload, WEB_API_FORBIDDEN_FIELDS, "WebEventEnvelope.payload")
        data["payload"] = payload
        return WebEventEnvelope.from_dict(data)

    def _ensure_replay_available(self, session_id: str, from_seq: int) -> None:
        session = self._session(session_id)
        if not session.events:
            return
        oldest_seq = session.events[0].seq
        if from_seq < oldest_seq - 1:
            raise ControlRestError(
                ErrorCode.SNAPSHOT_REQUIRED,
                "replay buffer no longer contains requested from_seq",
                details={"from_seq": from_seq, "oldest_seq": oldest_seq},
            )

    def _require_client(self, session_id: str, client_id: str) -> FrontendConnectionState:
        session_id = require_non_empty_str(session_id, "session_id")
        client_id = require_non_empty_str(client_id, "client_id")
        session = self._session(session_id)
        try:
            return session.clients[client_id]
        except KeyError as exc:
            raise ControlRestError(
                ErrorCode.BAD_REQUEST,
                "client is not connected",
                details={"client_id": client_id},
            ) from exc

    def _session(self, session_id: str) -> _SessionState:
        return self._sessions.setdefault(session_id, _SessionState())

    def _event_message(self, envelope: WebEventEnvelope) -> FrontendWsMessage:
        return FrontendWsMessage(kind="event", body=envelope.to_dict())

    def _control_message(
        self, kind: str, *, request_id: str, data: Mapping[str, Any]
    ) -> FrontendWsMessage:
        return FrontendWsMessage(
            kind=kind,
            body={
                "schema_version": SCHEMA_VERSION,
                "request_id": request_id,
                "server_time": _server_time(),
                "data": filter_web_api_payload(dict(data)),
            },
        )

    def _error_message(self, *, request_id: str, error: ControlRestError) -> FrontendWsMessage:
        payload = ErrorPayload(
            code=error.code,
            message=error.message,
            retryable=ERROR_RETRYABLE[error.code] if error.retryable is None else error.retryable,
            details=filter_web_api_payload(dict(error.details)),
        )
        return FrontendWsMessage(
            kind="error",
            body={
                "schema_version": SCHEMA_VERSION,
                "request_id": request_id,
                "server_time": _server_time(),
                "error": payload.to_dict(),
            },
        )


def topic_for_event_type(event_type: str) -> str:
    """Return the documented frontend topic for a WebSocket event type."""

    try:
        return EVENT_TOPIC_BY_TYPE[event_type]
    except KeyError as exc:
        raise SchemaValidationError(f"unsupported WebSocket event type: {event_type}") from exc


def _message_request_id(message: Mapping[str, Any]) -> str:
    if not isinstance(message, Mapping):
        return "missing_request_id"
    value = message.get("request_id")
    if isinstance(value, str) and value.strip():
        return value
    return "missing_request_id"


def _default_visibility(event_type: str) -> WebVisibility:
    if event_type in {"audit.graph", "audit.causal_chain"}:
        return WebVisibility.FRONTEND_ONLY
    if event_type == "agent.account_snapshot":
        return WebVisibility.AGENT_PRIVATE_SNAPSHOT
    if event_type.startswith("runtime.") or event_type == "system.error":
        return WebVisibility.CONTROL_ONLY_VIEW
    return WebVisibility.PUBLIC


def _server_time() -> str:
    return datetime.now(UTC).isoformat()


def buffered_events_for_topics(
    events: Iterable[WebEventEnvelope], topics: Iterable[str], *, from_seq: int
) -> list[WebEventEnvelope]:
    """Small pure helper for adapters/tests that need deterministic replay filtering."""

    topic_set = frozenset(topics)
    start_seq = require_int(from_seq, "from_seq", minimum=0)
    return [
        event
        for event in events
        if event.seq > start_seq and EVENT_TOPIC_BY_TYPE[event.type] in topic_set
    ]

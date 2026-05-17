from __future__ import annotations

import asyncio
import inspect
import json
import unittest
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from Ouroboros.core.schemas import (
    ErrorCode,
    RestErrorResponse,
    RestSuccessResponse,
    SchemaValidationError,
)

try:
    from Ouroboros.core.web_api.control_rest import ControlRestApi, RestHttpRequest
except ModuleNotFoundError as exc:
    if exc.name not in {
        "Ouroboros.core.web_api",
        "Ouroboros.core.web_api.control_rest",
    }:
        raise
    try:
        from Ouroboros.web_api.control_rest import ControlRestApi, RestHttpRequest
    except ModuleNotFoundError as fallback_exc:
        if fallback_exc.name not in {"Ouroboros.web_api", "Ouroboros.web_api.control_rest"}:
            raise
        ControlRestApi = None  # type: ignore[assignment]
        RestHttpRequest = None  # type: ignore[assignment]


MAX_EVENTS_LIMIT = 500


class FakeControlPlaneError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int,
        retryable: bool,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retryable = retryable
        self.details = dict(details or {})


class ForbiddenLayer3:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"REST API must not access Layer 3 directly: {name}")


def _plain(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    return value


def _request_payload(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> dict[str, Any]:
    if args:
        value = _plain(args[0])
        if isinstance(value, Mapping):
            return dict(value)
    for key in ("request", "payload", "command", "body"):
        value = _plain(kwargs.get(key))
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _session_id(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> str:
    if args and isinstance(args[0], str):
        return args[0]
    value = kwargs.get("session_id")
    if isinstance(value, str):
        return value
    payload = _request_payload(args, kwargs)
    value = payload.get("session_id")
    if isinstance(value, str):
        return value
    raise AssertionError("orchestrator call did not include session_id")


class FakeMetaOrchestrator:
    def __init__(self, *, initial_status: str = "created") -> None:
        self.calls: list[dict[str, Any]] = []
        self._layer3 = ForbiddenLayer3()
        self.sessions: dict[str, dict[str, Any]] = {
            "sim_001": self._session("sim_001", initial_status)
        }

    @property
    def layer3(self) -> ForbiddenLayer3:
        raise AssertionError("REST API must not access orchestrator.layer3")

    @property
    def clearing_house(self) -> ForbiddenLayer3:
        raise AssertionError("REST API must not access orchestrator.clearing_house")

    @property
    def matching_engine(self) -> ForbiddenLayer3:
        raise AssertionError("REST API must not access orchestrator.matching_engine")

    def create_session(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = _request_payload(args, kwargs)
        self.calls.append({"method": "create_session", "payload": payload})
        session = self._session(
            "sim_created",
            "created",
            current_tick_id=payload.get("start_tick_id", "2024-01-02T09:30:00+08:00"),
        )
        self.sessions[session["session_id"]] = session
        return {
            "session_id": session["session_id"],
            "status": "created",
            "current_tick_id": session["current_tick_id"],
            "websocket_url": f"/api/v1/sessions/{session['session_id']}/ws",
        }

    def get_session(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        session_id = _session_id(args, kwargs)
        self.calls.append({"method": "get_session", "session_id": session_id})
        return dict(self._require_session(session_id))

    def start_session(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        session_id = _session_id(args, kwargs)
        payload = _request_payload(args[1:], kwargs) if len(args) > 1 else _request_payload(args, kwargs)
        self.calls.append({"method": "start_session", "session_id": session_id, "payload": payload})
        session = self._require_session(session_id)
        self._require_status(session, {"created", "paused"}, "start")
        session["status"] = "running"
        return {"session_id": session_id, "status": "running", "accepted": True}

    start = start_session

    def pause_session(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        session_id = _session_id(args, kwargs)
        self.calls.append({"method": "pause_session", "session_id": session_id})
        session = self._require_session(session_id)
        self._require_status(session, {"running"}, "pause")
        session["status"] = "paused"
        return {
            "session_id": session_id,
            "status": "paused",
            "pause_after_state": "COMMIT_TICK",
        }

    pause = pause_session

    def step_session(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        session_id = _session_id(args, kwargs)
        payload = _request_payload(args[1:], kwargs) if len(args) > 1 else _request_payload(args, kwargs)
        self.calls.append({"method": "step_session", "session_id": session_id, "payload": payload})
        session = self._require_session(session_id)
        self._require_status(session, {"created", "paused"}, "step")
        ticks = int(payload.get("ticks", 1))
        if ticks != 1:
            raise FakeControlPlaneError(
                ErrorCode.BAD_REQUEST.value,
                "ticks must be 1",
                http_status=400,
                retryable=False,
            )
        session["status"] = "running"
        return {"session_id": session_id, "status": "running", "scheduled_ticks": 1}

    step = step_session

    def get_frontend_snapshot(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        session_id = _session_id(args, kwargs)
        self.calls.append({"method": "get_frontend_snapshot", "session_id": session_id})
        self._require_session(session_id)
        return _dirty_snapshot(session_id)

    get_snapshot = get_frontend_snapshot
    snapshot = get_frontend_snapshot

    def get_frontend_events(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        session_id = _session_id(args, kwargs)
        from_seq = int(kwargs.get("from_seq", 0))
        limit = int(kwargs.get("limit", MAX_EVENTS_LIMIT))
        if len(args) > 1:
            from_seq = int(args[1])
        if len(args) > 2:
            limit = int(args[2])
        self.calls.append(
            {
                "method": "get_frontend_events",
                "session_id": session_id,
                "from_seq": from_seq,
                "limit": limit,
            }
        )
        self._require_session(session_id)
        return {
            "events": [event for event in _dirty_events(session_id) if event["seq"] > from_seq][:limit],
            "next_from_seq": from_seq + limit,
            "has_more": True,
        }

    get_events = get_frontend_events
    events = get_frontend_events

    def stop_session(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        session_id = _session_id(args, kwargs)
        self.calls.append({"method": "stop_session", "session_id": session_id})
        session = self._require_session(session_id)
        self._require_status(session, {"created", "running", "paused"}, "stop")
        session["status"] = "completed"
        return {"session_id": session_id, "status": "completed"}

    stop = stop_session

    def _require_session(self, session_id: str) -> dict[str, Any]:
        return self.sessions[session_id]

    @staticmethod
    def _require_status(session: Mapping[str, Any], allowed: set[str], operation: str) -> None:
        if session["status"] not in allowed:
            raise FakeControlPlaneError(
                ErrorCode.SESSION_STATE_CONFLICT.value,
                f"{operation} is not allowed while session is {session['status']}",
                http_status=409,
                retryable=True,
                details={"status": session["status"], "thought": "must-not-leak"},
            )

    @staticmethod
    def _session(
        session_id: str,
        status: str,
        *,
        current_tick_id: str = "2024-01-02T14:02:00+08:00",
    ) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "status": status,
            "current_tick_id": current_tick_id,
            "tick_state": "COMMIT_TICK",
            "agent_count": 24,
            "active_agent_count": 23,
            "created_at": "2024-01-02T09:29:30+08:00",
        }


class ControlRestApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        if ControlRestApi is None:
            self.fail(
                "ControlRestApi is missing. Expected "
                "Ouroboros.core.web_api.control_rest.ControlRestApi(control_plane=...)."
            )

    def test_create_get_start_pause_step_snapshot_events_and_stop_use_only_orchestrator(self) -> None:
        orchestrator = FakeMetaOrchestrator()
        api = self._api(orchestrator)

        create_body = self._success(
            self._call(
                api,
                "create_session",
                {
                    "scenario_id": "demo_a_share",
                    "symbol": "demo_stock",
                    "agent_profile_set": "default_24",
                    "start_tick_id": "2024-01-02T09:30:00+08:00",
                    "end_tick_id": "2024-01-02T15:00:00+08:00",
                    "tick_interval": "5m",
                },
                request_id="req_create",
            ),
            status_codes={200, 201},
        )
        self.assertEqual(create_body["data"]["status"], "created")
        self.assertEqual(create_body["data"]["websocket_url"], "/api/v1/sessions/sim_created/ws")

        get_body = self._success(
            self._call(api, "get_session", "sim_created", request_id="req_get")
        )
        self.assertEqual(get_body["data"]["session_id"], "sim_created")

        start_body = self._success(
            self._call(
                api,
                "start_session",
                "sim_created",
                {"mode": "continuous"},
                request_id="req_start",
            )
        )
        self.assertEqual(start_body["data"], {"session_id": "sim_created", "status": "running", "accepted": True})

        pause_body = self._success(
            self._call(
                api,
                "pause_session",
                "sim_created",
                {"reason": "operator_pause"},
                request_id="req_pause",
            )
        )
        self.assertEqual(pause_body["data"]["pause_after_state"], "COMMIT_TICK")

        step_body = self._success(
            self._call(
                api,
                "step_session",
                "sim_created",
                {"ticks": 1},
                request_id="req_step",
            )
        )
        self.assertEqual(step_body["data"]["scheduled_ticks"], 1)

        snapshot_body = self._success(
            self._call(api, "get_snapshot", "sim_created", request_id="req_snapshot")
        )
        self.assertEqual(snapshot_body["data"]["session_id"], "sim_created")

        events_body = self._success(
            self._call(
                api,
                "get_events",
                "sim_created",
                from_seq=1000,
                limit=99999,
                request_id="req_events",
            )
        )
        self.assertTrue(events_body["data"]["events"])
        self.assertTrue(all(event["seq"] > 1000 for event in events_body["data"]["events"]))
        self.assertLessEqual(orchestrator.calls[-1]["limit"], MAX_EVENTS_LIMIT)

        stop_body = self._success(
            self._call(
                api,
                "stop_session",
                "sim_created",
                {"reason": "operator_stop"},
                request_id="req_stop",
            )
        )
        self.assertEqual(
            stop_body["data"],
            {
                "session_id": "sim_created",
                "status": "completed",
                "completion_reason": "operator_stop",
            },
        )

        methods = [call["method"] for call in orchestrator.calls]
        for expected_method in [
            "create_session",
            "get_session",
            "start_session",
            "pause_session",
            "step_session",
            "get_frontend_snapshot",
            "get_frontend_events",
            "stop_session",
        ]:
            self.assertIn(expected_method, methods)

    def test_start_pause_step_and_stop_state_conflicts_return_error_schema(self) -> None:
        cases = [
            ("start_session", "running", {"mode": "continuous"}, "req_start_conflict"),
            ("pause_session", "completed", {"reason": "operator_pause"}, "req_pause_conflict"),
            ("step_session", "running", {"ticks": 1}, "req_step_conflict"),
            ("stop_session", "completed", {"reason": "operator_stop"}, "req_stop_conflict"),
        ]

        for method_name, status, payload, request_id in cases:
            with self.subTest(method_name=method_name, status=status):
                api = self._api(FakeMetaOrchestrator(initial_status=status))
                body = self._error(
                    self._call(api, method_name, "sim_001", payload, request_id=request_id),
                    status_code=409,
                )
                self.assertEqual(body["request_id"], request_id)
                self.assertEqual(body["error"]["code"], ErrorCode.SESSION_STATE_CONFLICT.value)
                self.assertTrue(body["error"]["retryable"])
                self._assert_no_private_web_data(body)

    def test_missing_session_returns_error_schema_without_private_details(self) -> None:
        api = self._api(FakeMetaOrchestrator())

        body = self._error(
            self._call(api, "get_session", "missing", request_id="req_missing"),
            status_code=404,
        )

        self.assertEqual(body["request_id"], "req_missing")
        self.assertEqual(body["error"]["code"], ErrorCode.SESSION_NOT_FOUND.value)
        self.assertFalse(body["error"]["retryable"])
        self._assert_no_private_web_data(body)

    def test_snapshot_filters_thought_ui_audit_order_input_private_memory_and_internal_payload(self) -> None:
        api = self._api(FakeMetaOrchestrator())

        body = self._success(
            self._call(api, "get_snapshot", "sim_001", request_id="req_snapshot_filter")
        )

        data = body["data"]
        self.assertEqual(data["market"]["symbol"], "demo_stock")
        self.assertEqual(data["agents"][0]["agent_id"], "retail_b")
        self._assert_no_private_web_data(body)

    def test_events_apply_from_seq_limit_cap_and_visibility_filtering(self) -> None:
        orchestrator = FakeMetaOrchestrator()
        api = self._api(orchestrator)

        body = self._success(
            self._call(
                api,
                "get_events",
                "sim_001",
                from_seq=1000,
                limit=99999,
                request_id="req_events_filter",
            )
        )

        events = body["data"]["events"]
        self.assertTrue(events)
        self.assertTrue(all(event["seq"] > 1000 for event in events))
        self.assertLessEqual(len(events), MAX_EVENTS_LIMIT)
        self.assertLessEqual(orchestrator.calls[-1]["limit"], MAX_EVENTS_LIMIT)
        self.assertEqual(orchestrator.calls[-1]["from_seq"], 1000)
        self.assertNotIn("Order_Input", {event["type"] for event in events})
        self.assertNotIn("UI_Audit", {event["type"] for event in events})
        self._assert_no_private_web_data(body)

    def _api(self, orchestrator: FakeMetaOrchestrator) -> Any:
        try:
            return ControlRestApi(control_plane=orchestrator)  # type: ignore[misc]
        except TypeError:
            return ControlRestApi(orchestrator=orchestrator)  # type: ignore[misc]

    def _call(self, api: Any, method_name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(api, method_name, None)
        if method is None:
            handle = getattr(api, "handle", None)
            if handle is None or RestHttpRequest is None:
                self.fail(f"ControlRestApi missing method {method_name}")
            result = handle(self._http_request(method_name, *args, **kwargs))
        else:
            result = method(*args, **kwargs)
        if inspect.isawaitable(result):
            return asyncio.run(result)
        return result

    def _http_request(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        request_id = kwargs.pop("request_id")
        headers = {"X-Request-Id": request_id, "Content-Type": "application/json"}
        session_id = args[0] if args and isinstance(args[0], str) else None
        body = args[1] if len(args) > 1 and isinstance(args[1], Mapping) else None
        query: dict[str, int] = {}
        if method_name == "create_session":
            return RestHttpRequest(
                method="POST",
                path="/api/v1/sessions",
                headers=headers,
                body=args[0],
            )
        if method_name == "get_session":
            return RestHttpRequest(
                method="GET",
                path=f"/api/v1/sessions/{session_id}",
                headers={"X-Request-Id": request_id},
            )
        if method_name == "start_session":
            return RestHttpRequest(
                method="POST",
                path=f"/api/v1/sessions/{session_id}/start",
                headers=headers,
                body=body,
            )
        if method_name == "pause_session":
            return RestHttpRequest(
                method="POST",
                path=f"/api/v1/sessions/{session_id}/pause",
                headers=headers,
                body=body,
            )
        if method_name == "step_session":
            return RestHttpRequest(
                method="POST",
                path=f"/api/v1/sessions/{session_id}/step",
                headers=headers,
                body=body,
            )
        if method_name == "get_snapshot":
            return RestHttpRequest(
                method="GET",
                path=f"/api/v1/sessions/{session_id}/snapshot",
                headers={"X-Request-Id": request_id},
            )
        if method_name == "get_events":
            query = {
                "from_seq": int(kwargs.get("from_seq", 0)),
                "limit": int(kwargs.get("limit", MAX_EVENTS_LIMIT)),
            }
            return RestHttpRequest(
                method="GET",
                path=f"/api/v1/sessions/{session_id}/events",
                headers={"X-Request-Id": request_id},
                query=query,
            )
        if method_name == "stop_session":
            return RestHttpRequest(
                method="POST",
                path=f"/api/v1/sessions/{session_id}/stop",
                headers=headers,
                body=body,
            )
        self.fail(f"ControlRestApi missing route mapping for {method_name}")

    def _success(self, response: Any, *, status_codes: set[int] | None = None) -> dict[str, Any]:
        status_codes = status_codes or {200}
        status, body = self._unwrap(response)
        if status is not None:
            self.assertIn(status, status_codes)
        parsed = RestSuccessResponse.from_dict(body)
        plain = parsed.to_dict()
        self.assertIn("data", plain)
        self.assertNotIn("error", plain)
        return plain

    def _error(self, response: Any, *, status_code: int) -> dict[str, Any]:
        status, body = self._unwrap(response)
        self.assertEqual(status, status_code, "REST errors must expose the documented HTTP status")
        parsed = RestErrorResponse.from_dict(body)
        plain = parsed.to_dict()
        self.assertIn("error", plain)
        self.assertNotIn("data", plain)
        return plain

    @staticmethod
    def _unwrap(response: Any) -> tuple[int | None, dict[str, Any]]:
        if isinstance(response, tuple) and len(response) == 2:
            status, body = response
            return int(status), dict(body)
        if isinstance(response, Mapping):
            if "status_code" in response and "body" in response:
                return int(response["status_code"]), dict(response["body"])
            return None, dict(response)
        if hasattr(response, "status_code") and hasattr(response, "body"):
            body = response.body
            if isinstance(body, bytes):
                body = json.loads(body.decode("utf-8"))
            return int(response.status_code), dict(body)
        raise AssertionError(f"unsupported ControlRestApi response type: {type(response)!r}")

    def _assert_no_private_web_data(self, body: Mapping[str, Any]) -> None:
        rendered = json.dumps(body, ensure_ascii=False, sort_keys=True)
        forbidden_fragments = [
            "thought",
            "thought_summary",
            "UI_Audit",
            "Order_Input",
            "private_memory",
            "prompt",
            "raw_agent_payload",
            "raw_payload",
            "internal_channel_payload",
            "agent_private_channel",
            "redis.raw",
            "must-not-leak",
        ]
        for fragment in forbidden_fragments:
            self.assertNotIn(fragment, rendered)
        try:
            if "error" in body:
                RestErrorResponse.from_dict(body)
            else:
                RestSuccessResponse.from_dict(body)
        except SchemaValidationError as exc:
            self.fail(f"response violates Web API schema: {exc}")


def _dirty_snapshot(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "last_seq": 1024,
        "current_tick_id": "2024-01-02T14:02:00+08:00",
        "tick_state": "COMMIT_TICK",
        "market": {
            "symbol": "demo_stock",
            "last_price": 15.2,
            "volume": 100000,
            "limit_state": "normal",
            "level2": {"bids": [["15.19", 12000]], "asks": [["15.21", 8000]]},
            "internal_channel_payload": {"channel": "redis.raw", "body": "must-not-leak"},
        },
        "agents": [
            {
                "agent_id": "retail_b",
                "agent_type": "retail",
                "lifecycle_state": "active",
                "risk_state": "normal",
                "equity": 5760000.0,
                "position_value": 152000.0,
                "private_memory": "must-not-leak",
                "raw_agent_payload": {"thought": "must-not-leak"},
            }
        ],
        "audit_graph": {
            "nodes": [{"id": "n1", "UI_Audit": {"thought": "must-not-leak"}}],
            "edges": [{"from": "n1", "to": "n2", "internal_channel_payload": "must-not-leak"}],
        },
        "causal_chains": [
            {
                "chain_id": "chain_001",
                "title": "public title",
                "summary": "public sanitized summary",
                "last_event_ref": "mkt_002",
                "thought_summary": "must-not-leak",
            }
        ],
        "Order_Input": {"order_id": "order_001"},
        "UI_Audit": {"thought": "must-not-leak"},
    }


def _dirty_events(session_id: str) -> list[dict[str, Any]]:
    return [
        {
            "seq": 1000,
            "type": "market.price",
            "session_id": session_id,
            "tick_id": "2024-01-02T14:00:00+08:00",
            "payload": {"symbol": "demo_stock", "last_price": 15.1},
        },
        {
            "seq": 1001,
            "type": "Order_Input",
            "session_id": session_id,
            "tick_id": "2024-01-02T14:01:00+08:00",
            "payload": {"order_id": "order_001", "reason": "must-not-leak"},
        },
        {
            "seq": 1002,
            "type": "UI_Audit",
            "session_id": session_id,
            "tick_id": "2024-01-02T14:01:00+08:00",
            "payload": {"thought": "must-not-leak"},
        },
        {
            "seq": 1003,
            "type": "agent.raw_payload",
            "session_id": session_id,
            "tick_id": "2024-01-02T14:01:00+08:00",
            "payload": {"raw_agent_payload": {"thought": "must-not-leak"}},
        },
        {
            "seq": 1004,
            "type": "audit.causal_chain",
            "session_id": session_id,
            "tick_id": "2024-01-02T14:02:00+08:00",
            "payload": {"summary": "public sanitized summary", "thought_summary": "must-not-leak"},
        },
        {
            "seq": 1005,
            "type": "market.price",
            "session_id": session_id,
            "tick_id": "2024-01-02T14:02:00+08:00",
            "payload": {
                "symbol": "demo_stock",
                "last_price": 15.2,
                "internal_channel_payload": {"channel": "agent_private_channel"},
            },
        },
        {
            "seq": 1006,
            "type": "market.price",
            "session_id": session_id,
            "tick_id": "2024-01-02T14:02:00+08:00",
            "payload": {"symbol": "demo_stock", "last_price": 15.3},
        },
    ]


if __name__ == "__main__":
    unittest.main()

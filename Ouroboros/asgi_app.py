"""ASGI deployment adapter for the Ouroboros Web API.

The app is intentionally thin: FastAPI owns HTTP/WebSocket transport only,
while the framework-free ControlRestApi and SessionRunner keep protocol and
runtime behavior in core code.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from Ouroboros.core.agents import AgentRuntime
from Ouroboros.core.chronos import InMemoryChronosRepository
from Ouroboros.core.llm import LLMConfig, LLMGateway
from Ouroboros.core.orchestrator import SessionAgentSpec, SessionRunner
from Ouroboros.core.schemas import SCHEMA_VERSION
from Ouroboros.core.schemas.common import SchemaValidationError
from Ouroboros.core.schemas.common import OrderActionType, Sentiment
from Ouroboros.core.web_api.control_rest import ControlRestApi, RestHttpRequest
from Ouroboros.core.web_api.realtime_ws import FrontendRealtimeGateway, FrontendWsMessage


app = FastAPI(title="Ouroboros Web API")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route(
    "/api/v1/{path:path}",
    methods=["GET", "POST"],
)
async def control_rest(path: str, request: Request) -> JSONResponse:
    body = await _json_body(request)
    response = await asyncio.to_thread(
        _control_api.handle,
        RestHttpRequest(
            method=request.method,
            path=f"/api/v1/{path}",
            headers=dict(request.headers),
            body=body,
            query=dict(request.query_params.multi_items()),
        ),
    )
    await _mirror_replay_events(response.body)
    return JSONResponse(
        status_code=response.status_code,
        content=response.body,
        headers=response.headers,
    )


@app.websocket("/api/v1/sessions/{session_id}/ws")
async def session_ws(
    websocket: WebSocket,
    session_id: str,
    client_id: str,
    from_seq: int | None = None,
) -> None:
    await websocket.accept()
    connect_messages = _realtime_gateway.connect(session_id, client_id, from_seq=from_seq)
    await _register_ws(session_id, client_id, websocket)
    await _send_ws_messages(websocket, connect_messages)
    try:
        while True:
            message = await websocket.receive_json()
            responses = _realtime_gateway.handle_client_message(
                session_id,
                client_id,
                message,
            )
            await _send_ws_messages(websocket, responses)
    except WebSocketDisconnect:
        pass
    finally:
        await _unregister_ws(session_id, client_id, websocket)
        _realtime_gateway.disconnect(session_id, client_id)


@dataclass(frozen=True)
class _DefaultAgentTemplate:
    agent_id: str
    agent_type: str
    cash: float
    position: int


_DEFAULT_AGENT_TEMPLATES: tuple[_DefaultAgentTemplate, ...] = (
    _DefaultAgentTemplate("mutual_fund_a", "mutual_fund", 2_000_000.0, 120_000),
    _DefaultAgentTemplate("mutual_fund_b", "mutual_fund", 1_800_000.0, 100_000),
    _DefaultAgentTemplate("hot_money_a", "hot_money", 800_000.0, 70_000),
    _DefaultAgentTemplate("hot_money_b", "hot_money", 750_000.0, 65_000),
    _DefaultAgentTemplate("quant_algo_a", "quant_algo", 600_000.0, 50_000),
    _DefaultAgentTemplate("quant_algo_b", "quant_algo", 600_000.0, 45_000),
    _DefaultAgentTemplate("national_team_a", "national_team", 5_000_000.0, 260_000),
    _DefaultAgentTemplate("national_team_b", "national_team", 4_500_000.0, 240_000),
    *(
        _DefaultAgentTemplate(
            f"retail_{suffix}",
            "retail",
            40_000.0 + (index % 4) * 10_000.0,
            1_000 + (index % 5) * 500,
        )
        for index, suffix in enumerate(
            (
                "a",
                "b",
                "c",
                "d",
                "e",
                "f",
                "g",
                "h",
                "i",
                "j",
                "k",
                "l",
                "m",
                "n",
                "o",
                "p",
            )
        )
    ),
)
_AGENT_MODE_ENV = "OUROBOROS_AGENT_MODE"
_AGENT_MODE_LLM = "llm"
_AGENT_MODE_MOCK_HOLD = "mock_hold"
_AGENT_MODES = frozenset({_AGENT_MODE_LLM, _AGENT_MODE_MOCK_HOLD})


def _default_agent_specs() -> list[SessionAgentSpec]:
    return [
        SessionAgentSpec.from_dict(
            {
                "permission_profile": _permission_profile(
                    template.agent_id,
                    template.agent_type,
                ),
                "cash": template.cash,
                "positions": {"demo_stock": template.position},
                "mark_prices": {"demo_stock": 10.0},
            }
        )
        for template in _DEFAULT_AGENT_TEMPLATES
    ]


def _permission_profile(agent_id: str, agent_type: str) -> dict[str, Any]:
    subscriptions = [
        "Market_Price",
        "Account_Snapshot:self",
        "Tape_Alerts",
        "End_of_Day",
    ]
    if agent_type in {"mutual_fund", "hot_money", "quant_algo", "national_team"}:
        subscriptions.insert(0, "Official_News")
    if agent_type in {"hot_money", "retail"}:
        subscriptions.append("Forum_Rumors")

    return {
        "schema_version": SCHEMA_VERSION,
        "agent_id": agent_id,
        "agent_type": agent_type,
        "subscriptions": subscriptions,
        "publish_permissions": {
            "order_action": True,
            "ui_audit": True,
            "forum_post": agent_type == "hot_money",
        },
        "official_news_scope": _official_news_scope(agent_type),
    }


def _official_news_scope(agent_type: str) -> list[str]:
    if agent_type == "retail":
        return []
    if agent_type == "national_team":
        return ["announcement", "news", "regulatory_notice"]
    return ["announcement", "news"]


def _create_runner() -> SessionRunner:
    agent_mode = _agent_mode_from_env()
    return SessionRunner(
        chronos_repository=InMemoryChronosRepository.from_dicts(
            initial_market_seeds={
                "demo_stock": {
                    "schema_version": SCHEMA_VERSION,
                    "seed_id": "seed_demo_stock",
                    "symbol": "demo_stock",
                    "previous_close": 10.0,
                    "limit_up": 11.0,
                    "limit_down": 9.0,
                    "initial_l2_snapshot": {
                        "bids": [["9.99", 1000], ["9.98", 1200]],
                        "asks": [["10.01", 1000], ["10.02", 1200]],
                    },
                }
            },
        ),
        agent_profile_sets={"default_24": _default_agent_specs()},
        agent_runtime_factory=_agent_runtime_factory(agent_mode),
    )


def _agent_mode_from_env(environ: Mapping[str, str] | None = None) -> str:
    source = environ if environ is not None else os.environ
    mode = source.get(_AGENT_MODE_ENV, _AGENT_MODE_LLM).strip().lower() or _AGENT_MODE_LLM
    if mode not in _AGENT_MODES:
        allowed = ", ".join(sorted(_AGENT_MODES))
        raise SchemaValidationError(f"{_AGENT_MODE_ENV} must be one of: {allowed}")
    return mode


def _agent_runtime_factory(agent_mode: str) -> Callable[[], AgentRuntime]:
    if agent_mode == _AGENT_MODE_MOCK_HOLD:
        return lambda: AgentRuntime(
            default_actions={
                template.agent_id: _default_action(template)
                for template in _DEFAULT_AGENT_TEMPLATES
            }
        )
    if agent_mode == _AGENT_MODE_LLM:
        return _create_llm_agent_runtime
    raise SchemaValidationError(f"unsupported agent mode: {agent_mode}")


def _create_llm_agent_runtime() -> AgentRuntime:
    gateway = LLMGateway(
        config=LLMConfig.from_env(),
        require_provider_config=True,
    )
    gateway.validate_provider_config()
    return AgentRuntime(llm_gateway=gateway)


def _default_action(template: _DefaultAgentTemplate) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "agent_id": template.agent_id,
        "action": {
            "action_type": OrderActionType.HOLD.value,
        },
        "belief_shift": {
            "confidence_delta": 0.0,
            "sentiment": Sentiment.NEUTRAL.value,
            "risk_appetite_delta": 0.0,
        },
        "evidence_refs": [_default_evidence_ref(template)],
    }


def _default_evidence_ref(template: _DefaultAgentTemplate) -> str:
    if template.agent_type == "retail":
        return "forum_post_default_signal"
    if template.agent_type == "national_team":
        return "tape_default_stabilizer"
    return "mkt_default_opening_signal"


_runner = _create_runner()
_control_api = ControlRestApi(control_plane=_runner)
_realtime_gateway = FrontendRealtimeGateway()
_mirrored_seq_by_session: dict[str, int] = {}
_ws_connections: dict[str, dict[str, WebSocket]] = {}
_ws_connections_lock = asyncio.Lock()


async def _json_body(request: Request) -> Mapping[str, Any] | None:
    if request.method.upper() == "GET":
        return None
    raw = await request.body()
    if not raw:
        return {}
    data = await request.json()
    if isinstance(data, Mapping):
        return data
    return {"_invalid_body": data}


async def _mirror_replay_events(body: Mapping[str, Any]) -> None:
    data = body.get("data")
    if not isinstance(data, Mapping):
        return
    session_id = data.get("session_id") or body.get("session_id")
    if not isinstance(session_id, str):
        return
    from_seq = _mirrored_seq_by_session.get(session_id, 0)
    try:
        events = _runner.get_frontend_events(
            session_id,
            from_seq=from_seq,
            limit=500,
            request_id="req_ws_mirror",
            trace_id=str(body.get("trace_id") or "trace_ws_mirror"),
        )["events"]
    except Exception:
        return
    for event in events:
        outbound = _realtime_gateway.publish_event(session_id, event)
        await _fanout_ws_messages(session_id, outbound)
    if events:
        _mirrored_seq_by_session[session_id] = int(events[-1]["seq"])


async def _register_ws(session_id: str, client_id: str, websocket: WebSocket) -> None:
    async with _ws_connections_lock:
        _ws_connections.setdefault(session_id, {})[client_id] = websocket


async def _unregister_ws(session_id: str, client_id: str, websocket: WebSocket) -> None:
    async with _ws_connections_lock:
        clients = _ws_connections.get(session_id)
        if clients is None or clients.get(client_id) is not websocket:
            return
        clients.pop(client_id, None)
        if not clients:
            _ws_connections.pop(session_id, None)


async def _fanout_ws_messages(
    session_id: str,
    outbound: Mapping[str, list[FrontendWsMessage]],
) -> None:
    async with _ws_connections_lock:
        sockets = {
            client_id: websocket
            for client_id, websocket in _ws_connections.get(session_id, {}).items()
            if client_id in outbound
        }
    for client_id, websocket in sockets.items():
        try:
            await _send_ws_messages(websocket, outbound[client_id])
        except RuntimeError:
            await _unregister_ws(session_id, client_id, websocket)


async def _send_ws_messages(
    websocket: WebSocket,
    messages: list[FrontendWsMessage],
) -> None:
    for message in messages:
        await websocket.send_json(message.body)

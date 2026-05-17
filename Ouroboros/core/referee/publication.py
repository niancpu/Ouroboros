"""Referee publication builders.

This module keeps Referee publication deterministic and narrow: pure builders
produce schema objects, while the lightweight classes only add routing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from Ouroboros.core.routing import Channel, ChannelRouter
from Ouroboros.core.schemas import (
    AuditGraphEvent,
    CausalChainEvent,
    EndOfDayEvent,
    InternalVisibility,
    MarketPriceEvent,
    SCHEMA_VERSION,
    SchemaValidationError,
    Severity,
    TapeAlertEvent,
    TapeAlertType,
    TradeBatch,
    TradeEvent,
)
from Ouroboros.core.schemas.common import (
    PRIVATE_FIELD_NAMES,
    PUBLIC_MARKET_FORBIDDEN_FIELD_NAMES,
    coerce_enum,
    ensure_no_forbidden_keys,
    require_int,
    require_mapping,
    require_non_empty_str,
    require_number,
)


EXCHANGE_PRODUCER = "exchange_broadcaster"
UI_AUDIT_PRODUCER = "ui_audit_officer"
POST_CLOSE_PHASES = frozenset({"closed", "after_close", "post_close", "end_of_day"})
FRONTEND_REF_PREFIXES = ("audit_graph_", "chain_")
PUBLIC_REF_PREFIXES = ("mkt_", "tape_", "eod_", "forum_", "news_", "trade_")


def build_tape_alerts(
    market_output: MarketPriceEvent | Mapping[str, Any],
    *,
    previous_market_output: MarketPriceEvent | Mapping[str, Any] | None = None,
    event_id_prefix: str = "tape",
    sequence_start: int = 1,
) -> list[TapeAlertEvent]:
    """Build public tape alerts from sanitized anonymous market output."""

    current = _market_output_data(market_output, "market_output")
    previous = (
        _market_output_data(previous_market_output, "previous_market_output")
        if previous_market_output is not None
        else None
    )
    symbol = require_non_empty_str(current.get("symbol"), "symbol")
    tick_id = require_non_empty_str(current.get("tick_id"), "tick_id")
    trace_id = require_non_empty_str(current.get("trace_id"), "trace_id")
    metrics = _anonymous_metrics(current, previous)
    alerts: list[tuple[TapeAlertType, Severity, str, dict[str, Any]]] = []

    price_change_pct = metrics.get("price_change_pct")
    if isinstance(price_change_pct, float) and price_change_pct >= 3.0:
        alerts.append(
            (
                TapeAlertType.LARGE_BUY_PRESSURE,
                Severity.MEDIUM,
                f"{symbol} 单 Tick 快速上涨，匿名买盘推动价格走强。",
                {"price_change_pct": price_change_pct},
            )
        )
    if isinstance(price_change_pct, float) and price_change_pct <= -3.0:
        alerts.append(
            (
                TapeAlertType.LARGE_SELL_PRESSURE,
                Severity.MEDIUM,
                f"{symbol} 单 Tick 快速下跌，匿名卖盘压力扩大。",
                {"price_change_pct": price_change_pct},
            )
        )

    if _ratio_trigger(current.get("active_sell_volume"), current.get("avg_sell_volume_5"), 3.0):
        alerts.append(
            (
                TapeAlertType.LARGE_SELL_PRESSURE,
                Severity.MEDIUM,
                f"{symbol} 匿名主动卖出量显著高于近 5 Tick 均值。",
                {"sell_volume": int(current["active_sell_volume"])},
            )
        )
    if _ratio_trigger(current.get("active_buy_volume"), current.get("avg_buy_volume_5"), 3.0):
        alerts.append(
            (
                TapeAlertType.LARGE_BUY_PRESSURE,
                Severity.MEDIUM,
                f"{symbol} 匿名主动买入量显著高于近 5 Tick 均值。",
                {"buy_volume": int(current["active_buy_volume"])},
            )
        )
    if _ratio_trigger(current.get("volume"), current.get("avg_volume_5"), 3.0):
        alerts.append(
            (
                TapeAlertType.VOLUME_SPIKE,
                Severity.LOW,
                f"{symbol} 成交量显著放大。",
                {"volume": int(current["volume"])},
            )
        )

    bid_depth_change_pct = metrics.get("bid_depth_change_pct")
    if isinstance(bid_depth_change_pct, float) and bid_depth_change_pct <= -30.0:
        alerts.append(
            (
                TapeAlertType.LIQUIDITY_VACUUM,
                Severity.HIGH,
                f"{symbol} 买一到买五深度快速下降，盘口承接减弱。",
                {"bid_depth_change_pct": bid_depth_change_pct},
            )
        )

    if current.get("limit_state") == "limit_up":
        alerts.append(
            (
                TapeAlertType.LIMIT_UP_PRESSURE,
                Severity.HIGH,
                f"{symbol} 触及涨停状态。",
                {"last_price": require_number(current.get("last_price"), "last_price", minimum=0)},
            )
        )
    if current.get("limit_state") == "limit_down":
        alerts.append(
            (
                TapeAlertType.LIMIT_DOWN_PRESSURE,
                Severity.HIGH,
                f"{symbol} 触及跌停状态。",
                {"last_price": require_number(current.get("last_price"), "last_price", minimum=0)},
            )
        )

    events: list[TapeAlertEvent] = []
    for offset, (alert_type, severity, public_text, alert_metrics) in enumerate(alerts):
        payload = {
            "schema_version": SCHEMA_VERSION,
            "event_id": f"{event_id_prefix}_{_stable_id(symbol)}_{sequence_start + offset:06d}",
            "tick_id": tick_id,
            "trace_id": trace_id,
            "producer": EXCHANGE_PRODUCER,
            "visibility": InternalVisibility.PUBLIC.value,
            "symbol": symbol,
            "alert_type": alert_type.value,
            "severity": severity.value,
            "public_text": public_text,
            "source": "anonymous_order_flow",
            "metrics": {**metrics, **alert_metrics},
        }
        events.append(TapeAlertEvent.from_dict(payload))
    return events


def build_end_of_day(
    market_output: MarketPriceEvent | Mapping[str, Any],
    *,
    market_phase: str,
    dragon_tiger: Mapping[str, Any] | None = None,
    event_id: str | None = None,
) -> EndOfDayEvent:
    """Build delayed post-close disclosure from anonymous market statistics."""

    phase = require_non_empty_str(market_phase, "market_phase")
    if phase not in POST_CLOSE_PHASES:
        raise SchemaValidationError("End_of_Day can only be published after close")
    data = _market_output_data(market_output, "market_output")
    dragon_data = require_mapping(dragon_tiger if dragon_tiger is not None else data.get("dragon_tiger", {}), "dragon_tiger")
    ensure_no_forbidden_keys(dragon_data, PUBLIC_MARKET_FORBIDDEN_FIELD_NAMES, "dragon_tiger")
    symbol = require_non_empty_str(data.get("symbol"), "symbol")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id or f"eod_{_stable_id(symbol)}_{_stable_id(str(data.get('tick_id')))}",
        "tick_id": require_non_empty_str(data.get("tick_id"), "tick_id"),
        "trace_id": require_non_empty_str(data.get("trace_id"), "trace_id"),
        "producer": EXCHANGE_PRODUCER,
        "visibility": InternalVisibility.PUBLIC.value,
        "symbol": symbol,
        "close_price": require_number(data.get("close_price", data.get("last_price")), "close_price", minimum=0),
        "volume": require_int(data.get("volume"), "volume", minimum=0),
        "turnover": require_number(data.get("turnover"), "turnover", minimum=0),
        "dragon_tiger": {
            "buy_rank": list(dragon_data.get("buy_rank", [])),
            "sell_rank": list(dragon_data.get("sell_rank", [])),
        },
    }
    return EndOfDayEvent.from_dict(payload)


def build_audit_graph(
    ui_audit_events: Iterable[Mapping[str, Any]],
    *,
    event_id: str,
    tick_id: str,
    trace_id: str,
) -> AuditGraphEvent:
    """Build a frontend-only audit graph from UI audit material."""

    nodes_by_agent: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for raw in ui_audit_events:
        event = _ui_audit_data(raw)
        agent_id = require_non_empty_str(event.get("agent_id"), "agent_id")
        nodes_by_agent[agent_id] = {
            "agent_id": agent_id,
            "agent_type": require_non_empty_str(event.get("agent_type", "unknown"), "agent_type"),
            "belief_score": require_number(event.get("belief_score", 0.0), "belief_score"),
            "position_value": require_number(event.get("position_value", 0.0), "position_value"),
            "risk_state": require_non_empty_str(event.get("risk_state", "normal"), "risk_state"),
        }
        edge_weight = _audit_edge_weight(event.get("belief_shift", 0.0))
        for idx, ref in enumerate(_string_list(event.get("evidence_refs", []), "evidence_refs")):
            _assert_allowed_event_ref(ref)
            edges.append(
                {
                    "source": require_non_empty_str(event.get("source_agent_id", "public_event"), "source"),
                    "target": agent_id,
                    "weight": edge_weight,
                    "reason_ref": ref,
                    "public_reason": str(event.get("public_reason") or "公开事件影响审计节点。"),
                }
            )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "event_id": require_non_empty_str(event_id, "event_id"),
        "tick_id": require_non_empty_str(tick_id, "tick_id"),
        "trace_id": require_non_empty_str(trace_id, "trace_id"),
        "producer": UI_AUDIT_PRODUCER,
        "visibility": InternalVisibility.FRONTEND_ONLY.value,
        "nodes": list(nodes_by_agent.values()),
        "edges": edges,
    }
    return AuditGraphEvent.from_dict(payload)


def build_causal_chain(
    *,
    event_id: str,
    tick_id: str,
    trace_id: str,
    chain_id: str,
    title: str,
    summary: str,
    steps: Iterable[Mapping[str, Any]],
    metrics: Mapping[str, Any] | None = None,
    trades: TradeBatch | Iterable[TradeEvent | Mapping[str, Any]] | None = None,
) -> CausalChainEvent:
    """Build a frontend-only, de-identified causal chain."""

    step_payloads: list[dict[str, Any]] = []
    for raw_step in steps:
        step = dict(require_mapping(raw_step, "step"))
        ensure_no_forbidden_keys(step, PRIVATE_FIELD_NAMES, "CausalStep")
        ref = require_non_empty_str(step.get("event_ref"), "event_ref")
        _assert_allowed_event_ref(ref)
        step_payloads.append(step)
    metric_data = dict(require_mapping(metrics or {}, "metrics"))
    ensure_no_forbidden_keys(metric_data, PRIVATE_FIELD_NAMES, "metrics")
    trade_count = _trade_count(trades)
    if trade_count is not None:
        metric_data.setdefault("trade_count", trade_count)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "event_id": require_non_empty_str(event_id, "event_id"),
        "tick_id": require_non_empty_str(tick_id, "tick_id"),
        "trace_id": require_non_empty_str(trace_id, "trace_id"),
        "producer": UI_AUDIT_PRODUCER,
        "visibility": InternalVisibility.FRONTEND_ONLY.value,
        "chain_id": require_non_empty_str(chain_id, "chain_id"),
        "title": require_non_empty_str(title, "title"),
        "summary": require_non_empty_str(summary, "summary"),
        "steps": step_payloads,
        "metrics": metric_data,
    }
    return CausalChainEvent.from_dict(payload)


@dataclass
class ExchangeBroadcaster:
    """Build and optionally route public exchange publications."""

    router: ChannelRouter | None = None
    _sequence: int = 0

    def build_tape_alerts(
        self,
        market_output: MarketPriceEvent | Mapping[str, Any],
        *,
        previous_market_output: MarketPriceEvent | Mapping[str, Any] | None = None,
    ) -> list[TapeAlertEvent]:
        events = build_tape_alerts(
            market_output,
            previous_market_output=previous_market_output,
            sequence_start=self._sequence + 1,
        )
        self._sequence += len(events)
        return events

    def publish_tape_alerts(
        self,
        market_output: MarketPriceEvent | Mapping[str, Any],
        *,
        previous_market_output: MarketPriceEvent | Mapping[str, Any] | None = None,
        ttl_seconds: float | None = None,
    ) -> list[TapeAlertEvent]:
        events = self.build_tape_alerts(
            market_output,
            previous_market_output=previous_market_output,
        )
        self._require_router()
        for event in events:
            self.router.publish(
                Channel.TAPE_ALERTS,
                event,
                producer=EXCHANGE_PRODUCER,
                ttl_seconds=ttl_seconds,
            )
        return events

    def build_end_of_day(
        self,
        market_output: MarketPriceEvent | Mapping[str, Any],
        *,
        market_phase: str,
        dragon_tiger: Mapping[str, Any] | None = None,
        event_id: str | None = None,
    ) -> EndOfDayEvent:
        return build_end_of_day(
            market_output,
            market_phase=market_phase,
            dragon_tiger=dragon_tiger,
            event_id=event_id,
        )

    def publish_end_of_day(
        self,
        market_output: MarketPriceEvent | Mapping[str, Any],
        *,
        market_phase: str,
        dragon_tiger: Mapping[str, Any] | None = None,
        event_id: str | None = None,
        ttl_seconds: float | None = None,
    ) -> EndOfDayEvent:
        event = self.build_end_of_day(
            market_output,
            market_phase=market_phase,
            dragon_tiger=dragon_tiger,
            event_id=event_id,
        )
        self._require_router()
        self.router.publish(
            Channel.END_OF_DAY,
            event,
            producer=EXCHANGE_PRODUCER,
            ttl_seconds=ttl_seconds,
        )
        return event

    def _require_router(self) -> None:
        if self.router is None:
            raise SchemaValidationError("router is required to publish referee events")


@dataclass
class UIAuditOfficer:
    """Build and optionally route frontend-only audit publications."""

    router: ChannelRouter | None = None

    def build_audit_graph(
        self,
        ui_audit_events: Iterable[Mapping[str, Any]],
        *,
        event_id: str,
        tick_id: str,
        trace_id: str,
    ) -> AuditGraphEvent:
        return build_audit_graph(
            ui_audit_events,
            event_id=event_id,
            tick_id=tick_id,
            trace_id=trace_id,
        )

    def publish_audit_graph(
        self,
        ui_audit_events: Iterable[Mapping[str, Any]],
        *,
        event_id: str,
        tick_id: str,
        trace_id: str,
        ttl_seconds: float | None = None,
    ) -> AuditGraphEvent:
        event = self.build_audit_graph(
            ui_audit_events,
            event_id=event_id,
            tick_id=tick_id,
            trace_id=trace_id,
        )
        self._require_router()
        self.router.publish(
            Channel.FRONTEND_AUDIT_GRAPH,
            event,
            producer=UI_AUDIT_PRODUCER,
            ttl_seconds=ttl_seconds,
        )
        return event

    def build_causal_chain(self, **kwargs: Any) -> CausalChainEvent:
        return build_causal_chain(**kwargs)

    def publish_causal_chain(
        self,
        *,
        ttl_seconds: float | None = None,
        **kwargs: Any,
    ) -> CausalChainEvent:
        event = self.build_causal_chain(**kwargs)
        self._require_router()
        self.router.publish(
            Channel.FRONTEND_CAUSAL_CHAIN,
            event,
            producer=UI_AUDIT_PRODUCER,
            ttl_seconds=ttl_seconds,
        )
        return event

    def _require_router(self) -> None:
        if self.router is None:
            raise SchemaValidationError("router is required to publish referee events")


def _market_output_data(value: MarketPriceEvent | Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if isinstance(value, MarketPriceEvent):
        data = value.to_dict()
    else:
        data = dict(require_mapping(value, field_name))
    ensure_no_forbidden_keys(data, PUBLIC_MARKET_FORBIDDEN_FIELD_NAMES, field_name)
    return data


def _ui_audit_data(value: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(require_mapping(value, "UI_Audit"))
    forbidden = PRIVATE_FIELD_NAMES - frozenset({"thought", "belief_shift"})
    ensure_no_forbidden_keys(data, forbidden, "UI_Audit")
    return data


def _anonymous_metrics(
    current: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    previous_price = current.get("previous_price")
    if previous is not None:
        previous_price = previous.get("last_price", previous_price)
    if previous_price is not None and current.get("last_price") is not None:
        base_price = require_number(previous_price, "previous_price", minimum=0)
        if base_price > 0:
            price = require_number(current.get("last_price"), "last_price", minimum=0)
            metrics["price_change_pct"] = round((price - base_price) / base_price * 100.0, 4)

    bid_depth = current.get("bid_depth")
    previous_bid_depth = current.get("previous_bid_depth")
    if bid_depth is None and current.get("level2") is not None:
        bid_depth = _bid_depth(current["level2"])
    if previous_bid_depth is None and previous is not None:
        previous_bid_depth = previous.get("bid_depth")
        if previous_bid_depth is None and previous.get("level2") is not None:
            previous_bid_depth = _bid_depth(previous["level2"])
    if bid_depth is not None and previous_bid_depth is not None:
        prev_depth = require_number(previous_bid_depth, "previous_bid_depth", minimum=0)
        if prev_depth > 0:
            current_depth = require_number(bid_depth, "bid_depth", minimum=0)
            metrics["bid_depth_change_pct"] = round((current_depth - prev_depth) / prev_depth * 100.0, 4)
    return metrics


def _bid_depth(level2: Any) -> int:
    data = require_mapping(level2, "level2")
    bids = data.get("bids", [])
    if not isinstance(bids, list):
        raise SchemaValidationError("level2.bids must be a list")
    depth = 0
    for item in bids[:5]:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise SchemaValidationError("level2.bids[] must be [price, quantity]")
        depth += require_int(item[1], "level2.bids.quantity", minimum=0)
    return depth


def _ratio_trigger(value: Any, average: Any, ratio: float) -> bool:
    if value is None or average in (None, 0, 0.0):
        return False
    return require_number(value, "value", minimum=0) >= require_number(average, "average", minimum=0) * ratio


def _string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise SchemaValidationError(f"{field_name} must be a list")
    return [require_non_empty_str(item, f"{field_name}[]") for item in value]


def _audit_edge_weight(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Mapping):
        confidence = abs(require_number(value.get("confidence_delta", 0.0), "belief_shift.confidence_delta"))
        risk = abs(require_number(value.get("risk_appetite_delta", 0.0), "belief_shift.risk_appetite_delta"))
        return max(0.05, min(1.0, confidence + risk * 0.5))
    return abs(require_number(value, "belief_shift"))


def _assert_allowed_event_ref(event_ref: str) -> None:
    if event_ref.startswith(PUBLIC_REF_PREFIXES) or event_ref.startswith(FRONTEND_REF_PREFIXES):
        return
    raise SchemaValidationError("event_ref must reference a public or frontend audit event")


def _trade_count(trades: TradeBatch | Iterable[TradeEvent | Mapping[str, Any]] | None) -> int | None:
    if trades is None:
        return None
    if isinstance(trades, TradeBatch):
        return len(trades.trades)
    count = 0
    for item in trades:
        if isinstance(item, TradeEvent):
            count += 1
        else:
            TradeEvent.from_dict(item)
            count += 1
    return count


def _stable_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_") or "unknown"


__all__ = [
    "ExchangeBroadcaster",
    "UIAuditOfficer",
    "build_audit_graph",
    "build_causal_chain",
    "build_end_of_day",
    "build_tape_alerts",
]

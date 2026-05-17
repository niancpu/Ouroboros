"""Market, clearing, Chronos, forum, and referee event schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .common import (
    CausalStepType,
    CommonEventHeader,
    InternalVisibility,
    LimitState,
    OrderKind,
    OrderSide,
    OrderType,
    PRIVATE_FIELD_NAMES,
    PUBLIC_MARKET_FORBIDDEN_FIELD_NAMES,
    RiskState,
    SCHEMA_VERSION,
    Severity,
    SourceType,
    Stance,
    TapeAlertType,
    TimeInForce,
    coerce_enum,
    ensure_no_forbidden_keys,
    ensure_schema_version,
    optional_str,
    reject_unknown_keys,
    require_int,
    require_int_map,
    require_mapping,
    require_non_empty_str,
    require_number,
    require_str_list,
    to_plain_data,
)


InternalEventHeader = CommonEventHeader


@dataclass(frozen=True)
class Level2Book:
    bids: list[tuple[str, int]] = field(default_factory=list)
    asks: list[tuple[str, int]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Level2Book":
        data = require_mapping(data, "level2")
        reject_unknown_keys(data, {"bids", "asks"}, "Level2Book")
        return cls(
            bids=_parse_level2_side(data.get("bids", []), "bids"),
            asks=_parse_level2_side(data.get("asks", []), "asks"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"bids": [list(item) for item in self.bids], "asks": [list(item) for item in self.asks]}


def _parse_level2_side(value: Any, field_name: str) -> list[tuple[str, int]]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    parsed: list[tuple[str, int]] = []
    for idx, item in enumerate(value):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(f"{field_name}[{idx}] must be [price, quantity]")
        parsed.append(
            (
                require_non_empty_str(str(item[0]), f"{field_name}[{idx}][0]"),
                require_int(item[1], f"{field_name}[{idx}][1]", minimum=0),
            )
        )
    return parsed


@dataclass(frozen=True)
class OrderInputEvent:
    schema_version: str
    event_id: str
    tick_id: str
    trace_id: str
    producer: str
    visibility: InternalVisibility
    agent_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float | None = None
    time_in_force: TimeInForce = TimeInForce.DAY
    client_order_id: str | None = None
    order_kind: OrderKind = OrderKind.NORMAL
    reason_code: str | None = None
    source_risk_state: RiskState | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OrderInputEvent":
        data = require_mapping(data, "OrderInputEvent")
        ensure_schema_version(data)
        ensure_no_forbidden_keys(data, PRIVATE_FIELD_NAMES, "OrderInputEvent")
        reject_unknown_keys(
            data,
            {
                "schema_version",
                "event_id",
                "tick_id",
                "trace_id",
                "producer",
                "visibility",
                "agent_id",
                "symbol",
                "side",
                "order_type",
                "price",
                "quantity",
                "time_in_force",
                "client_order_id",
                "order_kind",
                "reason_code",
                "source_risk_state",
            },
            "OrderInputEvent",
        )
        visibility = coerce_enum(InternalVisibility, data.get("visibility"), "visibility")
        if visibility != InternalVisibility.CONTROL_ONLY:
            raise ValueError("OrderInputEvent visibility must be control_only")
        order_type = coerce_enum(OrderType, data.get("order_type"), "order_type")
        price = (
            require_number(data["price"], "price", minimum=0)
            if data.get("price") is not None
            else None
        )
        if order_type == OrderType.LIMIT and price is None:
            raise ValueError("price is required for limit orders")
        return cls(
            schema_version=SCHEMA_VERSION,
            event_id=require_non_empty_str(data.get("event_id"), "event_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            producer=require_non_empty_str(data.get("producer"), "producer"),
            visibility=visibility,
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            symbol=require_non_empty_str(data.get("symbol"), "symbol"),
            side=coerce_enum(OrderSide, data.get("side"), "side"),
            order_type=order_type,
            price=price,
            quantity=require_int(data.get("quantity"), "quantity", minimum=1),
            time_in_force=coerce_enum(
                TimeInForce, data.get("time_in_force", "day"), "time_in_force"
            ),
            client_order_id=optional_str(data.get("client_order_id"), "client_order_id"),
            order_kind=coerce_enum(OrderKind, data.get("order_kind", "normal"), "order_kind"),
            reason_code=optional_str(data.get("reason_code"), "reason_code"),
            source_risk_state=(
                coerce_enum(RiskState, data["source_risk_state"], "source_risk_state")
                if data.get("source_risk_state") is not None
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class OrderRejectEvent:
    schema_version: str
    event_id: str
    tick_id: str
    order_event_id: str
    agent_id: str
    status: str
    reason_code: str
    public: bool

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OrderRejectEvent":
        data = require_mapping(data, "OrderRejectEvent")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            event_id=require_non_empty_str(data.get("event_id"), "event_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            order_event_id=require_non_empty_str(data.get("order_event_id"), "order_event_id"),
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            status=require_non_empty_str(data.get("status"), "status"),
            reason_code=require_non_empty_str(data.get("reason_code"), "reason_code"),
            public=bool(data.get("public", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class TradeEvent:
    schema_version: str
    event_id: str
    tick_id: str
    trace_id: str
    symbol: str
    price: float
    quantity: int
    buy_order_id: str
    sell_order_id: str
    trade_time: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TradeEvent":
        data = require_mapping(data, "TradeEvent")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            event_id=require_non_empty_str(data.get("event_id"), "event_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            symbol=require_non_empty_str(data.get("symbol"), "symbol"),
            price=require_number(data.get("price"), "price", minimum=0),
            quantity=require_int(data.get("quantity"), "quantity", minimum=1),
            buy_order_id=require_non_empty_str(data.get("buy_order_id"), "buy_order_id"),
            sell_order_id=require_non_empty_str(data.get("sell_order_id"), "sell_order_id"),
            trade_time=optional_str(data.get("trade_time"), "trade_time"),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class TradeBatch:
    schema_version: str
    batch_id: str
    tick_id: str
    trace_id: str
    trades: list[TradeEvent]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TradeBatch":
        data = require_mapping(data, "TradeBatch")
        ensure_schema_version(data)
        trades = data.get("trades", [])
        if not isinstance(trades, list):
            raise ValueError("trades must be a list")
        return cls(
            schema_version=SCHEMA_VERSION,
            batch_id=require_non_empty_str(data.get("batch_id"), "batch_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            trades=[TradeEvent.from_dict(item) for item in trades],
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class RiskResult:
    schema_version: str
    batch_id: str
    tick_id: str
    trace_id: str
    agent_id: str
    risk_state: RiskState
    equity: float
    drawdown_pct: float
    reason_code: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RiskResult":
        data = require_mapping(data, "RiskResult")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            batch_id=require_non_empty_str(data.get("batch_id"), "batch_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            risk_state=coerce_enum(RiskState, data.get("risk_state"), "risk_state"),
            equity=require_number(data.get("equity"), "equity"),
            drawdown_pct=require_number(data.get("drawdown_pct"), "drawdown_pct"),
            reason_code=require_non_empty_str(data.get("reason_code"), "reason_code"),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class AccountSnapshotEvent:
    schema_version: str
    event_id: str
    tick_id: str
    trace_id: str
    producer: str
    visibility: InternalVisibility
    agent_id: str
    cash: float
    available_cash: float
    positions: dict[str, int]
    available_shares: dict[str, int]
    frozen_shares: dict[str, int]
    market_value: float
    equity: float
    risk_state: RiskState
    source: str = "layer3_global_ledger"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AccountSnapshotEvent":
        data = require_mapping(data, "AccountSnapshotEvent")
        ensure_schema_version(data)
        visibility = coerce_enum(InternalVisibility, data.get("visibility"), "visibility")
        if visibility != InternalVisibility.AGENT_PRIVATE:
            raise ValueError("AccountSnapshotEvent visibility must be agent_private")
        return cls(
            schema_version=SCHEMA_VERSION,
            event_id=require_non_empty_str(data.get("event_id"), "event_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            producer=require_non_empty_str(data.get("producer"), "producer"),
            visibility=visibility,
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            cash=require_number(data.get("cash"), "cash"),
            available_cash=require_number(data.get("available_cash"), "available_cash"),
            positions=require_int_map(data.get("positions", {}), "positions"),
            available_shares=require_int_map(data.get("available_shares", {}), "available_shares"),
            frozen_shares=require_int_map(data.get("frozen_shares", {}), "frozen_shares"),
            market_value=require_number(data.get("market_value"), "market_value"),
            equity=require_number(data.get("equity"), "equity"),
            risk_state=coerce_enum(RiskState, data.get("risk_state"), "risk_state"),
            source=require_non_empty_str(data.get("source", "layer3_global_ledger"), "source"),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class MarketPriceEvent:
    schema_version: str
    event_id: str
    tick_id: str
    trace_id: str
    producer: str
    visibility: InternalVisibility
    symbol: str
    last_price: float
    volume: int
    turnover: float
    limit_up: float
    limit_down: float
    limit_state: LimitState
    level2: Level2Book

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MarketPriceEvent":
        data = require_mapping(data, "MarketPriceEvent")
        ensure_schema_version(data)
        ensure_no_forbidden_keys(data, PUBLIC_MARKET_FORBIDDEN_FIELD_NAMES, "MarketPriceEvent")
        visibility = coerce_enum(InternalVisibility, data.get("visibility"), "visibility")
        if visibility != InternalVisibility.PUBLIC:
            raise ValueError("MarketPriceEvent visibility must be public")
        return cls(
            schema_version=SCHEMA_VERSION,
            event_id=require_non_empty_str(data.get("event_id"), "event_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            producer=require_non_empty_str(data.get("producer"), "producer"),
            visibility=visibility,
            symbol=require_non_empty_str(data.get("symbol"), "symbol"),
            last_price=require_number(data.get("last_price"), "last_price", minimum=0),
            volume=require_int(data.get("volume"), "volume", minimum=0),
            turnover=require_number(data.get("turnover"), "turnover", minimum=0),
            limit_up=require_number(data.get("limit_up"), "limit_up", minimum=0),
            limit_down=require_number(data.get("limit_down"), "limit_down", minimum=0),
            limit_state=coerce_enum(LimitState, data.get("limit_state"), "limit_state"),
            level2=Level2Book.from_dict(data.get("level2", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class OfficialNewsEvent:
    schema_version: str
    event_id: str
    tick_id: str
    trace_id: str
    producer: str
    visibility: InternalVisibility
    created_at: str
    symbol: str
    fact_time: str
    source_type: SourceType
    source_name: str
    fact_id: str
    title: str
    summary: str
    confidence: str
    permission_tags: list[str]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OfficialNewsEvent":
        data = require_mapping(data, "OfficialNewsEvent")
        ensure_schema_version(data)
        visibility = coerce_enum(InternalVisibility, data.get("visibility"), "visibility")
        if visibility != InternalVisibility.PUBLIC:
            raise ValueError("OfficialNewsEvent visibility must be public")
        return cls(
            schema_version=SCHEMA_VERSION,
            event_id=require_non_empty_str(data.get("event_id"), "event_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            producer=require_non_empty_str(data.get("producer"), "producer"),
            visibility=visibility,
            created_at=require_non_empty_str(data.get("created_at"), "created_at"),
            symbol=require_non_empty_str(data.get("symbol"), "symbol"),
            fact_time=require_non_empty_str(data.get("fact_time"), "fact_time"),
            source_type=coerce_enum(SourceType, data.get("source_type"), "source_type"),
            source_name=require_non_empty_str(data.get("source_name"), "source_name"),
            fact_id=require_non_empty_str(data.get("fact_id"), "fact_id"),
            title=require_non_empty_str(data.get("title"), "title"),
            summary=require_non_empty_str(data.get("summary"), "summary"),
            confidence=require_non_empty_str(data.get("confidence"), "confidence"),
            permission_tags=require_str_list(data.get("permission_tags", []), "permission_tags"),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class ReleaseWindow:
    from_tick: str
    to_tick: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReleaseWindow":
        data = require_mapping(data, "release_window")
        return cls(
            from_tick=require_non_empty_str(data.get("from"), "release_window.from"),
            to_tick=require_non_empty_str(data.get("to"), "release_window.to"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"from": self.from_tick, "to": self.to_tick}


@dataclass(frozen=True)
class ReleaseFactsCommand:
    schema_version: str
    command_id: str
    tick_id: str
    trace_id: str
    symbol: str
    release_window: ReleaseWindow

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReleaseFactsCommand":
        data = require_mapping(data, "ReleaseFactsCommand")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            command_id=require_non_empty_str(data.get("command_id"), "command_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            symbol=require_non_empty_str(data.get("symbol"), "symbol"),
            release_window=ReleaseWindow.from_dict(data.get("release_window")),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class ReleaseFactsResult:
    schema_version: str
    command_id: str
    tick_id: str
    status: str
    published_event_ids: list[str]
    withheld_future_count: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReleaseFactsResult":
        data = require_mapping(data, "ReleaseFactsResult")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            command_id=require_non_empty_str(data.get("command_id"), "command_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            status=require_non_empty_str(data.get("status"), "status"),
            published_event_ids=require_str_list(
                data.get("published_event_ids", []), "published_event_ids"
            ),
            withheld_future_count=require_int(
                data.get("withheld_future_count"), "withheld_future_count", minimum=0
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class InitialMarketSeed:
    schema_version: str
    seed_id: str
    symbol: str
    previous_close: float
    limit_up: float
    limit_down: float
    initial_l2_snapshot: Level2Book

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "InitialMarketSeed":
        data = require_mapping(data, "InitialMarketSeed")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            seed_id=require_non_empty_str(data.get("seed_id"), "seed_id"),
            symbol=require_non_empty_str(data.get("symbol"), "symbol"),
            previous_close=require_number(data.get("previous_close"), "previous_close", minimum=0),
            limit_up=require_number(data.get("limit_up"), "limit_up", minimum=0),
            limit_down=require_number(data.get("limit_down"), "limit_down", minimum=0),
            initial_l2_snapshot=Level2Book.from_dict(
                data.get("initial_l2_snapshot", {})
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class ForumRumorEvent:
    schema_version: str
    event_id: str
    tick_id: str
    trace_id: str
    producer: str
    visibility: InternalVisibility
    post_id: str
    author_agent_id: str
    author_type: str
    text: str
    stance: Stance
    created_tick_id: str
    source: str = "agent_public_post"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ForumRumorEvent":
        data = require_mapping(data, "ForumRumorEvent")
        ensure_schema_version(data)
        ensure_no_forbidden_keys(data, PRIVATE_FIELD_NAMES, "ForumRumorEvent")
        visibility = coerce_enum(InternalVisibility, data.get("visibility"), "visibility")
        if visibility != InternalVisibility.PUBLIC:
            raise ValueError("ForumRumorEvent visibility must be public")
        return cls(
            schema_version=SCHEMA_VERSION,
            event_id=require_non_empty_str(data.get("event_id"), "event_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            producer=require_non_empty_str(data.get("producer"), "producer"),
            visibility=visibility,
            post_id=require_non_empty_str(data.get("post_id"), "post_id"),
            author_agent_id=require_non_empty_str(data.get("author_agent_id"), "author_agent_id"),
            author_type=require_non_empty_str(data.get("author_type"), "author_type"),
            text=require_non_empty_str(data.get("text"), "text"),
            stance=coerce_enum(Stance, data.get("stance"), "stance"),
            created_tick_id=require_non_empty_str(data.get("created_tick_id"), "created_tick_id"),
            source=require_non_empty_str(data.get("source", "agent_public_post"), "source"),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class TapeAlertEvent:
    schema_version: str
    event_id: str
    tick_id: str
    trace_id: str
    producer: str
    visibility: InternalVisibility
    symbol: str
    alert_type: TapeAlertType
    severity: Severity
    public_text: str
    source: str
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TapeAlertEvent":
        data = require_mapping(data, "TapeAlertEvent")
        ensure_schema_version(data)
        ensure_no_forbidden_keys(data, PUBLIC_MARKET_FORBIDDEN_FIELD_NAMES, "TapeAlertEvent")
        visibility = coerce_enum(InternalVisibility, data.get("visibility"), "visibility")
        if visibility != InternalVisibility.PUBLIC:
            raise ValueError("TapeAlertEvent visibility must be public")
        return cls(
            schema_version=SCHEMA_VERSION,
            event_id=require_non_empty_str(data.get("event_id"), "event_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            producer=require_non_empty_str(data.get("producer"), "producer"),
            visibility=visibility,
            symbol=require_non_empty_str(data.get("symbol"), "symbol"),
            alert_type=coerce_enum(TapeAlertType, data.get("alert_type"), "alert_type"),
            severity=coerce_enum(Severity, data.get("severity"), "severity"),
            public_text=require_non_empty_str(data.get("public_text"), "public_text"),
            source=require_non_empty_str(data.get("source"), "source"),
            metrics=dict(require_mapping(data.get("metrics", {}), "metrics")),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class DragonTigerSeat:
    seat_name: str
    seat_type: str
    buy_amount: float
    sell_amount: float
    net_amount: float

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DragonTigerSeat":
        data = require_mapping(data, "DragonTigerSeat")
        return cls(
            seat_name=require_non_empty_str(data.get("seat_name"), "seat_name"),
            seat_type=require_non_empty_str(data.get("seat_type"), "seat_type"),
            buy_amount=require_number(data.get("buy_amount"), "buy_amount"),
            sell_amount=require_number(data.get("sell_amount"), "sell_amount"),
            net_amount=require_number(data.get("net_amount"), "net_amount"),
        )


@dataclass(frozen=True)
class EndOfDayEvent:
    schema_version: str
    event_id: str
    tick_id: str
    trace_id: str
    producer: str
    visibility: InternalVisibility
    symbol: str
    close_price: float
    volume: int
    turnover: float
    dragon_tiger: dict[str, list[DragonTigerSeat]]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EndOfDayEvent":
        data = require_mapping(data, "EndOfDayEvent")
        ensure_schema_version(data)
        ensure_no_forbidden_keys(data, PUBLIC_MARKET_FORBIDDEN_FIELD_NAMES, "EndOfDayEvent")
        dragon = require_mapping(data.get("dragon_tiger", {}), "dragon_tiger")
        visibility = coerce_enum(InternalVisibility, data.get("visibility"), "visibility")
        if visibility != InternalVisibility.PUBLIC:
            raise ValueError("EndOfDayEvent visibility must be public")
        return cls(
            schema_version=SCHEMA_VERSION,
            event_id=require_non_empty_str(data.get("event_id"), "event_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            producer=require_non_empty_str(data.get("producer"), "producer"),
            visibility=visibility,
            symbol=require_non_empty_str(data.get("symbol"), "symbol"),
            close_price=require_number(data.get("close_price"), "close_price", minimum=0),
            volume=require_int(data.get("volume"), "volume", minimum=0),
            turnover=require_number(data.get("turnover"), "turnover", minimum=0),
            dragon_tiger={
                "buy_rank": [DragonTigerSeat.from_dict(item) for item in dragon.get("buy_rank", [])],
                "sell_rank": [DragonTigerSeat.from_dict(item) for item in dragon.get("sell_rank", [])],
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class AuditNode:
    agent_id: str
    agent_type: str
    belief_score: float
    position_value: float
    risk_state: RiskState

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AuditNode":
        data = require_mapping(data, "AuditNode")
        return cls(
            agent_id=require_non_empty_str(data.get("agent_id"), "agent_id"),
            agent_type=require_non_empty_str(data.get("agent_type"), "agent_type"),
            belief_score=require_number(data.get("belief_score"), "belief_score"),
            position_value=require_number(data.get("position_value"), "position_value"),
            risk_state=coerce_enum(RiskState, data.get("risk_state"), "risk_state"),
        )


@dataclass(frozen=True)
class AuditEdge:
    source: str
    target: str
    weight: float
    reason_ref: str
    public_reason: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AuditEdge":
        data = require_mapping(data, "AuditEdge")
        ensure_no_forbidden_keys(data, PRIVATE_FIELD_NAMES, "AuditEdge")
        return cls(
            source=require_non_empty_str(data.get("source"), "source"),
            target=require_non_empty_str(data.get("target"), "target"),
            weight=require_number(data.get("weight"), "weight"),
            reason_ref=require_non_empty_str(data.get("reason_ref"), "reason_ref"),
            public_reason=require_non_empty_str(data.get("public_reason"), "public_reason"),
        )


@dataclass(frozen=True)
class AuditGraphEvent:
    schema_version: str
    event_id: str
    tick_id: str
    trace_id: str
    producer: str
    visibility: InternalVisibility
    nodes: list[AuditNode]
    edges: list[AuditEdge]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AuditGraphEvent":
        data = require_mapping(data, "AuditGraphEvent")
        ensure_schema_version(data)
        ensure_no_forbidden_keys(data, PRIVATE_FIELD_NAMES, "AuditGraphEvent")
        visibility = coerce_enum(InternalVisibility, data.get("visibility"), "visibility")
        if visibility != InternalVisibility.FRONTEND_ONLY:
            raise ValueError("AuditGraphEvent visibility must be frontend_only")
        return cls(
            schema_version=SCHEMA_VERSION,
            event_id=require_non_empty_str(data.get("event_id"), "event_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            producer=require_non_empty_str(data.get("producer"), "producer"),
            visibility=visibility,
            nodes=[AuditNode.from_dict(item) for item in data.get("nodes", [])],
            edges=[AuditEdge.from_dict(item) for item in data.get("edges", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class CausalStep:
    step_id: str
    step_type: CausalStepType
    tick_id: str
    actor_id: str
    event_ref: str
    public_text: str
    label: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CausalStep":
        data = require_mapping(data, "CausalStep")
        ensure_no_forbidden_keys(data, PRIVATE_FIELD_NAMES, "CausalStep")
        return cls(
            step_id=require_non_empty_str(data.get("step_id"), "step_id"),
            step_type=coerce_enum(CausalStepType, data.get("step_type"), "step_type"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            actor_id=require_non_empty_str(data.get("actor_id"), "actor_id"),
            event_ref=require_non_empty_str(data.get("event_ref"), "event_ref"),
            label=optional_str(data.get("label"), "label"),
            public_text=require_non_empty_str(data.get("public_text"), "public_text"),
        )


@dataclass(frozen=True)
class CausalChainEvent:
    schema_version: str
    event_id: str
    tick_id: str
    trace_id: str
    producer: str
    visibility: InternalVisibility
    chain_id: str
    title: str
    summary: str
    last_event_ref: str
    steps: list[CausalStep]
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CausalChainEvent":
        data = require_mapping(data, "CausalChainEvent")
        ensure_schema_version(data)
        ensure_no_forbidden_keys(data, PRIVATE_FIELD_NAMES, "CausalChainEvent")
        visibility = coerce_enum(InternalVisibility, data.get("visibility"), "visibility")
        if visibility != InternalVisibility.FRONTEND_ONLY:
            raise ValueError("CausalChainEvent visibility must be frontend_only")
        steps = [CausalStep.from_dict(item) for item in data.get("steps", [])]
        last_event_ref = data.get("last_event_ref")
        if last_event_ref is None and steps:
            last_event_ref = steps[-1].event_ref
        return cls(
            schema_version=SCHEMA_VERSION,
            event_id=require_non_empty_str(data.get("event_id"), "event_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            producer=require_non_empty_str(data.get("producer"), "producer"),
            visibility=visibility,
            chain_id=require_non_empty_str(data.get("chain_id"), "chain_id"),
            title=require_non_empty_str(data.get("title"), "title"),
            summary=require_non_empty_str(data.get("summary"), "summary"),
            last_event_ref=require_non_empty_str(last_event_ref, "last_event_ref"),
            steps=steps,
            metrics=dict(require_mapping(data.get("metrics", {}), "metrics")),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)

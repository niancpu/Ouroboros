"""Deterministic in-process Layer 3 MarketDataPublisher.

The publisher owns only sanitized market snapshot cache. It consumes public
LOB views and internal trade batches, then emits `MarketPriceEvent` payloads
without exposing order IDs, agent IDs, client IDs, or private reasoning fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Mapping

from Ouroboros.core.routing import Channel, ChannelRouter
from Ouroboros.core.schemas import (
    InitialMarketSeed,
    InternalVisibility,
    Level2Book,
    LimitState,
    MarketPriceEvent,
    SCHEMA_VERSION,
    SchemaValidationError,
    TradeBatch,
    TradeEvent,
)
from Ouroboros.core.schemas.common import require_non_empty_str


@dataclass(frozen=True)
class MarketDataConfig:
    default_depth: int = 10

    def __post_init__(self) -> None:
        if self.default_depth < 1:
            raise SchemaValidationError("default_depth must be >= 1")


@dataclass
class MarketSnapshotState:
    symbol: str
    last_price: Decimal
    volume: int
    turnover: Decimal
    limit_up: Decimal
    limit_down: Decimal
    level2: Level2Book = field(default_factory=Level2Book)
    halted: bool = False


class MarketDataPublisher:
    """Build and optionally route compliant `MarketPriceEvent` snapshots."""

    producer = "market_data_publisher"

    def __init__(
        self,
        *,
        router: ChannelRouter | None = None,
        config: MarketDataConfig | None = None,
    ) -> None:
        self.router = router
        self.config = config or MarketDataConfig()
        self._states: dict[str, MarketSnapshotState] = {}
        self._event_sequence = 0

    def initialize_market(
        self,
        seed: InitialMarketSeed | Mapping[str, Any] | Iterable[InitialMarketSeed | Mapping[str, Any]],
        *,
        tick_id: str | None = None,
        trace_id: str | None = None,
        publish: bool = False,
        depth: int | None = None,
        ttl_seconds: float | None = None,
    ) -> MarketPriceEvent | list[MarketPriceEvent]:
        """Load initial market seeds and return the first public snapshot."""

        single_seed = isinstance(seed, InitialMarketSeed) or isinstance(seed, Mapping)
        seeds = [seed] if single_seed else list(seed)
        events: list[MarketPriceEvent] = []
        for item in seeds:
            parsed = item if isinstance(item, InitialMarketSeed) else InitialMarketSeed.from_dict(item)
            event_tick_id = tick_id or parsed.seed_id
            event_trace_id = trace_id or parsed.seed_id
            state = MarketSnapshotState(
                symbol=parsed.symbol,
                last_price=_decimal(parsed.previous_close, "previous_close"),
                volume=0,
                turnover=Decimal("0"),
                limit_up=_decimal(parsed.limit_up, "limit_up"),
                limit_down=_decimal(parsed.limit_down, "limit_down"),
                level2=_clip_level2(parsed.initial_l2_snapshot, depth or self.config.default_depth),
            )
            self._states[parsed.symbol] = state
            event = self._event_from_state(
                state,
                tick_id=event_tick_id,
                trace_id=event_trace_id,
                depth=depth,
            )
            if publish:
                self._publish(event, ttl_seconds=ttl_seconds)
            events.append(event)
        return events[0] if single_seed else events

    def build_market_price(
        self,
        *,
        symbol: str,
        tick_id: str,
        trace_id: str | None = None,
        trade_batch: TradeBatch | Mapping[str, Any] | None = None,
        trades: Iterable[TradeEvent | Mapping[str, Any]] | None = None,
        lob_view: Any | None = None,
        level2: Level2Book | Mapping[str, Any] | None = None,
        depth: int | None = None,
    ) -> MarketPriceEvent:
        """Apply trades and build one sanitized public price event."""

        symbol = require_non_empty_str(symbol, "symbol")
        tick_id = require_non_empty_str(tick_id, "tick_id")
        state = self._require_state(symbol)
        parsed_trades, batch_trace_id = _coerce_trades(trade_batch=trade_batch, trades=trades)
        for trade in parsed_trades:
            if trade.symbol != symbol:
                continue
            state.last_price = _decimal(trade.price, "trade.price")
            state.volume += trade.quantity
            state.turnover += _decimal(trade.price, "trade.price") * Decimal(trade.quantity)

        if lob_view is not None:
            state.level2 = _coerce_lob_view(lob_view, symbol=symbol, depth=depth or self.config.default_depth)
        elif level2 is not None:
            state.level2 = _clip_level2(_coerce_level2(level2), depth or self.config.default_depth)

        return self._event_from_state(
            state,
            tick_id=tick_id,
            trace_id=trace_id or batch_trace_id or f"trace_{_stable_id(tick_id)}",
            depth=depth,
        )

    def publish_market_view(
        self,
        *,
        symbol: str,
        tick_id: str,
        trace_id: str | None = None,
        trade_batch: TradeBatch | Mapping[str, Any] | None = None,
        trades: Iterable[TradeEvent | Mapping[str, Any]] | None = None,
        lob_view: Any | None = None,
        level2: Level2Book | Mapping[str, Any] | None = None,
        depth: int | None = None,
        ttl_seconds: float | None = None,
    ) -> MarketPriceEvent:
        event = self.build_market_price(
            symbol=symbol,
            tick_id=tick_id,
            trace_id=trace_id,
            trade_batch=trade_batch,
            trades=trades,
            lob_view=lob_view,
            level2=level2,
            depth=depth,
        )
        self._publish(event, ttl_seconds=ttl_seconds)
        return event

    def set_halted(self, symbol: str, halted: bool = True) -> None:
        self._require_state(symbol).halted = bool(halted)

    def snapshot_state(self, symbol: str) -> MarketSnapshotState:
        state = self._require_state(symbol)
        return MarketSnapshotState(
            symbol=state.symbol,
            last_price=state.last_price,
            volume=state.volume,
            turnover=state.turnover,
            limit_up=state.limit_up,
            limit_down=state.limit_down,
            level2=Level2Book(bids=list(state.level2.bids), asks=list(state.level2.asks)),
            halted=state.halted,
        )

    def _event_from_state(
        self,
        state: MarketSnapshotState,
        *,
        tick_id: str,
        trace_id: str,
        depth: int | None,
    ) -> MarketPriceEvent:
        self._event_sequence += 1
        payload = {
            "schema_version": SCHEMA_VERSION,
            "event_id": f"mkt_{_stable_id(state.symbol)}_{self._event_sequence:06d}",
            "tick_id": tick_id,
            "trace_id": trace_id,
            "producer": self.producer,
            "visibility": InternalVisibility.PUBLIC.value,
            "symbol": state.symbol,
            "last_price": _float_decimal(state.last_price),
            "volume": state.volume,
            "turnover": _float_decimal(state.turnover),
            "limit_up": _float_decimal(state.limit_up),
            "limit_down": _float_decimal(state.limit_down),
            "limit_state": _limit_state(state).value,
            "level2": _clip_level2(state.level2, depth or self.config.default_depth).to_dict(),
        }
        return MarketPriceEvent.from_dict(payload)

    def _publish(self, event: MarketPriceEvent, *, ttl_seconds: float | None = None) -> None:
        if self.router is None:
            raise SchemaValidationError("router is required to publish market data")
        self.router.publish(
            Channel.MARKET_PRICE,
            event,
            producer=self.producer,
            ttl_seconds=ttl_seconds,
        )

    def _require_state(self, symbol: str) -> MarketSnapshotState:
        symbol = require_non_empty_str(symbol, "symbol")
        try:
            return self._states[symbol]
        except KeyError as exc:
            raise SchemaValidationError(f"market not initialized for symbol {symbol!r}") from exc


def _coerce_trades(
    *,
    trade_batch: TradeBatch | Mapping[str, Any] | None,
    trades: Iterable[TradeEvent | Mapping[str, Any]] | None,
) -> tuple[list[TradeEvent], str | None]:
    if trade_batch is not None and trades is not None:
        raise SchemaValidationError("use either trade_batch or trades, not both")
    if trade_batch is not None:
        batch = trade_batch if isinstance(trade_batch, TradeBatch) else TradeBatch.from_dict(trade_batch)
        return list(batch.trades), batch.trace_id
    if trades is None:
        return [], None
    parsed: list[TradeEvent] = []
    for item in trades:
        parsed.append(item if isinstance(item, TradeEvent) else TradeEvent.from_dict(item))
    trace_id = parsed[0].trace_id if parsed else None
    return parsed, trace_id


def _coerce_lob_view(lob_view: Any, *, symbol: str, depth: int) -> Level2Book:
    if hasattr(lob_view, "symbol") and getattr(lob_view, "symbol") != symbol:
        raise SchemaValidationError("lob_view symbol must match requested symbol")
    if hasattr(lob_view, "to_level2"):
        return _clip_level2(lob_view.to_level2(), depth)
    if hasattr(lob_view, "to_dict"):
        data = lob_view.to_dict()
    else:
        data = lob_view
    if not isinstance(data, Mapping):
        raise SchemaValidationError("lob_view must be a LobView-like object or mapping")
    if data.get("symbol", symbol) != symbol:
        raise SchemaValidationError("lob_view symbol must match requested symbol")
    return _clip_level2(Level2Book.from_dict({"bids": data.get("bids", []), "asks": data.get("asks", [])}), depth)


def _coerce_level2(level2: Level2Book | Mapping[str, Any]) -> Level2Book:
    return level2 if isinstance(level2, Level2Book) else Level2Book.from_dict(level2)


def _clip_level2(level2: Level2Book, depth: int) -> Level2Book:
    if depth < 1:
        raise SchemaValidationError("depth must be >= 1")
    return Level2Book(
        bids=_aggregate_side(level2.bids, reverse=True, depth=depth),
        asks=_aggregate_side(level2.asks, reverse=False, depth=depth),
    )


def _aggregate_side(
    levels: Iterable[tuple[str, int]],
    *,
    reverse: bool,
    depth: int,
) -> list[tuple[str, int]]:
    aggregated: dict[Decimal, int] = {}
    for price_text, quantity in levels:
        price = _decimal(price_text, "level2.price")
        if quantity < 0:
            raise SchemaValidationError("level2 quantity must be >= 0")
        if quantity == 0:
            continue
        aggregated[price] = aggregated.get(price, 0) + quantity
    return [
        (_format_price(price), quantity)
        for price, quantity in sorted(aggregated.items(), reverse=reverse)[:depth]
    ]


def _limit_state(state: MarketSnapshotState) -> LimitState:
    if state.halted:
        return LimitState.HALTED
    if state.last_price >= state.limit_up:
        return LimitState.LIMIT_UP
    if state.last_price <= state.limit_down:
        return LimitState.LIMIT_DOWN
    return LimitState.NORMAL


def _decimal(value: Any, field_name: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise SchemaValidationError(f"{field_name} must be a number")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise SchemaValidationError(f"{field_name} must be a number") from exc
    if not number.is_finite():
        raise SchemaValidationError(f"{field_name} must be finite")
    if number < 0:
        raise SchemaValidationError(f"{field_name} must be >= 0")
    return number


def _float_decimal(value: Decimal) -> float:
    return float(value)


def _format_price(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _stable_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_") or "unknown"


__all__ = [
    "MarketDataConfig",
    "MarketDataPublisher",
    "MarketSnapshotState",
]

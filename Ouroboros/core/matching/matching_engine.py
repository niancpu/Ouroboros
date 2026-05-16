"""Deterministic in-process Layer 3 MatchingEngine.

The MatchingEngine owns LOB state and order status. It validates incoming
orders at the matching boundary, then generates trade batches for
ClearingHouse without publishing public market data or touching routing code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Mapping, Protocol

from Ouroboros.core.schemas import (
    InitialMarketSeed,
    InternalVisibility,
    Level2Book,
    OrderInputEvent,
    OrderKind,
    OrderRejectEvent,
    OrderSide,
    OrderType,
    SCHEMA_VERSION,
    SchemaValidationError,
    TimeInForce,
    TradeBatch,
    TradeEvent,
)
from Ouroboros.core.schemas.common import require_non_empty_str


class OrderLedger(Protocol):
    def validate_order(self, order: OrderInputEvent | Mapping[str, Any]) -> None:
        ...

    def register_order(self, order: OrderInputEvent | Mapping[str, Any]) -> object:
        ...


@dataclass(frozen=True)
class MatchingConfig:
    lot_size: int = 1
    allowed_producers: tuple[str, ...] = ("meta_orchestrator", "system_forced_liquidation")

    def __post_init__(self) -> None:
        if self.lot_size < 1:
            raise SchemaValidationError("lot_size must be >= 1")
        if not self.allowed_producers:
            raise SchemaValidationError("allowed_producers must not be empty")
        for producer in self.allowed_producers:
            require_non_empty_str(producer, "allowed_producers[]")


@dataclass(frozen=True)
class SymbolMarket:
    symbol: str
    previous_close: Decimal
    limit_up: Decimal
    limit_down: Decimal
    halted: bool = False

    def __post_init__(self) -> None:
        if self.limit_down > self.limit_up:
            raise SchemaValidationError("limit_down must be <= limit_up")


@dataclass
class RestingOrder:
    order: OrderInputEvent
    sequence: int
    remaining_quantity: int

    @property
    def price(self) -> Decimal:
        if self.order.price is None:
            raise SchemaValidationError("resting order must have a price")
        return _decimal(self.order.price, "order.price")


@dataclass(frozen=True)
class OrderStatus:
    order_id: str
    accepted_quantity: int
    remaining_quantity: int
    filled_quantity: int = 0
    status: str = "accepted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "accepted_quantity": self.accepted_quantity,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "status": self.status,
        }


@dataclass(frozen=True)
class OrderSubmissionResult:
    accepted_orders: list[OrderInputEvent] = field(default_factory=list)
    rejected_orders: list[OrderRejectEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted_orders": [item.to_dict() for item in self.accepted_orders],
            "rejected_orders": [item.to_dict() for item in self.rejected_orders],
        }


@dataclass(frozen=True)
class LobView:
    symbol: str
    bids: list[tuple[str, int]]
    asks: list[tuple[str, int]]

    def to_level2(self) -> Level2Book:
        return Level2Book(bids=self.bids, asks=self.asks)

    def to_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "bids": [list(item) for item in self.bids], "asks": [list(item) for item in self.asks]}


class LimitOrderBook:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.bids: list[RestingOrder] = []
        self.asks: list[RestingOrder] = []

    def add(self, order: RestingOrder) -> None:
        if order.order.side == OrderSide.BUY:
            self.bids.append(order)
        else:
            self.asks.append(order)

    def remove_empty(self) -> None:
        self.bids = [order for order in self.bids if order.remaining_quantity > 0]
        self.asks = [order for order in self.asks if order.remaining_quantity > 0]

    def best_opposite(self, incoming: OrderInputEvent) -> RestingOrder | None:
        book_side = self.asks if incoming.side == OrderSide.BUY else self.bids
        candidates = [order for order in book_side if order.remaining_quantity > 0]
        if not candidates:
            return None
        if incoming.side == OrderSide.BUY:
            return min(candidates, key=lambda item: (item.price, item.sequence))
        return max(candidates, key=lambda item: (item.price, -item.sequence))

    def visible_levels(self, depth: int = 10) -> LobView:
        bids = _aggregate_levels(self.bids, reverse=True, depth=depth)
        asks = _aggregate_levels(self.asks, reverse=False, depth=depth)
        return LobView(symbol=self.symbol, bids=bids, asks=asks)


class MatchingEngine:
    def __init__(
        self,
        *,
        config: MatchingConfig | None = None,
        order_ledger: OrderLedger | None = None,
    ) -> None:
        self.config = config or MatchingConfig()
        self.order_ledger = order_ledger
        self._markets: dict[str, SymbolMarket] = {}
        self._books: dict[str, LimitOrderBook] = {}
        self._pending_orders: list[RestingOrder] = []
        self._order_status: dict[str, OrderStatus] = {}
        self._accepted_orders: dict[str, OrderInputEvent] = {}
        self._sequence = 0
        self._trade_sequence = 0
        self._batch_sequence = 0

    def initialize_market(
        self,
        seed: InitialMarketSeed | Mapping[str, Any] | Iterable[InitialMarketSeed | Mapping[str, Any]],
    ) -> None:
        seeds: Iterable[InitialMarketSeed | Mapping[str, Any]]
        if isinstance(seed, InitialMarketSeed) or isinstance(seed, Mapping):
            seeds = [seed]
        else:
            seeds = seed

        for item in seeds:
            parsed = item if isinstance(item, InitialMarketSeed) else InitialMarketSeed.from_dict(item)
            market = SymbolMarket(
                symbol=parsed.symbol,
                previous_close=_decimal(parsed.previous_close, "previous_close"),
                limit_up=_decimal(parsed.limit_up, "limit_up"),
                limit_down=_decimal(parsed.limit_down, "limit_down"),
            )
            self._markets[parsed.symbol] = market
            self._books[parsed.symbol] = LimitOrderBook(parsed.symbol)
            self._load_initial_l2(parsed)

    def submit_orders(
        self,
        order_batch: OrderInputEvent | Mapping[str, Any] | Iterable[OrderInputEvent | Mapping[str, Any]],
        *,
        tick_id: str | None = None,
    ) -> OrderSubmissionResult:
        accepted: list[OrderInputEvent] = []
        rejected: list[OrderRejectEvent] = []
        orders = _as_order_iterable(order_batch)
        for raw_order in orders:
            parsed_tick = tick_id
            try:
                order = raw_order if isinstance(raw_order, OrderInputEvent) else OrderInputEvent.from_dict(raw_order)
                parsed_tick = parsed_tick or order.tick_id
                self._validate_order(order, tick_id=tick_id)
                self._accept_order(order)
                accepted.append(order)
            except SchemaValidationError as exc:
                rejected.append(_reject_from_raw(raw_order, parsed_tick, _reason_code(exc)))
            except ValueError as exc:
                rejected.append(_reject_from_raw(raw_order, parsed_tick, _reason_code(exc)))
        return OrderSubmissionResult(accepted_orders=accepted, rejected_orders=rejected)

    def match_orders(self, tick_id: str) -> TradeBatch:
        require_non_empty_str(tick_id, "tick_id")
        self._batch_sequence += 1
        batch_id = f"batch_{self._batch_sequence:06d}"
        pending = self._pop_pending_for_tick(tick_id)
        trace_id = pending[0].order.trace_id if pending else f"trace_{_stable_id(tick_id)}"
        trades: list[TradeEvent] = []
        for resting_order in sorted(pending, key=_incoming_priority_key):
            trades.extend(self._match_single(resting_order, tick_id=tick_id))
        return TradeBatch(
            schema_version=SCHEMA_VERSION,
            batch_id=batch_id,
            tick_id=tick_id,
            trace_id=trace_id,
            trades=trades,
        )

    def lob_view(self, symbol: str, *, depth: int = 10) -> LobView:
        book = self._require_book(symbol)
        return book.visible_levels(depth=depth)

    def order_status(self, order_id: str) -> OrderStatus:
        try:
            return self._order_status[order_id]
        except KeyError as exc:
            raise SchemaValidationError(f"order not found: {order_id!r}") from exc

    def _validate_order(self, order: OrderInputEvent, *, tick_id: str | None) -> None:
        if tick_id is not None and order.tick_id != tick_id:
            raise SchemaValidationError("stale_tick")
        if order.producer not in self.config.allowed_producers:
            raise SchemaValidationError("invalid_schema")
        if order.order_kind == OrderKind.FORCED_LIQUIDATION:
            if order.producer != "meta_orchestrator":
                raise SchemaValidationError("invalid_schema")
            if not order.reason_code or order.source_risk_state is None:
                raise SchemaValidationError("invalid_schema")
        if order.event_id in self._accepted_orders:
            raise SchemaValidationError("invalid_schema")

        market = self._require_market(order.symbol)
        if market.halted:
            raise SchemaValidationError("symbol_halted")
        if order.quantity % self.config.lot_size != 0:
            raise SchemaValidationError("invalid_lot_size")
        if order.price is not None:
            price = _decimal(order.price, "price")
            if price < market.limit_down or price > market.limit_up:
                raise SchemaValidationError("price_out_of_limit")
        if self.order_ledger is not None:
            self.order_ledger.validate_order(order)

    def _accept_order(self, order: OrderInputEvent) -> None:
        self._sequence += 1
        resting = RestingOrder(
            order=order,
            sequence=self._sequence,
            remaining_quantity=order.quantity,
        )
        self._pending_orders.append(resting)
        self._accepted_orders[order.event_id] = order
        self._order_status[order.event_id] = OrderStatus(
            order_id=order.event_id,
            accepted_quantity=order.quantity,
            remaining_quantity=order.quantity,
            status="accepted",
        )
        if self.order_ledger is not None:
            self.order_ledger.register_order(order)

    def _match_single(self, incoming: RestingOrder, *, tick_id: str) -> list[TradeEvent]:
        order = incoming.order
        book = self._require_book(order.symbol)
        trades: list[TradeEvent] = []
        while incoming.remaining_quantity > 0:
            passive = book.best_opposite(order)
            if passive is None or not _can_cross(order, passive):
                break
            quantity = min(incoming.remaining_quantity, passive.remaining_quantity)
            trades.append(self._build_trade(incoming, passive, quantity, tick_id=tick_id))
            incoming.remaining_quantity -= quantity
            passive.remaining_quantity -= quantity
            self._record_fill(incoming.order.event_id, quantity, incoming.remaining_quantity)
            self._record_fill(passive.order.event_id, quantity, passive.remaining_quantity)
            book.remove_empty()

        if incoming.remaining_quantity > 0 and _can_rest(order):
            book.add(incoming)
            self._record_resting(incoming.order.event_id, incoming.remaining_quantity)
        elif incoming.remaining_quantity > 0:
            self._record_canceled(incoming.order.event_id, incoming.remaining_quantity)
        return trades

    def _build_trade(
        self,
        incoming: RestingOrder,
        passive: RestingOrder,
        quantity: int,
        *,
        tick_id: str,
    ) -> TradeEvent:
        self._trade_sequence += 1
        buy_order_id = incoming.order.event_id if incoming.order.side == OrderSide.BUY else passive.order.event_id
        sell_order_id = incoming.order.event_id if incoming.order.side == OrderSide.SELL else passive.order.event_id
        return TradeEvent(
            schema_version=SCHEMA_VERSION,
            event_id=f"trade_{self._trade_sequence:06d}",
            tick_id=tick_id,
            trace_id=incoming.order.trace_id,
            symbol=incoming.order.symbol,
            price=float(passive.price),
            quantity=quantity,
            buy_order_id=buy_order_id,
            sell_order_id=sell_order_id,
            trade_time=tick_id,
        )

    def _record_fill(self, order_id: str, quantity: int, remaining_quantity: int) -> None:
        previous = self._order_status[order_id]
        filled_quantity = previous.filled_quantity + quantity
        status = "filled" if remaining_quantity == 0 else "partially_filled"
        self._order_status[order_id] = OrderStatus(
            order_id=order_id,
            accepted_quantity=previous.accepted_quantity,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            status=status,
        )

    def _record_resting(self, order_id: str, remaining_quantity: int) -> None:
        previous = self._order_status[order_id]
        status = "accepted" if previous.filled_quantity == 0 else "partially_filled"
        self._order_status[order_id] = OrderStatus(
            order_id=order_id,
            accepted_quantity=previous.accepted_quantity,
            filled_quantity=previous.filled_quantity,
            remaining_quantity=remaining_quantity,
            status=status,
        )

    def _record_canceled(self, order_id: str, remaining_quantity: int) -> None:
        previous = self._order_status[order_id]
        status = "canceled" if previous.filled_quantity == 0 else "partially_filled_canceled"
        self._order_status[order_id] = OrderStatus(
            order_id=order_id,
            accepted_quantity=previous.accepted_quantity,
            filled_quantity=previous.filled_quantity,
            remaining_quantity=remaining_quantity,
            status=status,
        )

    def _pop_pending_for_tick(self, tick_id: str) -> list[RestingOrder]:
        matching: list[RestingOrder] = []
        remaining: list[RestingOrder] = []
        for order in self._pending_orders:
            if order.order.tick_id == tick_id:
                matching.append(order)
            else:
                remaining.append(order)
        self._pending_orders = remaining
        return matching

    def _load_initial_l2(self, seed: InitialMarketSeed) -> None:
        book = self._require_book(seed.symbol)
        for side, levels in ((OrderSide.BUY, seed.initial_l2_snapshot.bids), (OrderSide.SELL, seed.initial_l2_snapshot.asks)):
            for index, level in enumerate(levels):
                price_text, quantity = level
                if quantity <= 0:
                    continue
                if quantity % self.config.lot_size != 0:
                    raise SchemaValidationError("invalid_lot_size")
                price = _decimal(price_text, "initial_l2_snapshot.price")
                market = self._require_market(seed.symbol)
                if price < market.limit_down or price > market.limit_up:
                    raise SchemaValidationError("price_out_of_limit")
                self._sequence += 1
                order = OrderInputEvent(
                    schema_version=SCHEMA_VERSION,
                    event_id=f"seed_{seed.seed_id}_{side.value}_{index + 1}",
                    tick_id=seed.seed_id,
                    trace_id=seed.seed_id,
                    producer="meta_orchestrator",
                    visibility=InternalVisibility.CONTROL_ONLY,
                    agent_id=f"seed_liquidity_{side.value}",
                    symbol=seed.symbol,
                    side=side,
                    order_type=OrderType.LIMIT,
                    price=float(price),
                    quantity=quantity,
                    time_in_force=TimeInForce.DAY,
                )
                book.add(RestingOrder(order=order, sequence=self._sequence, remaining_quantity=quantity))
                self._order_status[order.event_id] = OrderStatus(
                    order_id=order.event_id,
                    accepted_quantity=quantity,
                    remaining_quantity=quantity,
                    status="accepted",
                )

    def _require_market(self, symbol: str) -> SymbolMarket:
        try:
            return self._markets[symbol]
        except KeyError as exc:
            raise SchemaValidationError("symbol_halted") from exc

    def _require_book(self, symbol: str) -> LimitOrderBook:
        try:
            return self._books[symbol]
        except KeyError as exc:
            raise SchemaValidationError(f"book not initialized for symbol {symbol!r}") from exc


def _incoming_priority_key(order: RestingOrder) -> tuple[int, int]:
    forced_rank = 0 if order.order.order_kind == OrderKind.FORCED_LIQUIDATION else 1
    return (forced_rank, order.sequence)


def _as_order_iterable(
    order_batch: OrderInputEvent | Mapping[str, Any] | Iterable[OrderInputEvent | Mapping[str, Any]],
) -> Iterable[OrderInputEvent | Mapping[str, Any]]:
    if isinstance(order_batch, OrderInputEvent) or isinstance(order_batch, Mapping):
        return [order_batch]
    return order_batch


def _can_rest(order: OrderInputEvent) -> bool:
    return order.order_type == OrderType.LIMIT and order.time_in_force == TimeInForce.DAY


def _can_cross(incoming: OrderInputEvent, passive: RestingOrder) -> bool:
    if incoming.order_type == OrderType.MARKET:
        return True
    incoming_price = _decimal(incoming.price, "incoming.price")
    passive_price = passive.price
    if incoming.side == OrderSide.BUY:
        return incoming_price >= passive_price
    return incoming_price <= passive_price


def _aggregate_levels(
    orders: Iterable[RestingOrder],
    *,
    reverse: bool,
    depth: int,
) -> list[tuple[str, int]]:
    levels: dict[Decimal, int] = {}
    for order in orders:
        if order.remaining_quantity > 0:
            levels[order.price] = levels.get(order.price, 0) + order.remaining_quantity
    return [
        (_format_price(price), quantity)
        for price, quantity in sorted(levels.items(), reverse=reverse)[:depth]
    ]


def _reject_from_raw(
    raw_order: OrderInputEvent | Mapping[str, Any],
    tick_id: str | None,
    reason_code: str,
) -> OrderRejectEvent:
    if isinstance(raw_order, OrderInputEvent):
        order_event_id = raw_order.event_id
        agent_id = raw_order.agent_id
        reject_tick = raw_order.tick_id
    elif isinstance(raw_order, Mapping):
        order_event_id = str(raw_order.get("event_id") or "unknown_order")
        agent_id = str(raw_order.get("agent_id") or "unknown_agent")
        reject_tick = str(raw_order.get("tick_id") or tick_id or "unknown_tick")
    else:
        order_event_id = "unknown_order"
        agent_id = "unknown_agent"
        reject_tick = tick_id or "unknown_tick"
    return OrderRejectEvent(
        schema_version=SCHEMA_VERSION,
        event_id=f"reject_{_stable_id(order_event_id)}",
        tick_id=reject_tick,
        order_event_id=order_event_id,
        agent_id=agent_id,
        status="rejected",
        reason_code=reason_code,
        public=False,
    )


def _reason_code(exc: Exception) -> str:
    message = str(exc)
    allowed = {
        "invalid_schema",
        "stale_tick",
        "agent_suspended",
        "symbol_halted",
        "price_out_of_limit",
        "invalid_lot_size",
        "insufficient_available_cash",
        "insufficient_available_shares",
        "t_plus_one_restricted",
    }
    for code in allowed:
        if code in message:
            return code
    return "invalid_schema"


def _decimal(value: Any, field_name: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise SchemaValidationError(f"{field_name} must be a number")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise SchemaValidationError(f"{field_name} must be a number") from exc
    if not number.is_finite():
        raise SchemaValidationError(f"{field_name} must be finite")
    return number


def _format_price(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _stable_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_") or "unknown"


__all__ = [
    "LimitOrderBook",
    "LobView",
    "MatchingConfig",
    "MatchingEngine",
    "OrderLedger",
    "OrderStatus",
    "OrderSubmissionResult",
    "RestingOrder",
    "SymbolMarket",
]

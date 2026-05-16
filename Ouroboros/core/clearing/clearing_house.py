"""Deterministic in-memory Layer 3 ClearingHouse.

The ClearingHouse owns cash, positions, frozen shares, and account snapshots.
It consumes matched trade batches; it does not own matching, order queues, or
public market-data publication.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping

from Ouroboros.core.schemas import (
    AccountSnapshotEvent,
    InternalVisibility,
    OrderInputEvent,
    OrderSide,
    RiskResult,
    RiskState,
    SCHEMA_VERSION,
    SchemaValidationError,
    TradeBatch,
    TradeEvent,
)
from Ouroboros.core.schemas.common import require_mapping, require_non_empty_str


MONEY_QUANT = Decimal("0.000001")


@dataclass(frozen=True)
class ClearingConfig:
    commission_rate: float = 0.0
    stamp_tax_rate: float = 0.0
    warning_drawdown_pct: float = 20.0
    margin_call_drawdown_pct: float = 50.0

    def __post_init__(self) -> None:
        if self.commission_rate < 0:
            raise SchemaValidationError("commission_rate must be >= 0")
        if self.stamp_tax_rate < 0:
            raise SchemaValidationError("stamp_tax_rate must be >= 0")
        if self.warning_drawdown_pct < 0:
            raise SchemaValidationError("warning_drawdown_pct must be >= 0")
        if self.margin_call_drawdown_pct < self.warning_drawdown_pct:
            raise SchemaValidationError(
                "margin_call_drawdown_pct must be >= warning_drawdown_pct"
            )


@dataclass
class AccountLedger:
    agent_id: str
    cash: Decimal
    positions: dict[str, int] = field(default_factory=dict)
    frozen_lots: dict[str, dict[date, int]] = field(default_factory=dict)
    initial_equity: Decimal = Decimal("0")
    risk_state: RiskState = RiskState.NORMAL

    def total_frozen(self, symbol: str) -> int:
        return sum(self.frozen_lots.get(symbol, {}).values())

    def frozen_shares(self) -> dict[str, int]:
        symbols = set(self.positions) | set(self.frozen_lots)
        return {
            symbol: self.total_frozen(symbol)
            for symbol in sorted(symbols)
            if self.total_frozen(symbol) > 0
        }

    def available_shares(self) -> dict[str, int]:
        available: dict[str, int] = {}
        for symbol, quantity in self.positions.items():
            sellable = quantity - self.total_frozen(symbol)
            available[symbol] = max(0, sellable)
        return available


@dataclass(frozen=True)
class OrderLedgerRecord:
    order_id: str
    agent_id: str
    symbol: str
    side: OrderSide


@dataclass(frozen=True)
class SettlementResult:
    batch_id: str
    tick_id: str
    trace_id: str
    account_snapshots: list[AccountSnapshotEvent]
    risk_results: list[RiskResult]


class ClearingHouse:
    """Layer 3 in-memory SSOT for assets.

    Trade events only contain order IDs by contract, so the ClearingHouse keeps
    a small order-owner ledger registered from accepted `OrderInputEvent`s.
    """

    def __init__(self, config: ClearingConfig | None = None) -> None:
        self.config = config or ClearingConfig()
        self._accounts: dict[str, AccountLedger] = {}
        self._orders: dict[str, OrderLedgerRecord] = {}
        self._last_prices: dict[str, Decimal] = {}
        self._current_trading_date: date | None = None

    def open_account(
        self,
        *,
        agent_id: str,
        cash: float,
        positions: Mapping[str, int] | None = None,
        mark_prices: Mapping[str, float] | None = None,
    ) -> None:
        agent_id = require_non_empty_str(agent_id, "agent_id")
        if agent_id in self._accounts:
            raise SchemaValidationError(f"account already exists for agent {agent_id!r}")
        cash_value = _money(cash, "cash")
        position_data = _validate_positions(positions or {})
        if mark_prices:
            for symbol, price in mark_prices.items():
                self._last_prices[require_non_empty_str(symbol, "mark_prices key")] = _money(
                    price, f"mark_prices.{symbol}"
                )
        initial_equity = cash_value + self._market_value(position_data, mark_prices)
        self._accounts[agent_id] = AccountLedger(
            agent_id=agent_id,
            cash=cash_value,
            positions=position_data,
            initial_equity=initial_equity,
        )

    def register_order(self, order: OrderInputEvent | Mapping[str, Any]) -> OrderLedgerRecord:
        order = _coerce_order(order)
        if order.event_id in self._orders:
            existing = self._orders[order.event_id]
            if (
                existing.agent_id != order.agent_id
                or existing.symbol != order.symbol
                or existing.side != order.side
            ):
                raise SchemaValidationError(f"conflicting order registration {order.event_id!r}")
            return existing

        if order.agent_id not in self._accounts:
            raise SchemaValidationError(f"account not found for agent {order.agent_id!r}")
        record = OrderLedgerRecord(
            order_id=order.event_id,
            agent_id=order.agent_id,
            symbol=order.symbol,
            side=order.side,
        )
        self._orders[order.event_id] = record
        return record

    def validate_order(self, order: OrderInputEvent | Mapping[str, Any]) -> None:
        order = _coerce_order(order)
        account = self._require_account(order.agent_id)
        if order.side == OrderSide.SELL:
            available = account.available_shares().get(order.symbol, 0)
            if available < order.quantity:
                if account.positions.get(order.symbol, 0) >= order.quantity:
                    raise SchemaValidationError("t_plus_one_restricted")
                raise SchemaValidationError("insufficient_available_shares")
        elif order.price is not None:
            required_cash = self._buy_cash_required(
                price=_decimal(order.price, "price"),
                quantity=order.quantity,
            )
            if account.cash < required_cash:
                raise SchemaValidationError("insufficient_available_cash")

    def settle_trade_batch(
        self,
        batch: TradeBatch | Mapping[str, Any],
        *,
        mark_prices: Mapping[str, float] | None = None,
    ) -> SettlementResult:
        batch = _coerce_batch(batch)
        trading_date = _tick_date(batch.tick_id, "tick_id")
        self._advance_trading_date(trading_date)
        if mark_prices:
            for symbol, price in mark_prices.items():
                self._last_prices[require_non_empty_str(symbol, "mark_prices key")] = _money(
                    price, f"mark_prices.{symbol}"
                )

        touched_agents: set[str] = set()
        accounts_before = deepcopy(self._accounts)
        prices_before = dict(self._last_prices)
        try:
            for trade in batch.trades:
                self._settle_trade(trade, trading_date)
                touched_agents.add(self._orders[trade.buy_order_id].agent_id)
                touched_agents.add(self._orders[trade.sell_order_id].agent_id)
        except Exception:
            self._accounts = accounts_before
            self._last_prices = prices_before
            raise

        snapshots = [
            self.account_snapshot(agent_id, tick_id=batch.tick_id, trace_id=batch.trace_id)
            for agent_id in sorted(touched_agents)
        ]
        risk_results = [
            self.risk_result(
                agent_id,
                batch_id=batch.batch_id,
                tick_id=batch.tick_id,
                trace_id=batch.trace_id,
            )
            for agent_id in sorted(touched_agents)
        ]
        return SettlementResult(
            batch_id=batch.batch_id,
            tick_id=batch.tick_id,
            trace_id=batch.trace_id,
            account_snapshots=snapshots,
            risk_results=risk_results,
        )

    def commit_tick(self, tick_id: str) -> None:
        trading_date = _tick_date(tick_id, "tick_id")
        self._advance_trading_date(trading_date)
        self._release_frozen_shares(trading_date)

    def account_snapshot(
        self, agent_id: str, *, tick_id: str, trace_id: str
    ) -> AccountSnapshotEvent:
        account = self._require_account(agent_id)
        market_value = self._market_value(account.positions)
        equity = account.cash + market_value
        risk_state = self._risk_state(account, equity)
        account.risk_state = risk_state
        return AccountSnapshotEvent(
            schema_version=SCHEMA_VERSION,
            event_id=f"acct_{agent_id}_{_stable_id(tick_id)}",
            tick_id=tick_id,
            trace_id=trace_id,
            producer="clearing_house",
            visibility=InternalVisibility.AGENT_PRIVATE,
            agent_id=agent_id,
            cash=_float_money(account.cash),
            available_cash=_float_money(account.cash),
            positions=dict(sorted(account.positions.items())),
            available_shares=account.available_shares(),
            frozen_shares=account.frozen_shares(),
            market_value=_float_money(market_value),
            equity=_float_money(equity),
            risk_state=risk_state,
            source="layer3_global_ledger",
        )

    def risk_result(
        self, agent_id: str, *, batch_id: str, tick_id: str, trace_id: str
    ) -> RiskResult:
        account = self._require_account(agent_id)
        market_value = self._market_value(account.positions)
        equity = account.cash + market_value
        risk_state = self._risk_state(account, equity)
        account.risk_state = risk_state
        drawdown_pct = self._drawdown_pct(account, equity)
        reason_code = "ok"
        if risk_state == RiskState.WARNING:
            reason_code = "equity_drawdown_warning"
        elif risk_state == RiskState.MARGIN_CALL:
            reason_code = "equity_drawdown_limit"
        return RiskResult(
            schema_version=SCHEMA_VERSION,
            batch_id=batch_id,
            tick_id=tick_id,
            trace_id=trace_id,
            agent_id=agent_id,
            risk_state=risk_state,
            equity=_float_money(equity),
            drawdown_pct=float(drawdown_pct),
            reason_code=reason_code,
        )

    def _settle_trade(self, trade: TradeEvent, trading_date: date) -> None:
        buy_order = self._require_order(trade.buy_order_id)
        sell_order = self._require_order(trade.sell_order_id)
        if buy_order.side != OrderSide.BUY:
            raise SchemaValidationError(f"buy_order_id {trade.buy_order_id!r} is not a buy order")
        if sell_order.side != OrderSide.SELL:
            raise SchemaValidationError(
                f"sell_order_id {trade.sell_order_id!r} is not a sell order"
            )
        if buy_order.symbol != trade.symbol or sell_order.symbol != trade.symbol:
            raise SchemaValidationError("trade symbol must match registered orders")
        buyer = self._require_account(buy_order.agent_id)
        seller = self._require_account(sell_order.agent_id)

        price = _money(trade.price, "trade.price")
        gross = price * Decimal(trade.quantity)
        buyer_fee = self._commission(gross)
        seller_fee = self._commission(gross) + self._stamp_tax(gross)
        buy_total = gross + buyer_fee
        sell_net = gross - seller_fee

        if buyer.cash < buy_total:
            raise SchemaValidationError("insufficient_available_cash")
        if seller.available_shares().get(trade.symbol, 0) < trade.quantity:
            if seller.positions.get(trade.symbol, 0) >= trade.quantity:
                raise SchemaValidationError("t_plus_one_restricted")
            raise SchemaValidationError("insufficient_available_shares")

        buyer.cash = _quantize(buyer.cash - buy_total)
        seller.cash = _quantize(seller.cash + sell_net)
        buyer.positions[trade.symbol] = buyer.positions.get(trade.symbol, 0) + trade.quantity
        seller.positions[trade.symbol] = seller.positions.get(trade.symbol, 0) - trade.quantity
        if seller.positions[trade.symbol] == 0:
            del seller.positions[trade.symbol]
        buyer.frozen_lots.setdefault(trade.symbol, {})
        buyer.frozen_lots[trade.symbol][trading_date] = (
            buyer.frozen_lots[trade.symbol].get(trading_date, 0) + trade.quantity
        )
        self._last_prices[trade.symbol] = price

    def _require_account(self, agent_id: str) -> AccountLedger:
        try:
            return self._accounts[agent_id]
        except KeyError as exc:
            raise SchemaValidationError(f"account not found for agent {agent_id!r}") from exc

    def _require_order(self, order_id: str) -> OrderLedgerRecord:
        try:
            return self._orders[order_id]
        except KeyError as exc:
            raise SchemaValidationError(f"order not registered: {order_id!r}") from exc

    def _advance_trading_date(self, trading_date: date) -> None:
        if self._current_trading_date is None:
            self._current_trading_date = trading_date
            return
        if trading_date < self._current_trading_date:
            raise SchemaValidationError("tick_id must not move to an earlier trading date")
        if trading_date > self._current_trading_date:
            self._release_frozen_shares(trading_date)
            self._current_trading_date = trading_date

    def _release_frozen_shares(self, trading_date: date) -> None:
        for account in self._accounts.values():
            for symbol in list(account.frozen_lots):
                lots = account.frozen_lots[symbol]
                for frozen_date in list(lots):
                    if frozen_date < trading_date:
                        del lots[frozen_date]
                if not lots:
                    del account.frozen_lots[symbol]

    def _buy_cash_required(self, *, price: Decimal, quantity: int) -> Decimal:
        gross = price * Decimal(quantity)
        return _quantize(gross + self._commission(gross))

    def _commission(self, gross: Decimal) -> Decimal:
        return _quantize(gross * _decimal(self.config.commission_rate, "commission_rate"))

    def _stamp_tax(self, gross: Decimal) -> Decimal:
        return _quantize(gross * _decimal(self.config.stamp_tax_rate, "stamp_tax_rate"))

    def _market_value(
        self,
        positions: Mapping[str, int],
        override_prices: Mapping[str, float] | None = None,
    ) -> Decimal:
        value = Decimal("0")
        for symbol, quantity in positions.items():
            if override_prices and symbol in override_prices:
                price = _money(override_prices[symbol], f"mark_prices.{symbol}")
            else:
                price = self._last_prices.get(symbol, Decimal("0"))
            value += price * Decimal(quantity)
        return _quantize(value)

    def _risk_state(self, account: AccountLedger, equity: Decimal) -> RiskState:
        drawdown_pct = self._drawdown_pct(account, equity)
        if drawdown_pct >= Decimal(str(self.config.margin_call_drawdown_pct)):
            return RiskState.MARGIN_CALL
        if drawdown_pct >= Decimal(str(self.config.warning_drawdown_pct)):
            return RiskState.WARNING
        return RiskState.NORMAL

    def _drawdown_pct(self, account: AccountLedger, equity: Decimal) -> Decimal:
        if account.initial_equity <= 0:
            return Decimal("0")
        drawdown = max(Decimal("0"), account.initial_equity - equity)
        return _quantize((drawdown / account.initial_equity) * Decimal("100"))


def _coerce_order(order: OrderInputEvent | Mapping[str, Any]) -> OrderInputEvent:
    if isinstance(order, OrderInputEvent):
        return order
    return OrderInputEvent.from_dict(order)


def _coerce_batch(batch: TradeBatch | Mapping[str, Any]) -> TradeBatch:
    if isinstance(batch, TradeBatch):
        return batch
    return TradeBatch.from_dict(batch)


def _validate_positions(positions: Mapping[str, int]) -> dict[str, int]:
    positions = require_mapping(positions, "positions")
    parsed: dict[str, int] = {}
    for symbol, quantity in positions.items():
        symbol = require_non_empty_str(symbol, "positions key")
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise SchemaValidationError(f"positions.{symbol} must be an integer")
        if quantity < 0:
            raise SchemaValidationError(f"positions.{symbol} must be >= 0")
        if quantity > 0:
            parsed[symbol] = quantity
    return parsed


def _tick_date(value: str, field_name: str) -> date:
    value = require_non_empty_str(value, field_name)
    try:
        return datetime.fromisoformat(value).date()
    except ValueError as exc:
        raise SchemaValidationError(f"{field_name} must be an ISO 8601 datetime") from exc


def _money(value: Any, field_name: str) -> Decimal:
    number = _decimal(value, field_name)
    if number < 0:
        raise SchemaValidationError(f"{field_name} must be >= 0")
    return _quantize(number)


def _decimal(value: Any, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise SchemaValidationError(f"{field_name} must be a number")
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise SchemaValidationError(f"{field_name} must be a number") from exc


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _float_money(value: Decimal) -> float:
    return float(_quantize(value))


def _stable_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_")

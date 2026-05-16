from __future__ import annotations

import unittest

from Ouroboros.core.clearing import ClearingConfig, ClearingHouse
from Ouroboros.core.schemas import InternalVisibility, RiskState, SchemaValidationError


TICK_DAY_1 = "2024-01-02T14:02:00+08:00"
TICK_DAY_2 = "2024-01-03T09:31:00+08:00"


def order(
    *,
    event_id: str,
    agent_id: str,
    side: str,
    quantity: int,
    price: float = 10.0,
) -> dict[str, object]:
    return {
        "schema_version": "v1",
        "event_id": event_id,
        "tick_id": TICK_DAY_1,
        "trace_id": "trace_abc",
        "producer": "meta_orchestrator",
        "visibility": "control_only",
        "agent_id": agent_id,
        "symbol": "demo_stock",
        "side": side,
        "order_type": "limit",
        "price": price,
        "quantity": quantity,
        "time_in_force": "day",
    }


def batch(
    *,
    batch_id: str,
    buy_order_id: str,
    sell_order_id: str,
    quantity: int,
    price: float = 10.0,
    tick_id: str = TICK_DAY_1,
) -> dict[str, object]:
    return {
        "schema_version": "v1",
        "batch_id": batch_id,
        "tick_id": tick_id,
        "trace_id": "trace_abc",
        "trades": [
            {
                "schema_version": "v1",
                "event_id": f"trade_{batch_id}",
                "tick_id": tick_id,
                "trace_id": "trace_abc",
                "symbol": "demo_stock",
                "price": price,
                "quantity": quantity,
                "buy_order_id": buy_order_id,
                "sell_order_id": sell_order_id,
            }
        ],
    }


def two_trade_batch_with_invalid_second_sell() -> dict[str, object]:
    return {
        "schema_version": "v1",
        "batch_id": "batch_two",
        "tick_id": TICK_DAY_1,
        "trace_id": "trace_abc",
        "trades": [
            {
                "schema_version": "v1",
                "event_id": "trade_ok",
                "tick_id": TICK_DAY_1,
                "trace_id": "trace_abc",
                "symbol": "demo_stock",
                "price": 10.0,
                "quantity": 100,
                "buy_order_id": "buy_001",
                "sell_order_id": "sell_001",
            },
            {
                "schema_version": "v1",
                "event_id": "trade_bad",
                "tick_id": TICK_DAY_1,
                "trace_id": "trace_abc",
                "symbol": "demo_stock",
                "price": 10.0,
                "quantity": 2_000,
                "buy_order_id": "buy_002",
                "sell_order_id": "sell_002",
            },
        ],
    }


def build_house() -> ClearingHouse:
    house = ClearingHouse(ClearingConfig(commission_rate=0.001, stamp_tax_rate=0.001))
    house.open_account(agent_id="buyer", cash=100_000.0)
    house.open_account(
        agent_id="seller",
        cash=1_000.0,
        positions={"demo_stock": 1_000},
        mark_prices={"demo_stock": 10.0},
    )
    return house


class ClearingHouseTests(unittest.TestCase):
    def test_buy_settlement_updates_cash_position_and_freezes_new_shares(self) -> None:
        house = build_house()
        house.register_order(order(event_id="buy_001", agent_id="buyer", side="buy", quantity=100))
        house.register_order(
            order(event_id="sell_001", agent_id="seller", side="sell", quantity=100)
        )

        result = house.settle_trade_batch(
            batch(batch_id="batch_001", buy_order_id="buy_001", sell_order_id="sell_001", quantity=100)
        )

        snapshots = {snapshot.agent_id: snapshot for snapshot in result.account_snapshots}
        buyer_snapshot = snapshots["buyer"]
        self.assertEqual(buyer_snapshot.producer, "clearing_house")
        self.assertEqual(buyer_snapshot.visibility, InternalVisibility.AGENT_PRIVATE)
        self.assertEqual(buyer_snapshot.cash, 98_999.0)
        self.assertEqual(buyer_snapshot.positions, {"demo_stock": 100})
        self.assertEqual(buyer_snapshot.available_shares, {"demo_stock": 0})
        self.assertEqual(buyer_snapshot.frozen_shares, {"demo_stock": 100})

        buyer_risk = next(item for item in result.risk_results if item.agent_id == "buyer")
        self.assertEqual(buyer_risk.risk_state, RiskState.NORMAL)
        self.assertEqual(buyer_risk.reason_code, "ok")

    def test_sell_settlement_reduces_available_position_and_adds_cash_after_fees(self) -> None:
        house = build_house()
        house.register_order(order(event_id="buy_001", agent_id="buyer", side="buy", quantity=200))
        house.register_order(
            order(event_id="sell_001", agent_id="seller", side="sell", quantity=200)
        )

        result = house.settle_trade_batch(
            batch(batch_id="batch_001", buy_order_id="buy_001", sell_order_id="sell_001", quantity=200)
        )

        seller_snapshot = next(
            snapshot for snapshot in result.account_snapshots if snapshot.agent_id == "seller"
        )
        self.assertEqual(seller_snapshot.cash, 2_996.0)
        self.assertEqual(seller_snapshot.positions, {"demo_stock": 800})
        self.assertEqual(seller_snapshot.available_shares, {"demo_stock": 800})
        self.assertEqual(seller_snapshot.frozen_shares, {})

    def test_same_day_bought_shares_cannot_be_sold(self) -> None:
        house = build_house()
        house.register_order(order(event_id="buy_001", agent_id="buyer", side="buy", quantity=100))
        house.register_order(
            order(event_id="sell_001", agent_id="seller", side="sell", quantity=100)
        )
        house.settle_trade_batch(
            batch(batch_id="batch_001", buy_order_id="buy_001", sell_order_id="sell_001", quantity=100)
        )

        same_day_sell = order(
            event_id="sell_same_day",
            agent_id="buyer",
            side="sell",
            quantity=100,
        )

        with self.assertRaisesRegex(SchemaValidationError, "t_plus_one_restricted"):
            house.validate_order(same_day_sell)

    def test_next_trading_day_unfreezes_bought_shares(self) -> None:
        house = build_house()
        house.register_order(order(event_id="buy_001", agent_id="buyer", side="buy", quantity=100))
        house.register_order(
            order(event_id="sell_001", agent_id="seller", side="sell", quantity=100)
        )
        house.settle_trade_batch(
            batch(batch_id="batch_001", buy_order_id="buy_001", sell_order_id="sell_001", quantity=100)
        )

        house.commit_tick(TICK_DAY_2)
        next_day_sell = {
            **order(event_id="sell_next_day", agent_id="buyer", side="sell", quantity=100),
            "tick_id": TICK_DAY_2,
        }

        house.validate_order(next_day_sell)
        snapshot = house.account_snapshot("buyer", tick_id=TICK_DAY_2, trace_id="trace_abc")
        self.assertEqual(snapshot.available_shares, {"demo_stock": 100})
        self.assertEqual(snapshot.frozen_shares, {})

    def test_partial_trade_only_freezes_filled_quantity(self) -> None:
        house = build_house()
        house.register_order(order(event_id="buy_001", agent_id="buyer", side="buy", quantity=500))
        house.register_order(
            order(event_id="sell_001", agent_id="seller", side="sell", quantity=500)
        )

        house.settle_trade_batch(
            batch(batch_id="batch_001", buy_order_id="buy_001", sell_order_id="sell_001", quantity=120)
        )

        snapshot = house.account_snapshot("buyer", tick_id=TICK_DAY_1, trace_id="trace_abc")
        self.assertEqual(snapshot.positions, {"demo_stock": 120})
        self.assertEqual(snapshot.frozen_shares, {"demo_stock": 120})

    def test_insufficient_cash_rejects_settlement_without_mutating_ledger(self) -> None:
        house = ClearingHouse()
        house.open_account(agent_id="buyer", cash=500.0)
        house.open_account(
            agent_id="seller",
            cash=0.0,
            positions={"demo_stock": 100},
            mark_prices={"demo_stock": 10.0},
        )
        house.register_order(order(event_id="buy_001", agent_id="buyer", side="buy", quantity=100))
        house.register_order(
            order(event_id="sell_001", agent_id="seller", side="sell", quantity=100)
        )

        with self.assertRaisesRegex(SchemaValidationError, "insufficient_available_cash"):
            house.settle_trade_batch(
                batch(
                    batch_id="batch_001",
                    buy_order_id="buy_001",
                    sell_order_id="sell_001",
                    quantity=100,
                )
            )

        snapshot = house.account_snapshot("buyer", tick_id=TICK_DAY_1, trace_id="trace_abc")
        self.assertEqual(snapshot.cash, 500.0)
        self.assertEqual(snapshot.positions, {})

    def test_failed_trade_batch_rolls_back_prior_fills(self) -> None:
        house = build_house()
        house.register_order(order(event_id="buy_001", agent_id="buyer", side="buy", quantity=100))
        house.register_order(
            order(event_id="sell_001", agent_id="seller", side="sell", quantity=100)
        )
        house.register_order(
            order(event_id="buy_002", agent_id="buyer", side="buy", quantity=2_000)
        )
        house.register_order(
            order(event_id="sell_002", agent_id="seller", side="sell", quantity=2_000)
        )

        with self.assertRaisesRegex(SchemaValidationError, "insufficient_available_shares"):
            house.settle_trade_batch(two_trade_batch_with_invalid_second_sell())

        buyer_snapshot = house.account_snapshot("buyer", tick_id=TICK_DAY_1, trace_id="trace_abc")
        seller_snapshot = house.account_snapshot("seller", tick_id=TICK_DAY_1, trace_id="trace_abc")
        self.assertEqual(buyer_snapshot.cash, 100_000.0)
        self.assertEqual(buyer_snapshot.positions, {})
        self.assertEqual(seller_snapshot.cash, 1_000.0)
        self.assertEqual(seller_snapshot.positions, {"demo_stock": 1_000})


if __name__ == "__main__":
    unittest.main()

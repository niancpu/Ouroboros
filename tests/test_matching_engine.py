from __future__ import annotations

import unittest

from Ouroboros.core.clearing import ClearingHouse
from Ouroboros.core.matching import MatchingConfig, MatchingEngine
from Ouroboros.core.schemas import OrderRejectEvent, TradeBatch


TICK = "2024-01-02T14:02:00+08:00"
TRACE = "trace_abc"


def seed() -> dict[str, object]:
    return {
        "schema_version": "v1",
        "seed_id": "seed_001",
        "symbol": "demo_stock",
        "previous_close": 10.0,
        "limit_up": 11.0,
        "limit_down": 9.0,
        "initial_l2_snapshot": {"bids": [], "asks": []},
    }


def order(
    *,
    event_id: str,
    agent_id: str,
    side: str,
    quantity: int,
    price: float | None = 10.0,
    order_type: str = "limit",
    tick_id: str = TICK,
    time_in_force: str = "day",
    producer: str = "meta_orchestrator",
    order_kind: str | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "schema_version": "v1",
        "event_id": event_id,
        "tick_id": tick_id,
        "trace_id": TRACE,
        "producer": producer,
        "visibility": "control_only",
        "agent_id": agent_id,
        "symbol": "demo_stock",
        "side": side,
        "order_type": order_type,
        "quantity": quantity,
        "time_in_force": time_in_force,
    }
    if price is not None:
        data["price"] = price
    if order_kind is not None:
        data.update(
            {
                "order_kind": order_kind,
                "reason_code": "equity_drawdown_limit",
                "source_risk_state": "margin_call",
            }
        )
    return data


class MatchingEngineTests(unittest.TestCase):
    def build_engine(self, *, lot_size: int = 1, ledger: ClearingHouse | None = None) -> MatchingEngine:
        engine = MatchingEngine(
            config=MatchingConfig(lot_size=lot_size),
            order_ledger=ledger,
        )
        engine.initialize_market(seed())
        return engine

    def test_submit_orders_validates_schema_tick_lot_limit_and_ledger_boundary(self) -> None:
        house = ClearingHouse()
        house.open_account(agent_id="buyer", cash=10_000.0)
        house.open_account(agent_id="poor_buyer", cash=100.0)
        house.open_account(agent_id="seller", cash=0.0, positions={"demo_stock": 100})
        engine = self.build_engine(lot_size=100, ledger=house)

        result = engine.submit_orders(
            [
                order(event_id="ok", agent_id="buyer", side="buy", quantity=100, price=10.0),
                order(event_id="stale", agent_id="buyer", side="buy", quantity=100, tick_id="2024-01-02T14:01:00+08:00"),
                order(event_id="bad_lot", agent_id="buyer", side="buy", quantity=50),
                order(event_id="bad_limit", agent_id="buyer", side="buy", quantity=100, price=11.01),
                order(event_id="bad_cash", agent_id="poor_buyer", side="buy", quantity=100, price=10.0),
            ],
            tick_id=TICK,
        )

        self.assertEqual([item.event_id for item in result.accepted_orders], ["ok"])
        reasons = {item.order_event_id: item.reason_code for item in result.rejected_orders}
        self.assertEqual(reasons["stale"], "stale_tick")
        self.assertEqual(reasons["bad_lot"], "invalid_lot_size")
        self.assertEqual(reasons["bad_limit"], "price_out_of_limit")
        self.assertEqual(reasons["bad_cash"], "insufficient_available_cash")
        for reject in result.rejected_orders:
            self.assertIsInstance(reject, OrderRejectEvent)
            self.assertFalse(reject.public)

    def test_lob_maintenance_keeps_unmatched_day_limit_orders_aggregated(self) -> None:
        engine = self.build_engine()

        engine.submit_orders(
            [
                order(event_id="bid_1", agent_id="buyer_a", side="buy", quantity=100, price=9.9),
                order(event_id="bid_2", agent_id="buyer_b", side="buy", quantity=200, price=9.9),
                order(event_id="ask_1", agent_id="seller_a", side="sell", quantity=300, price=10.2),
            ]
        )
        batch = engine.match_orders(TICK)

        self.assertEqual(batch.trades, [])
        view = engine.lob_view("demo_stock").to_dict()
        self.assertEqual(view["bids"], [["9.9", 300]])
        self.assertEqual(view["asks"], [["10.2", 300]])

    def test_price_time_priority_uses_best_price_then_oldest_resting_order(self) -> None:
        engine = self.build_engine()

        engine.submit_orders(
            [
                order(event_id="ask_old", agent_id="seller_a", side="sell", quantity=100, price=10.0),
                order(event_id="ask_better", agent_id="seller_b", side="sell", quantity=100, price=9.9),
                order(event_id="ask_new", agent_id="seller_c", side="sell", quantity=100, price=10.0),
            ]
        )
        engine.match_orders(TICK)
        engine.submit_orders(
            [order(event_id="buy_take", agent_id="buyer", side="buy", quantity=250, price=10.0)]
        )

        batch = engine.match_orders(TICK)

        self.assertEqual([trade.sell_order_id for trade in batch.trades], ["ask_better", "ask_old", "ask_new"])
        self.assertEqual([trade.quantity for trade in batch.trades], [100, 100, 50])
        self.assertEqual([trade.price for trade in batch.trades], [9.9, 10.0, 10.0])
        self.assertEqual(engine.order_status("ask_new").remaining_quantity, 50)
        self.assertEqual(engine.order_status("buy_take").status, "filled")

    def test_partial_fill_leaves_remainder_on_lob(self) -> None:
        engine = self.build_engine()

        engine.submit_orders(
            [
                order(event_id="ask_small", agent_id="seller", side="sell", quantity=100, price=10.0),
                order(event_id="buy_big", agent_id="buyer", side="buy", quantity=250, price=10.0),
            ]
        )
        batch = engine.match_orders(TICK)

        self.assertEqual(len(batch.trades), 1)
        self.assertEqual(batch.trades[0].quantity, 100)
        self.assertEqual(engine.order_status("buy_big").filled_quantity, 100)
        self.assertEqual(engine.order_status("buy_big").remaining_quantity, 150)
        self.assertEqual(engine.lob_view("demo_stock").to_dict()["bids"], [["10", 150]])

    def test_forced_liquidation_has_same_tick_priority_over_normal_order(self) -> None:
        engine = self.build_engine()

        engine.submit_orders(
            [
                order(event_id="bid_a", agent_id="buyer_a", side="buy", quantity=100, price=10.0),
                order(event_id="bid_b", agent_id="buyer_b", side="buy", quantity=100, price=10.0),
            ]
        )
        engine.match_orders(TICK)
        engine.submit_orders(
            [
                order(event_id="normal_sell", agent_id="seller_normal", side="sell", quantity=100, price=10.0),
                order(
                    event_id="forced_sell",
                    agent_id="seller_forced",
                    side="sell",
                    quantity=100,
                    price=None,
                    order_type="market",
                    time_in_force="ioc",
                    order_kind="forced_liquidation",
                ),
            ]
        )

        batch = engine.match_orders(TICK)

        self.assertEqual([trade.sell_order_id for trade in batch.trades], ["forced_sell", "normal_sell"])
        self.assertEqual([trade.buy_order_id for trade in batch.trades], ["bid_a", "bid_b"])

    def test_forced_liquidation_from_non_orchestrator_is_rejected(self) -> None:
        engine = self.build_engine()

        result = engine.submit_orders(
            [
                order(
                    event_id="bad_forced",
                    agent_id="seller",
                    side="sell",
                    quantity=100,
                    price=None,
                    order_type="market",
                    time_in_force="ioc",
                    order_kind="forced_liquidation",
                    producer="agent_runtime",
                )
            ]
        )

        self.assertEqual(result.rejected_orders[0].reason_code, "invalid_schema")

    def test_trade_batch_is_schema_compatible(self) -> None:
        engine = self.build_engine()
        engine.submit_orders(
            [
                order(event_id="ask", agent_id="seller", side="sell", quantity=100, price=10.0),
                order(event_id="buy", agent_id="buyer", side="buy", quantity=100, price=10.0),
            ]
        )

        batch = engine.match_orders(TICK)
        parsed = TradeBatch.from_dict(batch.to_dict())

        self.assertEqual(parsed.schema_version, "v1")
        self.assertEqual(parsed.tick_id, TICK)
        self.assertEqual(parsed.trace_id, TRACE)
        self.assertEqual(parsed.trades[0].buy_order_id, "buy")
        self.assertEqual(parsed.trades[0].sell_order_id, "ask")
        self.assertNotIn("agent_id", parsed.to_dict()["trades"][0])

    def test_matching_registers_accepted_orders_for_clearing_house_compatibility(self) -> None:
        house = ClearingHouse()
        house.open_account(agent_id="buyer", cash=10_000.0)
        house.open_account(agent_id="seller", cash=0.0, positions={"demo_stock": 100})
        engine = self.build_engine(ledger=house)

        submit_result = engine.submit_orders(
            [
                order(event_id="sell", agent_id="seller", side="sell", quantity=100, price=10.0),
                order(event_id="buy", agent_id="buyer", side="buy", quantity=100, price=10.0),
            ]
        )
        self.assertEqual(submit_result.rejected_orders, [])
        batch = engine.match_orders(TICK)

        settlement = house.settle_trade_batch(batch)

        self.assertEqual(settlement.account_snapshots[0].agent_id, "buyer")
        self.assertEqual(settlement.account_snapshots[0].positions, {"demo_stock": 100})


if __name__ == "__main__":
    unittest.main()

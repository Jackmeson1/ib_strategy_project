import time
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.core.types import ExecutionResult, Order, OrderAction, OrderStatus, Trade
from src.execution.smart_executor import SmartOrder, SmartOrderExecutor


@pytest.mark.usefixtures("set_ib_account")
class TestBatching:
    def test_orders_batched_correctly(self, monkeypatch, fake_contract):
        ib = MagicMock()
        pm = MagicMock()
        config = MagicMock()
        contracts = {f"SYM{i}": fake_contract for i in range(5)}
        executor = SmartOrderExecutor(ib, pm, config, contracts)
        executor.max_parallel_orders = 2

        smart_orders = [
            SmartOrder(Order(symbol=f"SYM{i}", action=OrderAction.BUY, quantity=1))
            for i in range(5)
        ]

        batch_sizes = []

        def fake_parallel_batch(batch):
            batch_sizes.append(len(batch))
            return ExecutionResult(True, [], [], 0, 0.0, [])

        monkeypatch.setattr(executor, "_execute_parallel_batch", fake_parallel_batch)
        monkeypatch.setattr(pm, "get_portfolio_leverage", lambda: 1.0)
        monkeypatch.setattr(time, "sleep", lambda *_: None)

        executor._execute_smart_batches(smart_orders, target_leverage=1.0)

        assert batch_sizes == [2, 2, 1]


@pytest.mark.usefixtures("set_ib_account")
class TestRetryLogic:
    def test_retry_executes_again(self, monkeypatch, fake_contract, trade_factory):
        ib = MagicMock()
        pm = MagicMock()
        config = MagicMock()
        contracts = {"TEST": fake_contract}
        executor = SmartOrderExecutor(ib, pm, config, contracts)

        smart_order = SmartOrder(Order(symbol="TEST", action=OrderAction.BUY, quantity=1))
        smart_order.max_retries = 1

        trade = trade_factory()
        results = [None, trade]

        def fake_wait(_trade, _timeout):
            return results.pop(0)

        monkeypatch.setattr(executor, "_wait_for_fill", fake_wait)
        monkeypatch.setattr(executor, "_handle_partial_fill", lambda *args: False)
        monkeypatch.setattr(executor, "_create_ib_order", lambda *_: MagicMock())
        monkeypatch.setattr(time, "sleep", lambda *_: None)

        ib.placeOrder.return_value = MagicMock(order="o")

        result = executor._execute_single_smart_order(smart_order)

        assert result == trade
        assert ib.placeOrder.call_count == 2
        assert ib.cancelOrder.call_count >= 1


@pytest.mark.usefixtures("set_ib_account")
class TestMarginCheck:
    def test_margin_rejects_unsafe(self, monkeypatch, fake_contract):
        ib = MagicMock()
        pm = MagicMock()
        config = MagicMock()
        contracts = {"AAPL": fake_contract}
        executor = SmartOrderExecutor(ib, pm, config, contracts)

        pm.get_account_summary.return_value = {
            "AvailableFunds": 1000,
            "BuyingPower": 5000,
            "NetLiquidation": 10000,
        }
        pm.get_positions.return_value = {}

        ticker = MagicMock(last=20, close=20)
        ib.reqMktData.return_value = ticker

        margin = executor._check_margin_safety({"AAPL": 100})

        assert not margin.is_safe
        assert "Insufficient funds" in margin.warning_message

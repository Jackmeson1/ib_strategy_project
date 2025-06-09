import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from src.core.types import Order, OrderAction
from src.execution.batch_executor import BatchOrderExecutor


@pytest.fixture
def simple_executor(fake_contract):
    ib = MagicMock()
    pm = MagicMock()
    config = MagicMock()
    contracts = {"AAPL": fake_contract}
    executor = BatchOrderExecutor(ib, pm, config, contracts)
    return executor, ib, pm


def make_ticker(price):
    ticker = MagicMock()
    ticker.marketPrice.return_value = price
    return ticker


def test_check_batch_margin_safety_insufficient_funds(simple_executor, monkeypatch):
    executor, ib, pm = simple_executor
    order = Order(symbol="AAPL", action=OrderAction.BUY, quantity=10)
    pm.get_account_summary.return_value = {"AvailableFunds": 1000, "NetLiquidation": 2000}
    pm.get_positions.return_value = {}
    ib.reqMktData.return_value = make_ticker(100)
    monkeypatch.setattr("src.utils.delay.wait", lambda *_: None)

    result = executor._check_batch_margin_safety([order])

    assert not result
    ib.cancelMktData.assert_called_once_with(executor.contracts["AAPL"])


def test_create_smart_order_types(simple_executor, monkeypatch):
    executor, ib, pm = simple_executor
    ib.reqMktData.return_value = make_ticker(200)
    monkeypatch.setattr("src.utils.delay.wait", lambda *_: None)

    small_order = Order(symbol="AAPL", action=OrderAction.BUY, quantity=10)
    big_order = Order(symbol="AAPL", action=OrderAction.SELL, quantity=100)

    mo = executor._create_smart_order(small_order)
    lo = executor._create_smart_order(big_order)

    from ib_insync import LimitOrder, MarketOrder

    assert isinstance(mo, MarketOrder)
    assert isinstance(lo, LimitOrder)
    assert lo.lmtPrice == round(200 * 0.998, 2)


def test_compile_results_builds_trades(simple_executor, monkeypatch):
    executor, ib, pm = simple_executor

    trade1 = MagicMock()
    trade1.contract.symbol = "AAPL"
    trade1.order.orderId = 1
    trade1.orderStatus.filled = 5
    trade1.orderStatus.avgFillPrice = 10
    trade1.commissionReport.commission = 1.0

    trade2 = MagicMock()
    trade2.contract.symbol = "AAPL"
    trade2.order.orderId = 2
    trade2.orderStatus.filled = 5
    trade2.orderStatus.avgFillPrice = 10
    trade2.commissionReport = None

    executor.completed_orders = {1: trade1, 2: trade2}
    executor.failed_orders = {3: "boom"}

    orders = [Order(symbol="AAPL", action=OrderAction.BUY, quantity=10)]

    class DummyTrade:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setattr("src.execution.batch_executor.Trade", DummyTrade)

    res = executor._compile_results(orders, start_time=time.time() - 1, success=True)

    assert res.success
    assert len(res.orders_placed) == 2
    assert res.total_commission == 1.0
    assert "boom" in res.errors[0]


def test_monitor_single_order_immediate_fill(simple_executor, monkeypatch):
    executor, ib, pm = simple_executor
    trade = MagicMock()
    trade.order.orderId = 1
    trade.contract.symbol = "AAPL"
    trade.orderStatus.filled = 10
    trade.order.totalQuantity = 10
    trade.orderStatus.avgFillPrice = 100
    trade.isDone.return_value = True
    monkeypatch.setattr("src.utils.delay.wait", lambda *_: None)
    monkeypatch.setattr(executor, "_validate_fill", lambda *args, **kwargs: True)
    assert executor._monitor_single_order(trade)


def test_cleanup_monitoring(simple_executor):
    executor, ib, pm = simple_executor
    executor.active_orders = {1: object()}
    executor.completed_orders = {1: object()}
    executor.failed_orders = {1: "err"}
    executor._monitor_active = True
    dummy_exec = MagicMock()
    executor._executor = dummy_exec
    executor._cleanup_monitoring()
    assert executor.active_orders == {}
    assert executor.completed_orders == {}
    assert executor.failed_orders == {}
    dummy_exec.shutdown.assert_called()


def test_fire_all_orders_places_orders(simple_executor, monkeypatch):
    executor, ib, pm = simple_executor
    ib.placeOrder.return_value = MagicMock()
    ib.reqMktData.return_value = make_ticker(50)
    monkeypatch.setattr("src.utils.delay.wait", lambda *_: None)
    order = Order(symbol="AAPL", action=OrderAction.BUY, quantity=1)
    result = executor._fire_all_orders([order])
    assert len(result) == 1
    ib.placeOrder.assert_called_once()


def test_monitor_all_orders_success(simple_executor, monkeypatch):
    executor, ib, pm = simple_executor
    trade = MagicMock()
    trade.order.orderId = 1
    trade.contract.symbol = "AAPL"

    class DummyFuture:
        def result(self):
            return True

    class DummyExecutor:
        def __init__(self, *args, **kwargs):
            pass

        def submit(self, fn, trade):
            return DummyFuture()

        def shutdown(self, wait=False):
            pass

    monkeypatch.setattr("src.execution.batch_executor.ThreadPoolExecutor", DummyExecutor)
    monkeypatch.setattr("src.execution.batch_executor.as_completed", lambda fs, timeout=None: fs)
    monkeypatch.setattr(executor, "_monitor_single_order", lambda t: True)
    monkeypatch.setattr("src.utils.delay.wait", lambda *_: None)

    assert executor._monitor_all_orders([trade])


def test_check_batch_margin_safety_success(simple_executor, monkeypatch):
    executor, ib, pm = simple_executor
    order = Order(symbol="AAPL", action=OrderAction.BUY, quantity=1)
    pm.get_account_summary.return_value = {"AvailableFunds": 100000, "NetLiquidation": 200000}
    pm.get_positions.return_value = {}
    ib.reqMktData.return_value = make_ticker(50)
    monkeypatch.setattr("src.utils.delay.wait", lambda *_: None)
    assert executor._check_batch_margin_safety([order])


def test_monitor_single_order_partial_fill(simple_executor, monkeypatch):
    executor, ib, _ = simple_executor
    trade = MagicMock()
    trade.order.orderId = 1
    trade.contract.symbol = "AAPL"
    trade.order.totalQuantity = 10
    trade.orderStatus.filled = 5
    trade.orderStatus.avgFillPrice = 50
    trade.isDone.side_effect = [False, False, True]
    monkeypatch.setattr("src.utils.delay.wait", lambda *_: None)
    monkeypatch.setattr(executor, "_validate_fill", lambda *args, **kwargs: True)
    assert executor._monitor_single_order(trade)


def test_monitor_single_order_thread_safe(simple_executor, monkeypatch):
    """Ensure _monitor_single_order can run in a background thread."""
    executor, ib, _ = simple_executor
    trade = MagicMock()
    trade.order.orderId = 1
    trade.contract.symbol = "AAPL"
    trade.order.totalQuantity = 1
    trade.orderStatus.filled = 1
    trade.orderStatus.avgFillPrice = 100
    trade.isDone.return_value = True

    monkeypatch.setattr("src.utils.delay.wait", lambda *_: None)
    monkeypatch.setattr(executor, "_validate_fill", lambda *a, **k: True)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(executor._monitor_single_order, trade)
        result = future.result()

    assert result

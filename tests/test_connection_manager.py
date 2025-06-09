import time
from unittest.mock import MagicMock

import pytest

from src.core import connection as connection_module
from src.core.types import Order, OrderAction
from src.execution.batch_executor import BatchOrderExecutor
from src.execution.smart_executor import SmartOrder, SmartOrderExecutor


@pytest.mark.usefixtures("set_ib_account")
def test_connection_retry_backoff(monkeypatch):
    config = MagicMock(host="h", port=1, client_id=1, account_id="A")

    attempts = []
    sleep_times = []

    class FakeEvent(list):
        def __iadd__(self, other):
            self.append(other)
            return self

    class FakeIB:
        def __init__(self):
            self.disconnectedEvent = FakeEvent()

        def connect(self, host, port, clientId, timeout):
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("fail")

        def managedAccounts(self):
            return ["TEST"]

        def isConnected(self):
            return True

        def disconnect(self):
            pass

    monkeypatch.setattr(connection_module, "IB", FakeIB)
    monkeypatch.setattr(connection_module.time, "sleep", lambda s: sleep_times.append(s))

    manager = connection_module.IBConnectionManager(config, max_retries=2, backoff_base=1)
    manager.connect(timeout=0)

    assert len(attempts) == 3
    assert sleep_times == [1, 2]


@pytest.mark.usefixtures("set_ib_account")
def test_batch_executor_cancel_on_disconnect(fake_contract):
    ib = MagicMock()
    pm = MagicMock()
    config = MagicMock()
    executor = BatchOrderExecutor(ib, pm, config, {})

    trade = MagicMock()
    trade.order.orderId = 1
    executor.active_orders = {1: trade}

    executor._on_ib_disconnect()

    ib.cancelOrder.assert_called_with(trade.order)
    assert not executor.active_orders


@pytest.mark.usefixtures("set_ib_account")
def test_smart_executor_cancel_on_disconnect(fake_contract):
    ib = MagicMock()
    pm = MagicMock()
    config = MagicMock()
    executor = SmartOrderExecutor(ib, pm, config, {})

    smart_order = SmartOrder(Order(symbol="A", action=OrderAction.BUY, quantity=1))
    trade = MagicMock()
    trade.order.orderId = 1
    smart_order.ib_trades = [trade]
    executor.active_orders = {"A": smart_order}

    executor._on_ib_disconnect()

    ib.cancelOrder.assert_called_with(trade.order)
    assert not executor.active_orders
    assert smart_order.retry_count > smart_order.max_retries

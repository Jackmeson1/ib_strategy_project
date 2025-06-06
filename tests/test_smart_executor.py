import time
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.execution.smart_executor import SmartOrderExecutor, SmartOrder
from src.core.types import Order, OrderAction, OrderStatus, Trade


@pytest.mark.usefixtures("set_ib_account")
class TestSmartOrderExecutorParallel:
    def test_parallel_batch_concurrency(self, monkeypatch):
        """_execute_parallel_batch should run orders concurrently."""
        ib = MagicMock()
        pm = MagicMock()
        config = MagicMock()
        contracts = {}

        executor = SmartOrderExecutor(ib, pm, config, contracts)
        executor.max_parallel_orders = 2

        smart_orders = [
            SmartOrder(Order(symbol=f"SYM{i}", action=OrderAction.BUY, quantity=1))
            for i in range(4)
        ]

        def fake_exec(order, timeout):
            time.sleep(0.2)
            return Trade(
                order_id=1,
                symbol=order.base_order.symbol,
                action=order.base_order.action,
                quantity=order.base_order.quantity,
                fill_price=1.0,
                commission=0,
                timestamp=datetime.now(),
                status=OrderStatus.FILLED,
            )

        monkeypatch.setattr(executor, "_execute_single_smart_order_with_timeout", fake_exec)

        start = time.time()
        result = executor._execute_parallel_batch(smart_orders)
        duration = time.time() - start

        assert duration < 0.6
        assert len(result.orders_placed) == 4
        assert not result.orders_failed


@pytest.fixture
def set_ib_account(monkeypatch):
    monkeypatch.setenv("IB_ACCOUNT_ID", "TEST")
    yield

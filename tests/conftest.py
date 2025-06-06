import os
import sys

# Ensure project root is on sys.path for tests
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Provide required environment variable for configuration loading during tests
os.environ.setdefault("IB_ACCOUNT_ID", "TEST")
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.core.types import OrderAction, OrderStatus, Trade


@pytest.fixture
def fake_contract():
    contract = MagicMock()
    contract.symbol = "TEST"
    return contract


@pytest.fixture
def trade_factory():
    def _factory(symbol="TEST", action=OrderAction.BUY, quantity=1, price=100.0, order_id=1):
        return Trade(
            order_id=order_id,
            symbol=symbol,
            action=action,
            quantity=quantity,
            fill_price=price,
            commission=0.0,
            timestamp=datetime.now(),
            status=OrderStatus.FILLED,
        )

    return _factory


@pytest.fixture
def set_ib_account(monkeypatch):
    monkeypatch.setenv("IB_ACCOUNT_ID", "TEST")
    yield

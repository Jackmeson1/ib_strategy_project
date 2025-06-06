from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.config.settings import Config
from src.core.types import Order, OrderAction
from src.execution.batch_executor import BatchOrderExecutor
from src.portfolio.manager import PortfolioManager

from tests.mock_gateway import MockIBGateway


@pytest.fixture
def mock_ib():
    account_summary = {
        "NetLiquidation": 10000,
        "GrossPositionValue": 5000,
        "AvailableFunds": 8000,
        "MaintMarginReq": 1000,
        "InitMarginReq": 1000,
    }
    positions = [
        SimpleNamespace(
            contract=SimpleNamespace(symbol="AAPL"),
            position=10,
            account="TEST",
            averageCost=100,
            marketValue=1000,
            unrealizedPNL=0.0,
        )
    ]
    market_prices = {"AAPL": 100}
    return MockIBGateway(account_summary, positions, market_prices)


@pytest.fixture
def portfolio_manager(mock_ib, set_ib_account):
    config = Config()
    market_data = MagicMock()
    market_data.get_fx_rate.return_value = 1
    contracts = {"AAPL": SimpleNamespace(symbol="AAPL")}
    return PortfolioManager(mock_ib, market_data, config, contracts)


@pytest.mark.usefixtures("set_ib_account")
def test_portfolio_manager_end_to_end(portfolio_manager):
    summary = portfolio_manager.get_account_summary()
    positions = portfolio_manager.get_positions(force_refresh=True)
    leverage = portfolio_manager.get_portfolio_leverage()

    assert summary["NetLiquidation"] == 10000
    assert "AAPL" in positions
    assert positions["AAPL"].quantity == 10
    assert leverage == pytest.approx(0.5)


@pytest.mark.usefixtures("set_ib_account")
def test_batch_order_executor_end_to_end(mock_ib, portfolio_manager):
    config = Config()
    contracts = {"AAPL": SimpleNamespace(symbol="AAPL")}
    executor = BatchOrderExecutor(mock_ib, portfolio_manager, config, contracts)

    order = Order(symbol="AAPL", action=OrderAction.BUY, quantity=5)
    result = executor.execute_batch([order])

    assert result.success
    assert len(result.orders_placed) == 1
    assert not result.orders_failed

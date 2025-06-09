from unittest.mock import MagicMock

import pytest

from src.core.types import OrderAction, Position
from src.portfolio.manager import PortfolioManager


def build_portfolio_item(symbol, position, avg_cost, account):
    item = MagicMock()
    item.position = position
    item.account = account
    item.contract.symbol = symbol
    item.marketValue = None
    item.unrealizedPNL = None
    item.averageCost = avg_cost
    return item


@pytest.fixture
def manager_instance():
    ib = MagicMock()
    market_data = MagicMock()
    config = MagicMock()
    config.ib.account_id = "TEST"
    config.accounts = []
    contracts = {"AAPL": MagicMock()}
    pm = PortfolioManager(ib, market_data, config, contracts)
    return pm, ib, market_data


def test_get_positions_fallback_to_avg_cost(manager_instance):
    pm, ib, _ = manager_instance
    ib.portfolio.return_value = [build_portfolio_item("AAPL", 10, 50, "TEST")]

    positions = pm.get_positions(force_refresh=True)

    assert positions["AAPL"].current_price == 50
    assert positions["AAPL"].market_value == 500


def test_check_margin_safety_threshold(manager_instance):
    pm, _, _ = manager_instance
    pm.config.strategy.safety_threshold = 0.2
    pm.get_account_summary = MagicMock(
        return_value={
            "NetLiquidation": 1000,
            "AvailableFunds": 100,
            "MaintMarginReq": 500,
            "InitMarginReq": 300,
        }
    )

    safe, metrics = pm.check_margin_safety()

    assert not safe
    assert metrics["safety_ratio"] == 0.1


def test_get_portfolio_leverage_conversion(manager_instance):
    pm, _, md = manager_instance
    pm.get_account_summary = MagicMock(
        return_value={"GrossPositionValue": 2000, "NetLiquidation": 1000}
    )
    md.get_fx_rate.return_value = 2

    leverage = pm.get_portfolio_leverage()

    assert leverage == 2.0

def test_get_portfolio_leverage_zero_nlv(manager_instance):
    pm, _, md = manager_instance
    pm.get_account_summary = MagicMock(return_value={"GrossPositionValue": 0, "NetLiquidation": 0})
    md.get_fx_rate.return_value = 1
    assert pm.get_portfolio_leverage() == 0.0

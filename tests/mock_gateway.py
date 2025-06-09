from types import SimpleNamespace
from typing import Dict, List, Optional


class MockTicker:
    """Simple market data ticker used by :class:`MockIBGateway`."""

    def __init__(self, price: float):
        self.last = price
        self.close = price
        self.bid = price - 0.1
        self.ask = price + 0.1
        self.volume = 100

    def marketPrice(self) -> float:
        return self.last

    def midpoint(self) -> float:
        return (self.bid + self.ask) / 2


class MockTrade:
    """Simplified trade object mirroring ib_insync.Trade."""

    def __init__(self, order, contract, fill_price: float):
        self.order = order
        self.contract = contract
        self.orderStatus = SimpleNamespace(
            filled=order.totalQuantity,
            avgFillPrice=fill_price,
            status="Filled",
        )
        self.commissionReport = None

    def isDone(self) -> bool:
        return True


class MockIBGateway:
    """Reusable mock of the ``ib_insync.IB`` client for tests.

    It returns deterministic market data, account information and trade fills so
    end-to-end flows can be tested without a real Interactive Brokers session.
    """

    def __init__(
        self,
        account_summary: Optional[Dict[str, float]] = None,
        positions: Optional[List[SimpleNamespace]] = None,
        market_prices: Optional[Dict[str, float]] = None,
    ) -> None:
        self.account_summary = account_summary or {}
        self.positions = positions or []
        self.market_prices = market_prices or {}
        self._order_id = 1

    # --- IB account/portfolio APIs -------------------------------------------------
    def accountSummary(self, account: str = "") -> List[SimpleNamespace]:
        return [SimpleNamespace(tag=k, value=str(v)) for k, v in self.account_summary.items()]

    def portfolio(self) -> List[SimpleNamespace]:
        return self.positions

    # --- Market data APIs -----------------------------------------------------------
    def reqMktData(self, contract, *args, **kwargs) -> MockTicker:
        price = self.market_prices.get(contract.symbol, 100)
        return MockTicker(price)

    def cancelMktData(self, _ticker) -> None:  # pragma: no cover - noop
        return None

    # --- Order APIs ----------------------------------------------------------------
    def placeOrder(self, contract, order) -> MockTrade:
        order.orderId = self._order_id
        self._order_id += 1
        price = self.market_prices.get(contract.symbol, 100)
        return MockTrade(order, contract, price)

    def cancelOrder(self, _order) -> None:  # pragma: no cover - noop
        return None

    # --- Utility methods -----------------------------------------------------------
    def sleep(self, _seconds: float) -> None:  # pragma: no cover - noop
        return None

    def isConnected(self) -> bool:
        return True

    def managedAccounts(self) -> List[str]:  # pragma: no cover - simple list
        return ["TEST"]

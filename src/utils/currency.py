from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type hints
    from src.data.market_data import MarketDataManager


def convert(amount: float, from_currency: str, to_currency: str, market_data: MarketDataManager) -> float:
    """Convert amount between currencies using market data FX rates."""
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    if from_currency == to_currency:
        return amount
    rate = market_data.get_fx_rate(from_currency=from_currency, to_currency=to_currency)
    return amount / rate

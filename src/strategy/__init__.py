"""Strategy module."""
from src.strategy.fixed_leverage import FixedLeverageStrategy
from src.strategy.vix_leverage import VIXLeverageStrategy

__all__ = ["FixedLeverageStrategy", "VIXLeverageStrategy"]

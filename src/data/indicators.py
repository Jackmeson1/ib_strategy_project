"""
Technical indicators module with support for various moving averages.
"""
from abc import ABC, abstractmethod
from typing import Optional, Union

import numpy as np
import pandas as pd

from src.core.types import MAType
from src.utils.logger import get_logger


class Indicator(ABC):
    """Base class for technical indicators."""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = get_logger(__name__)
    
    @abstractmethod
    def calculate(self, data: pd.Series) -> pd.Series:
        """Calculate the indicator values."""
        pass


class MovingAverage(Indicator):
    """Base class for moving averages."""
    
    def __init__(self, window: int, ma_type: MAType):
        super().__init__(f"{ma_type.value}_{window}")
        self.window = window
        self.ma_type = ma_type


class SimpleMovingAverage(MovingAverage):
    """Simple Moving Average (SMA)."""
    
    def __init__(self, window: int):
        super().__init__(window, MAType.SMA)
    
    def calculate(self, data: pd.Series) -> pd.Series:
        """Calculate SMA."""
        return data.rolling(window=self.window).mean()


class ExponentialMovingAverage(MovingAverage):
    """Exponential Moving Average (EMA)."""
    
    def __init__(self, window: int):
        super().__init__(window, MAType.EMA)
    
    def calculate(self, data: pd.Series) -> pd.Series:
        """Calculate EMA."""
        return data.ewm(span=self.window, adjust=False).mean()


class WeightedMovingAverage(MovingAverage):
    """Weighted Moving Average (WMA)."""
    
    def __init__(self, window: int):
        super().__init__(window, MAType.WMA)
    
    def calculate(self, data: pd.Series) -> pd.Series:
        """Calculate WMA."""
        def wma(values: pd.Series, window: int):
            weights = np.arange(1, window + 1)
            return values.rolling(window).apply(
                lambda x: (x * weights).sum() / weights.sum(),
                raw=True
            )
        return wma(data, self.window)


class HullMovingAverage(MovingAverage):
    """Hull Moving Average (HMA) - faster and smoother."""
    
    def __init__(self, window: int):
        super().__init__(window, MAType.HMA)
    
    def calculate(self, data: pd.Series) -> pd.Series:
        """Calculate HMA."""
        # HMA = WMA(2*WMA(n/2) - WMA(n), sqrt(n))
        half_window = max(int(self.window / 2), 1)
        sqrt_window = max(int(np.sqrt(self.window)), 1)
        
        wma = WeightedMovingAverage(self.window)
        wma_half = WeightedMovingAverage(half_window)
        wma_sqrt = WeightedMovingAverage(sqrt_window)
        
        # Calculate components
        wma_full = wma.calculate(data)
        wma_half_values = wma_half.calculate(data)
        
        # HMA formula
        hma_pre = 2 * wma_half_values - wma_full
        hma = wma_sqrt.calculate(hma_pre)
        
        return hma


class IndicatorFactory:
    """Factory for creating indicators."""
    
    @staticmethod
    def create_moving_average(ma_type: Union[str, MAType], window: int) -> MovingAverage:
        """
        Create a moving average indicator.
        
        Args:
            ma_type: Type of moving average
            window: Period for the moving average
            
        Returns:
            MovingAverage instance
        """
        if isinstance(ma_type, str):
            ma_type = MAType(ma_type.upper())
        
        if ma_type == MAType.SMA:
            return SimpleMovingAverage(window)
        elif ma_type == MAType.EMA:
            return ExponentialMovingAverage(window)
        elif ma_type == MAType.WMA:
            return WeightedMovingAverage(window)
        elif ma_type == MAType.HMA:
            return HullMovingAverage(window)
        else:
            raise ValueError(f"Unsupported moving average type: {ma_type}")

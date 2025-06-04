"""
Technical indicators module with support for various moving averages.
"""
from abc import ABC, abstractmethod
from typing import Optional, Union

import numpy as np
import pandas as pd

from src.core.types import MAType, VIXData
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


class VIXIndicator:
    """VIX-based indicators for volatility analysis."""
    
    def __init__(self, ma_type: Union[str, MAType] = MAType.SMA, ma_window: int = 10):
        self.ma_type = MAType(ma_type) if isinstance(ma_type, str) else ma_type
        self.ma_window = ma_window
        self.logger = get_logger(__name__)
        self.ma_indicator = IndicatorFactory.create_moving_average(self.ma_type, ma_window)
    
    def calculate_vix_ma(self, vix_data: pd.DataFrame) -> Optional[VIXData]:
        """
        Calculate VIX moving average.
        
        Args:
            vix_data: DataFrame with 'date' and 'close' columns
            
        Returns:
            VIXData with calculated MA, or None if insufficient data
        """
        if vix_data is None or len(vix_data) < self.ma_window:
            self.logger.warning(f"Insufficient VIX data for {self.ma_type.value}{self.ma_window}")
            return None
        
        # Calculate moving average
        vix_series = vix_data['close']
        ma_series = self.ma_indicator.calculate(vix_series)
        
        # Handle NaN values from MA calculation
        ma_series = ma_series.bfill()  # Backward fill for initial values
        
        # Get latest values
        latest_date = vix_data['date'].iloc[-1]
        latest_close = vix_series.iloc[-1]
        latest_ma = ma_series.iloc[-1]
        
        if pd.isna(latest_ma):
            self.logger.error("VIX MA calculation resulted in NaN")
            return None
        
        return VIXData(
            date=latest_date,
            close=latest_close,
            ma_value=latest_ma,
            ma_type=self.ma_type,
            ma_window=self.ma_window
        )
    
    def calculate_vix_percentile(self, vix_data: pd.DataFrame, lookback_days: int = 252) -> float:
        """
        Calculate VIX percentile rank over lookback period.
        
        Args:
            vix_data: DataFrame with VIX data
            lookback_days: Number of days to look back
            
        Returns:
            Percentile rank (0-100)
        """
        if len(vix_data) < lookback_days:
            lookback_days = len(vix_data)
        
        recent_data = vix_data.tail(lookback_days)
        current_vix = vix_data['close'].iloc[-1]
        
        percentile = (recent_data['close'] < current_vix).sum() / len(recent_data) * 100
        return percentile
    
    def calculate_vix_zscore(self, vix_data: pd.DataFrame, lookback_days: int = 20) -> float:
        """
        Calculate VIX z-score.
        
        Args:
            vix_data: DataFrame with VIX data
            lookback_days: Number of days for mean/std calculation
            
        Returns:
            Z-score
        """
        if len(vix_data) < lookback_days:
            return 0.0
        
        recent_data = vix_data['close'].tail(lookback_days)
        current_vix = vix_data['close'].iloc[-1]
        
        mean = recent_data.mean()
        std = recent_data.std()
        
        if std == 0:
            return 0.0
        
        return (current_vix - mean) / std 
"""
Tests for technical indicators module.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.core.types import MAType
from src.data.indicators import (
    SimpleMovingAverage, ExponentialMovingAverage,
    HullMovingAverage, IndicatorFactory
)


class TestMovingAverages:
    """Test moving average calculations."""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample price data."""
        dates = pd.date_range(start='2023-01-01', periods=20, freq='D')
        prices = [10, 11, 12, 11, 13, 14, 13, 12, 14, 15,
                  16, 15, 14, 16, 17, 18, 17, 16, 18, 19]
        return pd.Series(prices, index=dates)
    
    def test_sma_calculation(self, sample_data):
        """Test Simple Moving Average calculation."""
        sma = SimpleMovingAverage(window=5)
        result = sma.calculate(sample_data)
        
        # Check that we have the right number of values
        assert len(result) == len(sample_data)
        
        # Check that first 4 values are NaN (window=5)
        assert result.iloc[:4].isna().all()
        
        # Check specific calculation
        # For index 4: (10+11+12+11+13)/5 = 11.4
        assert result.iloc[4] == pytest.approx(11.4)
    
    def test_ema_calculation(self, sample_data):
        """Test Exponential Moving Average calculation."""
        ema = ExponentialMovingAverage(window=5)
        result = ema.calculate(sample_data)
        
        # EMA should not have NaN values (uses expanding window initially)
        assert not result.isna().any()
        
        # EMA should react faster to recent changes than SMA
        sma = SimpleMovingAverage(window=5)
        sma_result = sma.calculate(sample_data)
        
        # In an uptrend, EMA should be higher than SMA
        assert result.iloc[-1] > sma_result.iloc[-1]
    
    def test_hma_calculation(self, sample_data):
        """Test Hull Moving Average calculation."""
        hma = HullMovingAverage(window=9)
        result = hma.calculate(sample_data)
        
        # HMA uses complex calculation, so just verify it produces values
        assert len(result) == len(sample_data)
        assert not result.iloc[-5:].isna().any()  # Last 5 values should be valid


class TestIndicatorFactory:
    """Test indicator factory."""
    
    def test_create_sma(self):
        """Test creating SMA through factory."""
        indicator = IndicatorFactory.create_moving_average("SMA", 10)
        assert isinstance(indicator, SimpleMovingAverage)
        assert indicator.window == 10
        assert indicator.ma_type == MAType.SMA
    
    def test_create_ema(self):
        """Test creating EMA through factory."""
        indicator = IndicatorFactory.create_moving_average(MAType.EMA, 20)
        assert isinstance(indicator, ExponentialMovingAverage)
        assert indicator.window == 20
    
    def test_invalid_ma_type(self):
        """Test invalid MA type raises error."""
        with pytest.raises(ValueError):
            IndicatorFactory.create_moving_average("INVALID", 10)



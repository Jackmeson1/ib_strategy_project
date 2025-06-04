"""
Tests for technical indicators module.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.core.types import MAType, VIXData
from src.data.indicators import (
    SimpleMovingAverage, ExponentialMovingAverage,
    HullMovingAverage, VIXIndicator, IndicatorFactory
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


class TestVIXIndicator:
    """Test VIX indicator calculations."""
    
    @pytest.fixture
    def vix_data(self):
        """Create sample VIX data."""
        dates = pd.date_range(start='2023-01-01', periods=30, freq='D')
        # Simulate VIX values oscillating between 12 and 25
        vix_values = 18.5 + 6.5 * np.sin(np.linspace(0, 4*np.pi, 30))
        df = pd.DataFrame({
            'date': dates,
            'close': vix_values
        })
        return df
    
    def test_vix_ma_calculation(self, vix_data):
        """Test VIX MA calculation."""
        indicator = VIXIndicator(ma_type="SMA", ma_window=10)
        result = indicator.calculate_vix_ma(vix_data)
        
        assert isinstance(result, VIXData)
        assert result.ma_type == MAType.SMA
        assert result.ma_window == 10
        assert result.date == vix_data['date'].iloc[-1]
        assert result.close == vix_data['close'].iloc[-1]
        assert isinstance(result.ma_value, float)
    
    def test_vix_ma_insufficient_data(self):
        """Test VIX MA with insufficient data."""
        # Create data with only 5 points
        dates = pd.date_range(start='2023-01-01', periods=5, freq='D')
        df = pd.DataFrame({
            'date': dates,
            'close': [15, 16, 14, 15, 17]
        })
        
        indicator = VIXIndicator(ma_type="SMA", ma_window=10)
        result = indicator.calculate_vix_ma(df)
        
        assert result is None  # Should return None for insufficient data
    
    def test_vix_percentile(self, vix_data):
        """Test VIX percentile calculation."""
        indicator = VIXIndicator()
        percentile = indicator.calculate_vix_percentile(vix_data, lookback_days=20)
        
        assert 0 <= percentile <= 100
        
        # Test with current value at max
        vix_data_copy = vix_data.copy()
        vix_data_copy.loc[vix_data_copy.index[-1], 'close'] = 100
        percentile_max = indicator.calculate_vix_percentile(vix_data_copy, lookback_days=20)
        assert percentile_max > 90  # Should be near 100th percentile
    
    def test_vix_zscore(self, vix_data):
        """Test VIX z-score calculation."""
        indicator = VIXIndicator()
        zscore = indicator.calculate_vix_zscore(vix_data, lookback_days=20)
        
        # Z-score should typically be between -3 and 3
        assert -4 < zscore < 4
        
        # Test with extreme value
        vix_data_copy = vix_data.copy()
        mean = vix_data_copy['close'].tail(20).mean()
        std = vix_data_copy['close'].tail(20).std()
        vix_data_copy.loc[vix_data_copy.index[-1], 'close'] = mean + 2 * std
        
        zscore_high = indicator.calculate_vix_zscore(vix_data_copy, lookback_days=20)
        assert zscore_high > 1.5  # Should be significantly positive 
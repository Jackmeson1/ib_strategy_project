"""
Market data management with caching and error handling.
"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
from ib_insync import IB, Contract, Forex, Stock, MarketOrder

from src.core.exceptions import MarketDataError, TemporaryError
from src.core.types import MarketData
from src.utils.logger import get_logger


class MarketDataManager:
    """Manages market data retrieval with caching."""
    
    def __init__(self, ib: IB, cache_ttl_seconds: int = 300):
        self.ib = ib
        self.logger = get_logger(__name__)
        self.cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, tuple[any, datetime]] = {}
        self._price_cache: Dict[str, MarketData] = {}
    
    def _is_cache_valid(self, cache_time: datetime) -> bool:
        """Check if cached data is still valid."""
        return (datetime.now() - cache_time) < timedelta(seconds=self.cache_ttl)
    
    def _get_from_cache(self, key: str) -> Optional[any]:
        """Get data from cache if valid."""
        if key in self._cache:
            data, cache_time = self._cache[key]
            if self._is_cache_valid(cache_time):
                self.logger.debug(f"Cache hit for {key}")
                return data
        return None
    
    def _set_cache(self, key: str, data: any):
        """Set data in cache."""
        self._cache[key] = (data, datetime.now())
    
    def clear_cache(self):
        """Clear all cached data."""
        self._cache.clear()
        self._price_cache.clear()
        self.logger.info("Market data cache cleared")
    
    def get_fx_rate(self, from_currency: str = "USD", to_currency: str = "CAD") -> float:
        """
        Get foreign exchange rate.
        
        Args:
            from_currency: Base currency
            to_currency: Quote currency
            
        Returns:
            Exchange rate
            
        Raises:
            MarketDataError: If unable to get FX rate
        """
        cache_key = f"fx_{from_currency}{to_currency}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached
        
        try:
            fx_contract = Forex(f"{from_currency}{to_currency}")
            self.ib.qualifyContracts(fx_contract)
            
            ticker = self.ib.reqMktData(fx_contract, '', False, False)
            start_time = time.time()
            timeout = 10
            
            while time.time() - start_time < timeout:
                self.ib.sleep(0.5)
                
                # Try midpoint first
                if ticker.midpoint() and ticker.midpoint() > 0:
                    rate = ticker.midpoint()
                    self._set_cache(cache_key, rate)
                    self.logger.info(f"FX rate {from_currency}/{to_currency}: {rate:.4f}")
                    return rate
                
                # Try bid/ask
                if ticker.bid and ticker.ask and ticker.bid > 0 and ticker.ask > 0:
                    rate = (ticker.bid + ticker.ask) / 2
                    self._set_cache(cache_key, rate)
                    self.logger.info(f"FX rate {from_currency}/{to_currency}: {rate:.4f} (from bid/ask)")
                    return rate
                
                # Try last price
                if ticker.last and ticker.last > 0:
                    rate = ticker.last
                    self._set_cache(cache_key, rate)
                    self.logger.info(f"FX rate {from_currency}/{to_currency}: {rate:.4f} (last)")
                    return rate
            
            raise MarketDataError(f"Unable to get FX rate for {from_currency}/{to_currency} - market may be closed")
            
        except Exception as e:
            self.logger.error(f"Failed to get FX rate: {e}")
            raise MarketDataError(f"Failed to get FX rate: {e}")
    
    def get_market_price(self, contract: Contract, timeout: int = 10) -> float:
        """
        Get current market price for a contract.
        
        Args:
            contract: IB contract
            timeout: Timeout in seconds
            
        Returns:
            Market price
            
        Raises:
            MarketDataError: If unable to get price
        """
        symbol = contract.symbol
        cache_key = f"price_{symbol}"
        
        # Check cache
        if symbol in self._price_cache:
            cached_data = self._price_cache[symbol]
            if self._is_cache_valid(cached_data.timestamp):
                if cached_data.midpoint:
                    return cached_data.midpoint
                elif cached_data.last:
                    return cached_data.last
        
        try:
            ticker = self.ib.reqMktData(contract)
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                self.ib.sleep(0.5)
                
                market_data = MarketData(
                    symbol=symbol,
                    bid=ticker.bid,
                    ask=ticker.ask,
                    last=ticker.last,
                    volume=ticker.volume,
                    timestamp=datetime.now()
                )
                
                # Try to get a valid price
                if ticker.midpoint() and ticker.midpoint() > 0:
                    self._price_cache[symbol] = market_data
                    self.logger.debug(f"Price for {symbol}: {ticker.midpoint():.2f} (midpoint)")
                    return ticker.midpoint()
                
                if ticker.marketPrice() and ticker.marketPrice() > 0:
                    self._price_cache[symbol] = market_data
                    self.logger.debug(f"Price for {symbol}: {ticker.marketPrice():.2f} (market)")
                    return ticker.marketPrice()
                
                if ticker.last and ticker.last > 0:
                    self._price_cache[symbol] = market_data
                    self.logger.debug(f"Price for {symbol}: {ticker.last:.2f} (last)")
                    return ticker.last
            
            raise MarketDataError(f"Unable to get price for {symbol} - market may be closed")
            
        except Exception as e:
            self.logger.error(f"Failed to get price for {symbol}: {e}")
            raise MarketDataError(f"Failed to get price for {symbol}: {e}")
    
    def get_market_prices_batch(self, contracts: List[Contract], max_workers: int = 5) -> Dict[str, float]:
        """
        Get market prices for multiple contracts in parallel.
        
        Args:
            contracts: List of IB contracts
            max_workers: Maximum concurrent requests
            
        Returns:
            Dictionary of symbol to price
        """
        prices = {}
        
        # Process in batches to avoid overwhelming the API
        for i in range(0, len(contracts), max_workers):
            batch = contracts[i:i + max_workers]
            tickers = []
            
            # Request market data for batch
            for contract in batch:
                ticker = self.ib.reqMktData(contract)
                tickers.append((contract.symbol, ticker))
            
            # Wait for data
            self.ib.sleep(2)
            
            # Collect prices
            for symbol, ticker in tickers:
                try:
                    if ticker.midpoint() and ticker.midpoint() > 0:
                        prices[symbol] = ticker.midpoint()
                    elif ticker.last and ticker.last > 0:
                        prices[symbol] = ticker.last
                    else:
                        self.logger.warning(f"No valid price for {symbol}")
                except Exception as e:
                    self.logger.error(f"Error getting price for {symbol}: {e}")
            
            # Cancel market data subscriptions
            for _, ticker in tickers:
                self.ib.cancelMktData(ticker)
        
        return prices 
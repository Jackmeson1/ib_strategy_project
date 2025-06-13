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
from src.utils.delay import wait


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
                wait(0.5, self.ib)
                
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
            # Request market data with snapshot enabled for better data retrieval
            ticker = self.ib.reqMktData(contract, '', True, False)
            self.logger.debug(f"Requesting market data for {symbol}")
            
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                wait(0.1, self.ib)  # Shorter wait for more responsive checking
                
                # Log current ticker state for debugging
                self.logger.debug(f"{symbol}: bid={ticker.bid}, ask={ticker.ask}, last={ticker.last}, close={ticker.close}")
                
                # Try multiple price sources in order of preference
                price = None
                price_type = None
                
                # 1. Try midpoint (bid+ask)/2
                if ticker.bid and ticker.ask and ticker.bid > 0 and ticker.ask > 0:
                    price = (ticker.bid + ticker.ask) / 2
                    price_type = "midpoint"
                
                # 2. Try last trade price
                elif ticker.last and ticker.last > 0:
                    price = ticker.last
                    price_type = "last"
                
                # 3. Try close price (previous day)
                elif ticker.close and ticker.close > 0:
                    price = ticker.close
                    price_type = "close"
                
                # 4. Try market price function
                elif ticker.marketPrice() and ticker.marketPrice() > 0:
                    price = ticker.marketPrice()
                    price_type = "market"
                
                if price and price > 0:
                    market_data = MarketData(
                        symbol=symbol,
                        bid=ticker.bid,
                        ask=ticker.ask,
                        last=ticker.last,
                        volume=ticker.volume,
                        timestamp=datetime.now()
                    )
                    
                    self._price_cache[symbol] = market_data
                    self.logger.info(f"Price for {symbol}: ${price:.2f} ({price_type})")
                    self.ib.cancelMktData(contract)  # Clean up subscription
                    return price
            
            # Clean up even if no price found
            self.ib.cancelMktData(contract)
            raise MarketDataError(f"Unable to get price for {symbol} after {timeout}s timeout")
            
        except Exception as e:
            # Make sure to clean up subscription on error
            try:
                self.ib.cancelMktData(contract)
            except:
                pass
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
        
        # Use individual requests for more reliable data retrieval
        self.logger.info(f"Requesting prices for {len(contracts)} contracts")
        
        for contract in contracts:
            try:
                # Use the improved individual price method
                price = self.get_market_price(contract, timeout=5)
                prices[contract.symbol] = price
                self.logger.debug(f"Got price for {contract.symbol}: ${price:.2f}")
            except MarketDataError as e:
                self.logger.warning(f"No price for {contract.symbol}: {e}")
            except Exception as e:
                self.logger.error(f"Error getting price for {contract.symbol}: {e}")
        
        self.logger.info(f"Successfully retrieved {len(prices)}/{len(contracts)} prices")
        return prices 
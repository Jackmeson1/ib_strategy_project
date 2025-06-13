#!/usr/bin/env python3
"""
Debug market data issues - test direct market data retrieval.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from ib_insync import Stock
from src.config.settings import load_config
from src.core.connection import create_connection_manager
from src.data.market_data import MarketDataManager


async def debug_market_data():
    """Debug market data retrieval issues."""
    print("🐛 Debugging market data retrieval...")
    
    try:
        config = load_config()
        connection_manager = create_connection_manager(config)
        ib = await connection_manager.connect()
        
        if not ib.isConnected():
            print("❌ Failed to connect to IB")
            return
            
        print("✅ Connected to IB")
        
        # Test direct IB market data
        print("\n📊 Testing direct IB market data...")
        aapl = Stock("AAPL", "SMART", "USD")
        ib.qualifyContracts(aapl)
        
        # Request market data directly
        ticker = ib.reqMktData(aapl, "", False, False)
        print(f"📊 Ticker created: {ticker}")
        
        # Wait for data
        for i in range(10):
            print(f"📊 Attempt {i+1}: Checking ticker data...")
            
            # Let IB process events
            await asyncio.sleep(1)
            
            print(f"   Bid: {ticker.bid}")
            print(f"   Ask: {ticker.ask}")
            print(f"   Last: {ticker.last}")
            print(f"   Market Price: {ticker.marketPrice()}")
            print(f"   Midpoint: {ticker.midpoint()}")
            print(f"   Time: {ticker.time}")
            
            if ticker.bid and ticker.ask:
                print(f"✅ Got market data: Bid={ticker.bid}, Ask={ticker.ask}")
                break
                
            if ticker.last and ticker.last > 0:
                print(f"✅ Got last price: {ticker.last}")
                break
        else:
            print("❌ No market data received after 10 attempts")
        
        # Test MarketDataManager
        print("\n🔧 Testing MarketDataManager...")
        market_data = MarketDataManager(ib)
        
        try:
            price = market_data.get_market_price(aapl, timeout=10)
            print(f"✅ MarketDataManager price: ${price:.2f}")
        except Exception as e:
            print(f"❌ MarketDataManager failed: {e}")
        
        # Test different symbols
        print("\n📈 Testing multiple symbols...")
        symbols = ['MSFT', 'NVDA', 'GLD', 'SPY']
        
        for symbol in symbols:
            try:
                contract = Stock(symbol, "SMART", "USD")
                ib.qualifyContracts(contract)
                
                # Quick market data test
                ticker = ib.reqMktData(contract, "", False, False)
                await asyncio.sleep(2)
                
                if ticker.bid or ticker.ask or ticker.last:
                    price = ticker.marketPrice() or ticker.last or ticker.midpoint()
                    print(f"✅ {symbol}: ${price:.2f}")
                else:
                    print(f"❌ {symbol}: No data")
                    
                ib.cancelMktData(contract)
                    
            except Exception as e:
                print(f"❌ {symbol}: Error - {e}")
        
        await connection_manager.disconnect()
        
    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_market_data())
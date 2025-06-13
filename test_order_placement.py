#!/usr/bin/env python3
"""
Test script to verify actual order placement on TWS paper account.
This will place a small test order to verify TWS integration.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ib_insync import Stock, MarketOrder, LimitOrder
from src.config.settings import load_config
from src.core.connection import create_connection_manager
from src.data.market_data import MarketDataManager


async def test_order_placement():
    """Test placing a small order on TWS paper account."""
    print("🧪 Testing actual order placement on TWS paper account...")
    
    try:
        config = load_config()
        print(f"📋 Account: {config.ib.account_id}")
        print(f"📋 Base currency: {config.accounts[0].base_currency}")
        
        connection_manager = create_connection_manager(config)
        ib = await connection_manager.connect()
        
        if not ib.isConnected():
            print("❌ Failed to connect to IB")
            return False
            
        print("✅ Connected to IB")
        
        # Create a small test order for AAPL
        symbol = "AAPL"
        contract = Stock(symbol, "SMART", "USD")
        ib.qualifyContracts(contract)
        
        # Get current market price
        market_data = MarketDataManager(ib)
        try:
            current_price = market_data.get_market_price(contract, timeout=10)
            print(f"💰 Current {symbol} price: ${current_price:.2f}")
        except Exception as e:
            print(f"⚠️ Could not get market price: {e}")
            current_price = 200.0  # Fallback price
        
        # Create a small limit order to buy 1 share
        # Set limit price slightly below market to avoid immediate execution
        limit_price = current_price * 0.95  # 5% below market
        
        order = LimitOrder(
            action="BUY",
            totalQuantity=1,
            lmtPrice=round(limit_price, 2)
        )
        
        print(f"📤 Placing test order: BUY 1 {symbol} @ ${limit_price:.2f}")
        
        # Place the order
        trade = ib.placeOrder(contract, order)
        
        if trade:
            print(f"✅ Order placed successfully!")
            print(f"📊 Order ID: {trade.order.orderId}")
            print(f"📊 Order Status: {trade.orderStatus.status}")
            
            # Wait a few seconds to see initial status
            for i in range(10):
                await asyncio.sleep(1)
                print(f"📊 Status update {i+1}: {trade.orderStatus.status}")
                
                if trade.orderStatus.status in ['Filled', 'Cancelled']:
                    break
            
            # Cancel the order if it's still pending
            if trade.orderStatus.status in ['Submitted', 'PreSubmitted']:
                print("🔄 Cancelling test order...")
                ib.cancelOrder(trade.order)
                await asyncio.sleep(2)
                print(f"📊 Final status: {trade.orderStatus.status}")
            
            print("\n📋 Order Summary:")
            print(f"   Order ID: {trade.order.orderId}")
            print(f"   Symbol: {symbol}")
            print(f"   Action: {trade.order.action}")
            print(f"   Quantity: {trade.order.totalQuantity}")
            print(f"   Limit Price: ${trade.order.lmtPrice}")
            print(f"   Status: {trade.orderStatus.status}")
            print(f"   Filled: {trade.orderStatus.filled}")
            
            return True
            
        else:
            print("❌ Failed to place order")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
        
    finally:
        if 'connection_manager' in locals():
            await connection_manager.disconnect()


async def main():
    """Run the order placement test."""
    print("🚀 Starting TWS order placement test...\n")
    
    print("⚠️  IMPORTANT: This test will place a real order on your paper account!")
    print("⚠️  Make sure TWS is running and connected to paper trading.")
    print("⚠️  The order will be cancelled automatically after testing.\n")
    
    try:
        result = await test_order_placement()
        
        if result:
            print("\n🎉 Test completed successfully!")
            print("📋 Check your TWS interface to see the order activity.")
            print("📋 You should see the order in the 'Orders' tab in TWS.")
        else:
            print("\n❌ Test failed. Check the error messages above.")
            
        return result
        
    except Exception as e:
        print(f"\n💥 Test crashed: {e}")
        return False


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
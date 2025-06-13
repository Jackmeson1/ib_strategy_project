#!/usr/bin/env python3
"""
Simple test to place a manual order and verify TWS integration.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()

import asyncio
from ib_insync import Stock, MarketOrder
from src.config.settings import load_config
from src.core.connection import create_connection_manager


async def test_simple_order():
    """Test placing a simple order to verify TWS integration."""
    print("🧪 Testing simple order placement...")
    
    try:
        config = load_config()
        print(f"Account: {config.ib.account_id}")
        
        connection_manager = create_connection_manager(config)
        ib = await connection_manager.connect()
        
        if not ib.isConnected():
            print("❌ Failed to connect to IB")
            return
            
        print("✅ Connected to IB")
        
        # Create a simple contract
        contract = Stock("AAPL", "SMART", "USD")
        ib.qualifyContracts(contract)
        print(f"✅ Contract qualified: {contract}")
        
        # Check market data permissions first
        print("\n📊 Checking market data...")
        ticker = ib.reqMktData(contract, "", False, False)
        
        # Wait a bit for data
        for i in range(5):
            await asyncio.sleep(1)
            print(f"Attempt {i+1}: bid={ticker.bid}, ask={ticker.ask}, last={ticker.last}")
            
            if ticker.bid or ticker.ask or ticker.last:
                print("✅ Got some market data!")
                break
        else:
            print("⚠️ No market data - might be permissions issue or market closed")
        
        # Get account info
        account_summary = ib.accountSummary()
        for item in account_summary:
            if item.tag in ['NetLiquidation', 'AvailableFunds']:
                print(f"💰 {item.tag}: {item.value} {item.currency}")
        
        # Place a small test order (1 share, limit order way below market)
        print("\n📤 Placing test order...")
        
        # Use a very low limit price to avoid execution
        limit_price = 100.0  # Way below AAPL market price
        
        order = MarketOrder(
            action="BUY",
            totalQuantity=1
        )
        
        print(f"📤 Placing BUY 1 AAPL market order...")
        
        # Place the order
        trade = ib.placeOrder(contract, order)
        
        if trade:
            print(f"✅ Order placed successfully!")
            print(f"📊 Order ID: {trade.order.orderId}")
            print(f"📊 Initial Status: {trade.orderStatus.status}")
            
            # Monitor for a few seconds
            for i in range(10):
                await asyncio.sleep(1)
                print(f"📊 Status update {i+1}: {trade.orderStatus.status}")
                
                if trade.orderStatus.status in ['Filled', 'Cancelled']:
                    print(f"🎯 Order completed with status: {trade.orderStatus.status}")
                    break
                    
                if trade.orderStatus.filled > 0:
                    print(f"📈 Partial fill: {trade.orderStatus.filled} shares")
            
            # If still pending, cancel it
            if trade.orderStatus.status in ['Submitted', 'PreSubmitted']:
                print("🔄 Cancelling test order...")
                ib.cancelOrder(trade.order)
                await asyncio.sleep(2)
                print(f"📊 Final status: {trade.orderStatus.status}")
            
            print(f"\n📋 Final Order Details:")
            print(f"   Order ID: {trade.order.orderId}")
            print(f"   Status: {trade.orderStatus.status}")
            print(f"   Filled: {trade.orderStatus.filled}")
            print(f"   Remaining: {trade.orderStatus.remaining}")
            
            return True
            
        else:
            print("❌ Failed to place order")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        if 'connection_manager' in locals():
            await connection_manager.disconnect()


if __name__ == "__main__":
    success = asyncio.run(test_simple_order())
    print(f"\n{'🎉 Test PASSED' if success else '❌ Test FAILED'}")
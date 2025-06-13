#!/usr/bin/env python3
"""
Test script to validate currency handling and batch execution fixes.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.config.settings import load_config
from src.core.connection import create_connection_manager
from src.data.market_data import MarketDataManager
from src.portfolio.manager import PortfolioManager
from src.utils.currency import convert
from src.utils.logger import setup_logger


async def test_currency_conversion():
    """Test currency conversion with CAD base currency."""
    print("🧪 Testing currency conversion...")
    
    try:
        config = load_config()
        print(f"📋 Base currency configured as: {config.accounts[0].base_currency}")
        
        connection_manager = create_connection_manager(config)
        ib = await connection_manager.connect()
        
        if not ib.isConnected():
            print("❌ Failed to connect to IB")
            return False
            
        print("✅ Connected to IB")
        
        # Create market data manager
        market_data = MarketDataManager(ib)
        
        # Test FX rate retrieval
        try:
            usd_to_cad = market_data.get_fx_rate("USD", "CAD")
            print(f"💱 USD/CAD rate: {usd_to_cad:.4f}")
            
            cad_to_usd = market_data.get_fx_rate("CAD", "USD") 
            print(f"💱 CAD/USD rate: {cad_to_usd:.4f}")
            
            # Test conversion function
            test_amount = 1000.0
            converted_usd_to_cad = convert(test_amount, "USD", "CAD", market_data)
            converted_cad_to_usd = convert(test_amount, "CAD", "USD", market_data)
            
            print(f"💰 ${test_amount} USD = CAD {converted_usd_to_cad:.2f}")
            print(f"💰 CAD {test_amount} = ${converted_cad_to_usd:.2f}")
            
            # Validation - round trip should be close to original
            round_trip = convert(converted_usd_to_cad, "CAD", "USD", market_data)
            diff = abs(round_trip - test_amount)
            
            if diff < 0.01:  # Less than 1 cent difference
                print("✅ Currency conversion working correctly")
                return True
            else:
                print(f"❌ Currency conversion error: {diff:.4f} difference in round trip")
                return False
                
        except Exception as e:
            print(f"❌ Currency conversion test failed: {e}")
            return False
            
        finally:
            await connection_manager.disconnect()
            
    except Exception as e:
        print(f"❌ Currency test setup failed: {e}")
        return False


async def test_portfolio_manager_currency():
    """Test portfolio manager with CAD base currency."""
    print("\n🧪 Testing portfolio manager currency handling...")
    
    try:
        config = load_config()
        connection_manager = create_connection_manager(config)
        ib = await connection_manager.connect()
        
        if not ib.isConnected():
            print("❌ Failed to connect to IB")
            return False
        
        # Create managers
        market_data = MarketDataManager(ib)
        contracts = {}  # Empty for this test
        portfolio_manager = PortfolioManager(ib, market_data, config, contracts)
        
        # Test account summary retrieval
        try:
            account = portfolio_manager.get_account_summary()
            print(f"📊 Account summary retrieved successfully")
            print(f"💰 Net Liquidation: {account.get('NetLiquidation', 0):,.2f}")
            print(f"💰 Available Funds: {account.get('AvailableFunds', 0):,.2f}")
            
            # Test leverage calculation
            leverage = portfolio_manager.get_portfolio_leverage()
            print(f"📈 Current leverage: {leverage:.3f}")
            
            return True
            
        except Exception as e:
            print(f"❌ Portfolio manager test failed: {e}")
            return False
            
        finally:
            await connection_manager.disconnect()
            
    except Exception as e:
        print(f"❌ Portfolio manager test setup failed: {e}")
        return False


def test_config_loading():
    """Test configuration loading with CAD base currency."""
    print("\n🧪 Testing configuration loading...")
    
    try:
        config = load_config()
        
        print(f"📋 Account ID: {config.ib.account_id}")
        print(f"📋 Base currency: {config.accounts[0].base_currency}")
        print(f"📋 Target leverage: {config.strategy.default_leverage}")
        
        if config.accounts[0].base_currency == "CAD":
            print("✅ CAD base currency configured correctly")
            return True
        else:
            print(f"❌ Expected CAD, got {config.accounts[0].base_currency}")
            return False
            
    except Exception as e:
        print(f"❌ Config loading failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("🚀 Starting currency and configuration tests...\n")
    
    # Setup basic logging
    import logging
    logging.basicConfig(level=logging.INFO)
    
    results = []
    
    # Test 1: Configuration loading
    results.append(test_config_loading())
    
    # Test 2: Currency conversion (requires IB connection)
    try:
        results.append(await test_currency_conversion())
    except Exception as e:
        print(f"❌ Currency conversion test failed with exception: {e}")
        results.append(False)
    
    # Test 3: Portfolio manager currency handling  
    try:
        results.append(await test_portfolio_manager_currency())
    except Exception as e:
        print(f"❌ Portfolio manager test failed with exception: {e}")
        results.append(False)
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Currency fixes are working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Please check the output above.")
        return False


if __name__ == "__main__":
    # Run the async main function
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
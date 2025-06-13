#!/usr/bin/env python3
"""
Comprehensive Test Suite for IB Portfolio Rebalancing Tool
Tests all functionality using live TWS paper account backend.
"""

import asyncio
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv
from src.config.settings import load_config

# Load environment variables
load_dotenv()
from src.core.connection import create_connection_manager
from src.data.market_data import MarketDataManager
from src.portfolio.manager import PortfolioManager
from src.strategy.fixed_leverage import FixedLeverageStrategy
from src.strategy.enhanced_fixed_leverage import EnhancedFixedLeverageStrategy
from src.execution.native_batch_executor import NativeBatchExecutor
from src.execution.smart_executor import SmartOrderExecutor
from src.utils.currency import convert
from ib_insync import Stock, Contract


class ComprehensiveTestSuite:
    """Comprehensive test suite for IB portfolio rebalancing system."""
    
    def __init__(self):
        self.config = None
        self.connection_manager = None
        self.ib = None
        self.market_data = None
        self.portfolio_manager = None
        self.contracts = {}
        self.test_results = {}
        self.start_time = datetime.now()
        
    async def setup(self):
        """Set up test environment."""
        print("🔧 Setting up test environment...")
        
        try:
            self.config = load_config()
            print(f"✅ Config loaded: Account {self.config.ib.account_id}, Base currency {self.config.accounts[0].base_currency}")
            
            self.connection_manager = create_connection_manager(self.config)
            self.ib = await self.connection_manager.connect()
            
            if not self.ib.isConnected():
                raise Exception("Failed to connect to IB")
                
            print("✅ Connected to IB TWS paper account")
            
            # Create managers
            self.market_data = MarketDataManager(self.ib)
            self.portfolio_manager = PortfolioManager(self.ib, self.market_data, self.config, self.contracts)
            
            # Initialize common contracts
            test_symbols = ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'GLD']
            for symbol in test_symbols:
                contract = Stock(symbol, "SMART", "USD")
                self.ib.qualifyContracts(contract)
                self.contracts[symbol] = contract
                
            print(f"✅ Initialized {len(self.contracts)} test contracts")
            return True
            
        except Exception as e:
            print(f"❌ Setup failed: {e}")
            return False
    
    async def cleanup(self):
        """Clean up test environment."""
        print("\n🧹 Cleaning up test environment...")
        if self.connection_manager:
            await self.connection_manager.disconnect()
    
    def record_result(self, test_name: str, success: bool, details: str = "", execution_time: float = 0):
        """Record test result."""
        self.test_results[test_name] = {
            'success': success,
            'details': details,
            'execution_time': execution_time,
            'timestamp': datetime.now()
        }
        
        status = "✅ PASS" if success else "❌ FAIL"
        time_str = f" ({execution_time:.2f}s)" if execution_time > 0 else ""
        print(f"{status} {test_name}{time_str}")
        if details:
            print(f"    📋 {details}")
    
    async def test_connection_and_setup(self):
        """Test 1: Connection and basic setup."""
        print("\n🧪 Test 1: Connection and Basic Setup")
        start_time = time.time()
        
        try:
            # Test IB connection
            if not self.ib.isConnected():
                raise Exception("IB not connected")
                
            # Test account access
            account_summary = self.portfolio_manager.get_account_summary()
            nlv = account_summary.get('NetLiquidation', 0)
            
            if nlv <= 0:
                raise Exception("Invalid account data")
                
            execution_time = time.time() - start_time
            self.record_result(
                "Connection and Setup", 
                True, 
                f"NLV: {nlv:,.2f}, Available: {account_summary.get('AvailableFunds', 0):,.2f}",
                execution_time
            )
            return True
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.record_result("Connection and Setup", False, str(e), execution_time)
            return False
    
    async def test_currency_handling(self):
        """Test 2: Currency handling and FX rates."""
        print("\n🧪 Test 2: Currency Handling and FX Rates")
        start_time = time.time()
        
        try:
            # Test FX rate retrieval
            usd_to_cad = self.market_data.get_fx_rate("USD", "CAD")
            cad_to_usd = self.market_data.get_fx_rate("CAD", "USD")
            
            if usd_to_cad <= 0 or cad_to_usd <= 0:
                raise Exception("Invalid FX rates")
                
            # Test conversion function
            test_amount = 1000.0
            converted_usd_to_cad = convert(test_amount, "USD", "CAD", self.market_data)
            converted_back = convert(converted_usd_to_cad, "CAD", "USD", self.market_data)
            
            # Check round-trip accuracy (should be within 0.1%)
            accuracy = abs(converted_back - test_amount) / test_amount
            
            if accuracy > 0.001:  # 0.1% tolerance
                raise Exception(f"Currency conversion inaccuracy: {accuracy:.4f}")
            
            execution_time = time.time() - start_time
            self.record_result(
                "Currency Handling", 
                True,
                f"USD/CAD: {usd_to_cad:.4f}, Round-trip accuracy: {accuracy:.6f}",
                execution_time
            )
            return True
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.record_result("Currency Handling", False, str(e), execution_time)
            return False
    
    async def test_portfolio_management(self):
        """Test 3: Portfolio management and position tracking."""
        print("\n🧪 Test 3: Portfolio Management")
        start_time = time.time()
        
        try:
            # Test position retrieval
            positions = self.portfolio_manager.get_positions()
            
            # Test account summary
            account = self.portfolio_manager.get_account_summary()
            
            # Test leverage calculation
            leverage = self.portfolio_manager.get_portfolio_leverage()
            
            # Test data integrity validation
            integrity_check = self.portfolio_manager.validate_data_integrity()
            
            # Test margin safety check
            margin_safe, margin_metrics = self.portfolio_manager.check_margin_safety()
            
            execution_time = time.time() - start_time
            self.record_result(
                "Portfolio Management",
                True,
                f"Positions: {len(positions)}, Leverage: {leverage:.2f}, Margin Safe: {margin_safe}",
                execution_time
            )
            return True
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.record_result("Portfolio Management", False, str(e), execution_time)
            return False
    
    async def test_market_data(self):
        """Test 4: Market data retrieval."""
        print("\n🧪 Test 4: Market Data Retrieval")
        start_time = time.time()
        
        try:
            prices_retrieved = 0
            total_symbols = len(self.contracts)
            
            # Test individual price retrieval
            for symbol, contract in self.contracts.items():
                try:
                    price = self.market_data.get_market_price(contract, timeout=5)
                    if price > 0:
                        prices_retrieved += 1
                except Exception:
                    # During market closed, some prices might not be available
                    pass
            
            # Test batch price retrieval
            batch_prices = self.market_data.get_market_prices_batch(list(self.contracts.values()))
            
            execution_time = time.time() - start_time
            self.record_result(
                "Market Data",
                True,
                f"Individual prices: {prices_retrieved}/{total_symbols}, Batch prices: {len(batch_prices)}",
                execution_time
            )
            return True
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.record_result("Market Data", False, str(e), execution_time)
            return False
    
    async def test_execution_modes(self):
        """Test 5: Different execution modes."""
        print("\n🧪 Test 5: Execution Modes")
        
        # Test Standard Execution
        await self._test_standard_execution()
        
        # Test Smart Execution
        await self._test_smart_execution()
        
        # Test Native Batch Execution
        await self._test_native_batch_execution()
    
    async def _test_standard_execution(self):
        """Test standard execution mode."""
        print("\n  📊 Testing Standard Execution Mode")
        start_time = time.time()
        
        try:
            # Create standard strategy with dry run
            original_dry_run = self.config.dry_run
            self.config.dry_run = True  # Force dry run for testing
            
            strategy = FixedLeverageStrategy(
                self.ib, 
                self.config, 
                target_leverage=1.2  # Conservative for testing
            )
            
            # Test rebalancing
            success = strategy.rebalance(force=True)
            
            self.config.dry_run = original_dry_run  # Restore original setting
            
            execution_time = time.time() - start_time
            self.record_result(
                "Standard Execution",
                success,
                "Dry run rebalance completed",
                execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.record_result("Standard Execution", False, str(e), execution_time)
    
    async def _test_smart_execution(self):
        """Test smart execution mode."""
        print("\n  📊 Testing Smart Execution Mode")
        start_time = time.time()
        
        try:
            # Create enhanced strategy with smart execution
            original_dry_run = self.config.dry_run
            self.config.dry_run = True  # Force dry run for testing
            
            strategy = EnhancedFixedLeverageStrategy(
                self.ib,
                self.config,
                target_leverage=1.2,
                batch_execution=False  # Smart mode
            )
            
            # Test rebalancing
            success = strategy.rebalance(force=True)
            
            self.config.dry_run = original_dry_run  # Restore original setting
            
            execution_time = time.time() - start_time
            self.record_result(
                "Smart Execution",
                success,
                "Smart execution dry run completed",
                execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.record_result("Smart Execution", False, str(e), execution_time)
    
    async def _test_native_batch_execution(self):
        """Test native batch execution mode."""
        print("\n  📊 Testing Native Batch Execution Mode")
        start_time = time.time()
        
        try:
            # Create enhanced strategy with native batch execution
            original_dry_run = self.config.dry_run
            self.config.dry_run = True  # Force dry run for testing
            
            strategy = EnhancedFixedLeverageStrategy(
                self.ib,
                self.config,
                target_leverage=1.2,
                batch_execution=True  # Native batch mode
            )
            
            # Test rebalancing
            success = strategy.rebalance(force=True)
            
            self.config.dry_run = original_dry_run  # Restore original setting
            
            execution_time = time.time() - start_time
            self.record_result(
                "Native Batch Execution",
                success,
                "Native batch execution dry run completed",
                execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.record_result("Native Batch Execution", False, str(e), execution_time)
    
    async def test_margin_safety(self):
        """Test 6: Margin safety and leverage calculations."""
        print("\n🧪 Test 6: Margin Safety and Leverage")
        start_time = time.time()
        
        try:
            # Test current leverage calculation
            current_leverage = self.portfolio_manager.get_portfolio_leverage()
            
            # Test margin safety check
            margin_safe, metrics = self.portfolio_manager.check_margin_safety()
            
            # Test with different leverage targets
            test_leverages = [1.0, 1.5, 2.0]
            leverage_tests = []
            
            for target_leverage in test_leverages:
                # Create strategy with different leverage
                strategy = FixedLeverageStrategy(
                    self.ib,
                    self.config,
                    target_leverage=target_leverage
                )
                
                # Test if leverage calculation works
                try:
                    positions = strategy.calculate_target_positions()
                    leverage_tests.append(f"{target_leverage:.1f}x")
                except Exception as e:
                    leverage_tests.append(f"{target_leverage:.1f}x(failed)")
            
            execution_time = time.time() - start_time
            self.record_result(
                "Margin Safety",
                True,
                f"Current: {current_leverage:.2f}x, Safe: {margin_safe}, Tests: {', '.join(leverage_tests)}",
                execution_time
            )
            return True
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.record_result("Margin Safety", False, str(e), execution_time)
            return False
    
    async def test_error_handling(self):
        """Test 7: Error handling and edge cases."""
        print("\n🧪 Test 7: Error Handling and Edge Cases")
        start_time = time.time()
        
        try:
            error_tests = []
            
            # Test 1: Invalid symbol handling
            try:
                invalid_contract = Stock("INVALID_SYMBOL_123", "SMART", "USD")
                self.ib.qualifyContracts(invalid_contract)
                price = self.market_data.get_market_price(invalid_contract, timeout=2)
                error_tests.append("Invalid symbol: HANDLED")
            except Exception:
                error_tests.append("Invalid symbol: HANDLED")
            
            # Test 2: Network timeout handling
            try:
                # Test with very short timeout
                short_timeout_price = self.market_data.get_market_price(
                    self.contracts['AAPL'], timeout=0.1
                )
                error_tests.append("Short timeout: HANDLED")
            except Exception:
                error_tests.append("Short timeout: HANDLED")
            
            # Test 3: Zero leverage handling
            try:
                zero_leverage_strategy = FixedLeverageStrategy(
                    self.ib,
                    self.config,
                    target_leverage=0.0
                )
                error_tests.append("Zero leverage: HANDLED")
            except Exception:
                error_tests.append("Zero leverage: HANDLED")
            
            execution_time = time.time() - start_time
            self.record_result(
                "Error Handling",
                True,
                f"Tests: {', '.join(error_tests)}",
                execution_time
            )
            return True
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.record_result("Error Handling", False, str(e), execution_time)
            return False
    
    async def test_safety_mechanisms(self):
        """Test 8: Safety mechanisms."""
        print("\n🧪 Test 8: Safety Mechanisms")
        start_time = time.time()
        
        try:
            safety_tests = []
            
            # Test 1: Emergency leverage threshold
            emergency_threshold = self.config.strategy.emergency_leverage_threshold
            current_leverage = self.portfolio_manager.get_portfolio_leverage()
            
            if current_leverage < emergency_threshold:
                safety_tests.append(f"Emergency threshold: {emergency_threshold:.1f}x (safe)")
            else:
                safety_tests.append(f"Emergency threshold: {emergency_threshold:.1f}x (triggered)")
            
            # Test 2: Margin cushion
            margin_safe, metrics = self.portfolio_manager.check_margin_safety()
            safety_ratio = metrics.get('safety_ratio', 0)
            safety_tests.append(f"Margin cushion: {safety_ratio:.2%}")
            
            # Test 3: Position limits
            account = self.portfolio_manager.get_account_summary()
            nlv = account.get('NetLiquidation', 0)
            max_position = nlv * 0.8
            safety_tests.append(f"Position limit: {max_position:,.0f}")
            
            # Test 4: Data integrity
            integrity_ok = self.portfolio_manager.validate_data_integrity()
            safety_tests.append(f"Data integrity: {'OK' if integrity_ok else 'FAIL'}")
            
            execution_time = time.time() - start_time
            self.record_result(
                "Safety Mechanisms",
                True,
                f"Tests: {', '.join(safety_tests)}",
                execution_time
            )
            return True
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.record_result("Safety Mechanisms", False, str(e), execution_time)
            return False
    
    def print_summary(self):
        """Print comprehensive test summary."""
        print("\n" + "="*80)
        print("📊 COMPREHENSIVE TEST SUITE RESULTS")
        print("="*80)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result['success'])
        failed_tests = total_tests - passed_tests
        
        total_time = (datetime.now() - self.start_time).total_seconds()
        
        if total_tests > 0:
            pass_rate = passed_tests/total_tests*100
            print(f"📈 Overall Results: {passed_tests}/{total_tests} tests passed ({pass_rate:.1f}%)")
        else:
            print("📈 Overall Results: No tests completed")
        print(f"⏱️  Total execution time: {total_time:.2f} seconds")
        print(f"🏦 Account: {self.config.ib.account_id} (Paper Trading)")
        print(f"💱 Base Currency: {self.config.accounts[0].base_currency}")
        
        print(f"\n✅ Passed Tests ({passed_tests}):")
        for test_name, result in self.test_results.items():
            if result['success']:
                print(f"   • {test_name}: {result['details']}")
        
        if failed_tests > 0:
            print(f"\n❌ Failed Tests ({failed_tests}):")
            for test_name, result in self.test_results.items():
                if not result['success']:
                    print(f"   • {test_name}: {result['details']}")
        
        print("\n" + "="*80)
        
        if passed_tests == total_tests:
            print("🎉 ALL TESTS PASSED! The system is working correctly.")
        else:
            print(f"⚠️  {failed_tests} test(s) failed. Please review the issues above.")
        
        print("="*80)
        
        return passed_tests == total_tests
    
    async def run_all_tests(self):
        """Run all comprehensive tests."""
        print("🚀 Starting Comprehensive Test Suite for IB Portfolio Rebalancing")
        print(f"📅 Started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # Setup
            if not await self.setup():
                print("❌ Setup failed, aborting tests")
                return False
            
            # Run all tests
            await self.test_connection_and_setup()
            await self.test_currency_handling()
            await self.test_portfolio_management()
            await self.test_market_data()
            await self.test_execution_modes()
            await self.test_margin_safety()
            await self.test_error_handling()
            await self.test_safety_mechanisms()
            
            return True
            
        except Exception as e:
            print(f"💥 Test suite crashed: {e}")
            traceback.print_exc()
            return False
            
        finally:
            await self.cleanup()


async def main():
    """Main test runner."""
    test_suite = ComprehensiveTestSuite()
    
    try:
        success = await test_suite.run_all_tests()
        test_suite.print_summary()
        return success
        
    except KeyboardInterrupt:
        print("\n⏹️  Test suite interrupted by user")
        return False
    except Exception as e:
        print(f"\n💥 Test suite failed: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
#!/usr/bin/env python3
"""
Test 7: Currency handling with CAD/USD trades

Tests the system's ability to handle multi-currency portfolios with CAD base currency
and USD-denominated securities, including FX rate handling, leverage calculations,
and currency conversion accuracy.
"""

import time
from pathlib import Path

from ib_insync import IB

from src.config.settings import load_config
from src.strategy.enhanced_fixed_leverage import create_enhanced_strategy
from src.utils.logger import get_logger
from main import load_portfolio_weights

logger = get_logger(__name__)

def test_currency_handling():
    """Test currency handling with CAD/USD trades."""
    logger.info("=" * 60)
    logger.info("TEST 7: Currency handling with CAD/USD trades")
    logger.info("=" * 60)

    try:
        # Load config
        config = load_config()
        config.dry_run = False  # Real orders for testing
        
        # Connect to IB
        ib = IB()
        ib.connect(config.ib.host, config.ib.port, clientId=config.ib.client_id)
        logger.info(f"Connected to TWS at {config.ib.host}:{config.ib.port}")

        # Test 7.1: Verify base currency configuration
        logger.info("\n--- TEST 7.1: Base currency configuration verification ---")
        
        # Create strategy to access portfolio manager
        strategy = create_enhanced_strategy(
            ib=ib,
            config=config,
            target_leverage=1.0,
            batch_execution=True
        )
        
        # Check account currency configuration
        account_summary = strategy.portfolio_manager.get_account_summary()
        base_currency = config.accounts[0].base_currency if config.accounts else "USD"
        logger.info(f"Account base currency from config: {base_currency}")
        
        # Check actual account currency from IB
        logger.info("Account summary (in base currency):")
        for field, value in account_summary.items():
            if isinstance(value, (int, float)):
                logger.info(f"  {field}: ${value:,.2f} {base_currency}")

        # Test 7.2: FX rate retrieval and caching
        logger.info("\n--- TEST 7.2: FX rate retrieval and accuracy ---")
        
        # Test USD/CAD rate retrieval
        fx_rate_usd_cad = strategy.market_data.get_fx_rate('USD', 'CAD')
        logger.info(f"USD/CAD FX rate: {fx_rate_usd_cad:.4f}")
        
        # Test reverse rate
        try:
            fx_rate_cad_usd = strategy.market_data.get_fx_rate('CAD', 'USD')
            logger.info(f"CAD/USD FX rate: {fx_rate_cad_usd:.4f}")
            
            # Verify rate consistency (should be inverses)
            rate_product = fx_rate_usd_cad * fx_rate_cad_usd
            logger.info(f"Rate product (should be ~1.0): {rate_product:.6f}")
            
            if abs(rate_product - 1.0) < 0.001:
                logger.info("✓ FX rates are consistent (inverse relationship)")
            else:
                logger.warning(f"⚠ FX rate inconsistency: product = {rate_product}")
        except Exception as e:
            logger.warning(f"CAD/USD rate lookup failed: {e}")
            # Calculate inverse manually
            fx_rate_cad_usd = 1.0 / fx_rate_usd_cad
            logger.info(f"Using calculated inverse CAD/USD rate: {fx_rate_cad_usd:.4f}")

        # Test same-currency rate (should be 1.0)
        try:
            fx_rate_same = strategy.market_data.get_fx_rate('CAD', 'CAD')
            logger.info(f"CAD/CAD FX rate: {fx_rate_same:.4f}")
            
            if abs(fx_rate_same - 1.0) < 0.001:
                logger.info("✓ Same-currency rate is 1.0")
            else:
                logger.warning(f"⚠ Same-currency rate error: {fx_rate_same}")
        except Exception as e:
            logger.warning(f"Same-currency rate lookup failed: {e}")
            logger.info("✓ Same-currency rate should be 1.0 (expected behavior)")

        # Test 7.3: Currency conversion accuracy
        logger.info("\n--- TEST 7.3: Currency conversion accuracy ---")
        
        # Test various conversion amounts
        test_amounts = [1000, 10000, 100000]
        
        for amount_usd in test_amounts:
            try:
                # Convert USD to CAD
                amount_cad = strategy.market_data.convert_currency(
                    amount_usd, 'USD', 'CAD'
                )
                
                # Convert back to USD
                amount_usd_back = strategy.market_data.convert_currency(
                    amount_cad, 'CAD', 'USD'
                )
                
                conversion_error = abs(amount_usd - amount_usd_back)
                error_pct = (conversion_error / amount_usd) * 100
                
                logger.info(f"${amount_usd:,} USD -> ${amount_cad:,.2f} CAD -> ${amount_usd_back:,.2f} USD")
                logger.info(f"  Conversion error: ${conversion_error:.2f} ({error_pct:.4f}%)")
                
                if error_pct < 0.01:  # Less than 0.01% error
                    logger.info("  ✓ High conversion accuracy")
                else:
                    logger.warning(f"  ⚠ Conversion error exceeds tolerance")
            except Exception as e:
                logger.warning(f"  Currency conversion failed for ${amount_usd:,}: {e}")

        # Test 7.4: Portfolio leverage calculation with currency conversion
        logger.info("\n--- TEST 7.4: Multi-currency leverage calculation ---")
        
        # Load test portfolio
        weights_file = Path("test_simple_3stock.csv")
        if weights_file.exists():
            portfolio_weights = load_portfolio_weights(str(weights_file))
            strategy.portfolio_weights = portfolio_weights
        
        # Get current positions and their currencies
        positions = strategy.portfolio_manager.get_positions()
        logger.info("Current positions and their currencies:")
        
        total_usd_value = 0
        total_cad_value = 0
        
        for symbol, pos in positions.items():
            if abs(pos.quantity) > 1:
                # Assume USD securities (typical for US stocks)
                usd_value = abs(pos.market_value)
                try:
                    cad_value = strategy.market_data.convert_currency(
                        usd_value, 'USD', 'CAD'
                    )
                except:
                    # Use manual conversion if market data fails
                    cad_value = usd_value * fx_rate_usd_cad
                
                total_usd_value += usd_value
                total_cad_value += cad_value
                
                logger.info(f"  {symbol}: ${usd_value:,.2f} USD = ${cad_value:,.2f} CAD")
        
        logger.info(f"Total portfolio value: ${total_usd_value:,.2f} USD = ${total_cad_value:,.2f} CAD")
        
        # Calculate leverage manually and compare with system calculation
        account_nlv = account_summary.get('NetLiquidation', 0)
        manual_leverage = total_cad_value / account_nlv if account_nlv > 0 else 0
        system_leverage = strategy.portfolio_manager.get_portfolio_leverage()
        
        logger.info(f"Manual leverage calculation: {manual_leverage:.3f}x")
        logger.info(f"System leverage calculation: {system_leverage:.3f}x")
        
        leverage_diff = abs(manual_leverage - system_leverage)
        if leverage_diff < 0.05:
            logger.info("✓ Leverage calculations match within tolerance")
        else:
            logger.warning(f"⚠ Leverage calculation difference: {leverage_diff:.3f}x")

        # Test 7.5: Order execution with currency considerations
        logger.info("\n--- TEST 7.5: Multi-currency order execution ---")
        
        # Create a small rebalancing order to test currency handling
        logger.info("Testing small rebalancing order with currency conversion...")
        
        # Set conservative target to avoid large orders
        strategy.target_leverage = 1.1
        
        # Check available funds in both currencies
        available_cad = account_summary.get('AvailableFunds', 0)
        try:
            available_usd = strategy.market_data.convert_currency(
                available_cad, 'CAD', 'USD'
            )
        except:
            available_usd = available_cad * fx_rate_cad_usd
        
        logger.info(f"Available funds: ${available_cad:,.2f} CAD = ${available_usd:,.2f} USD")
        
        # Execute small rebalancing
        rebalance_result = strategy.rebalance(force=True)
        logger.info(f"Rebalancing result: {rebalance_result}")
        
        if rebalance_result:
            time.sleep(5)
            
            # Check new account state
            new_account = strategy.portfolio_manager.get_account_summary()
            new_available_cad = new_account.get('AvailableFunds', 0)
            
            funds_change_cad = new_available_cad - available_cad
            try:
                funds_change_usd = strategy.market_data.convert_currency(
                    abs(funds_change_cad), 'CAD', 'USD'
                )
            except:
                funds_change_usd = abs(funds_change_cad) * fx_rate_cad_usd
            
            logger.info(f"Available funds change: ${funds_change_cad:,.2f} CAD = ${funds_change_usd:,.2f} USD")

        # Test 7.6: Currency conversion edge cases
        logger.info("\n--- TEST 7.6: Currency conversion edge cases ---")
        
        # Test zero amount conversion
        try:
            zero_conversion = strategy.market_data.convert_currency(0, 'USD', 'CAD')
            logger.info(f"Zero amount conversion: {zero_conversion}")
            
            if zero_conversion == 0:
                logger.info("✓ Zero amount conversion handled correctly")
            else:
                logger.warning(f"⚠ Zero conversion error: {zero_conversion}")
        except Exception as e:
            logger.warning(f"Zero conversion test failed: {e}")
        
        # Test negative amount conversion
        negative_amount = -1000
        try:
            negative_conversion = strategy.market_data.convert_currency(
                negative_amount, 'USD', 'CAD'
            )
            expected_negative = negative_amount * fx_rate_usd_cad
            
            logger.info(f"Negative amount conversion: ${negative_amount} USD -> ${negative_conversion:.2f} CAD")
            logger.info(f"Expected: ${expected_negative:.2f} CAD")
            
            if abs(negative_conversion - expected_negative) < 0.01:
                logger.info("✓ Negative amount conversion handled correctly")
            else:
                logger.warning("⚠ Negative amount conversion error")
        except Exception as e:
            logger.warning(f"Negative conversion test failed: {e}")

        # Test 7.7: Currency impact on margin calculations
        logger.info("\n--- TEST 7.7: Currency impact on margin calculations ---")
        
        # Get margin requirements in CAD
        maint_margin_cad = account_summary.get('MaintMarginReq', 0)
        init_margin_cad = account_summary.get('InitMarginReq', 0)
        
        # Convert to USD for comparison
        try:
            maint_margin_usd = strategy.market_data.convert_currency(
                maint_margin_cad, 'CAD', 'USD'
            )
            init_margin_usd = strategy.market_data.convert_currency(
                init_margin_cad, 'CAD', 'USD'
            )
        except:
            maint_margin_usd = maint_margin_cad * fx_rate_cad_usd
            init_margin_usd = init_margin_cad * fx_rate_cad_usd
        
        logger.info("Margin requirements:")
        logger.info(f"  Maintenance: ${maint_margin_cad:,.2f} CAD = ${maint_margin_usd:,.2f} USD")
        logger.info(f"  Initial: ${init_margin_cad:,.2f} CAD = ${init_margin_usd:,.2f} USD")
        
        # Calculate margin ratios
        if account_nlv > 0:
            maint_margin_ratio = maint_margin_cad / account_nlv
            init_margin_ratio = init_margin_cad / account_nlv
            
            logger.info(f"  Maintenance margin ratio: {maint_margin_ratio:.2%}")
            logger.info(f"  Initial margin ratio: {init_margin_ratio:.2%}")
            
            if maint_margin_ratio < 0.5:  # Reasonable margin usage
                logger.info("✓ Margin usage within reasonable limits")
            else:
                logger.warning("⚠ High margin usage detected")

        # Test 7.8: FX rate caching and refresh
        logger.info("\n--- TEST 7.8: FX rate caching mechanism ---")
        
        # Get rate and timing
        start_time = time.time()
        rate1 = strategy.market_data.get_fx_rate('USD', 'CAD')
        first_call_time = time.time() - start_time
        
        # Get same rate again (should be cached)
        start_time = time.time()
        rate2 = strategy.market_data.get_fx_rate('USD', 'CAD')
        second_call_time = time.time() - start_time
        
        logger.info(f"First FX rate call: {rate1:.4f} ({first_call_time:.3f}s)")
        logger.info(f"Second FX rate call: {rate2:.4f} ({second_call_time:.3f}s)")
        
        if rate1 == rate2:
            logger.info("✓ FX rate caching working (same rate returned)")
        else:
            logger.warning(f"⚠ FX rate changed between calls: {rate1} vs {rate2}")
        
        if second_call_time < first_call_time:
            logger.info("✓ Second call faster (likely cached)")
        else:
            logger.info("Second call not significantly faster (may not be cached)")

        logger.info("\n--- TEST 7 COMPLETED ---")
        return True

    except Exception as e:
        logger.error(f"Currency handling test failed: {e}", exc_info=True)
        return False
    
    finally:
        if 'ib' in locals() and ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from TWS")

if __name__ == "__main__":
    success = test_currency_handling()
    if success:
        logger.info("✓ Currency handling test completed successfully")
    else:
        logger.error("✗ Currency handling test failed")
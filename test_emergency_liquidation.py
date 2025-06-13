#!/usr/bin/env python3
"""
Test 5: Emergency liquidation mechanisms

Tests the system's ability to handle emergency leverage threshold breaches
and execute emergency liquidation orders.
"""

import time
from pathlib import Path

from ib_insync import IB

from src.config.settings import load_config
from src.strategy.enhanced_fixed_leverage import create_enhanced_strategy
from src.utils.logger import get_logger
from main import load_portfolio_weights

logger = get_logger(__name__)

def test_emergency_liquidation():
    """Test emergency liquidation mechanisms."""
    logger.info("=" * 60)
    logger.info("TEST 5: Emergency liquidation mechanisms")
    logger.info("=" * 60)

    try:
        # Load config
        config = load_config()
        config.dry_run = False  # Real orders for testing
        
        # Connect to IB
        ib = IB()
        ib.connect(config.ib.host, config.ib.port, clientId=config.ib.client_id)
        logger.info(f"Connected to TWS at {config.ib.host}:{config.ib.port}")

        # Load test portfolio weights (3-stock portfolio)
        weights_file = Path("test_simple_3stock.csv")
        if not weights_file.exists():
            logger.error(f"Weights file not found: {weights_file}")
            return False

        # Create strategy with extremely high target leverage to simulate emergency
        # This should trigger the emergency threshold check
        emergency_leverage = 4.0  # Above the 3.0 emergency threshold
        
        logger.info(f"Setting target leverage to {emergency_leverage}x (above emergency threshold of 3.0x)")
        
        strategy = create_enhanced_strategy(
            ib=ib,
            config=config,
            target_leverage=emergency_leverage,
            batch_execution=True
        )

        # Load portfolio weights from CSV
        portfolio_weights = load_portfolio_weights(str(weights_file))
        strategy.portfolio_weights = portfolio_weights
        
        # Get current portfolio state before test
        logger.info("\n--- CURRENT PORTFOLIO STATE ---")
        current_leverage = strategy.portfolio_manager.get_portfolio_leverage()
        logger.info(f"Current leverage: {current_leverage:.3f}x")
        
        account_summary = strategy.portfolio_manager.get_account_summary()
        logger.info(f"Net Liquidation: ${account_summary.get('NetLiquidation', 0):,.2f} CAD")
        logger.info(f"Available Funds: ${account_summary.get('AvailableFunds', 0):,.2f} CAD")
        
        positions = strategy.portfolio_manager.get_positions()
        logger.info(f"Current positions: {len(positions)}")
        for symbol, pos in positions.items():
            if pos.quantity != 0:
                logger.info(f"  {symbol}: {pos.quantity} shares @ ${pos.avg_cost:.2f}")

        # Test 5.1: Simulate emergency condition by manually setting high leverage scenario
        logger.info("\n--- TEST 5.1: Emergency leverage threshold check ---")
        
        # Temporarily override the emergency threshold to a lower value to trigger emergency
        original_threshold = config.strategy.emergency_leverage_threshold
        config.strategy.emergency_leverage_threshold = 1.5  # Lower threshold to trigger emergency
        
        logger.info(f"Temporarily setting emergency threshold to {config.strategy.emergency_leverage_threshold}x")
        logger.info(f"Current leverage {current_leverage:.3f}x should trigger emergency if > 1.5x")
        
        if current_leverage > config.strategy.emergency_leverage_threshold:
            logger.info("✓ Emergency condition detected - should trigger liquidation")
            
            # Attempt rebalance - this should trigger emergency liquidation
            result = strategy.rebalance(force=True)
            
            if not result:
                logger.info("✓ Rebalancing correctly failed due to emergency condition")
                
                # Check if emergency liquidation was called
                # We should see "EMERGENCY LIQUIDATION INITIATED" in logs
                logger.info("Emergency liquidation should have been initiated")
                
            else:
                logger.warning("⚠ Rebalancing succeeded despite emergency condition")
        else:
            logger.info("Current leverage is below emergency threshold - need to build positions first")
            
            # Restore original threshold
            config.strategy.emergency_leverage_threshold = original_threshold
            
            # Build up leverage first by investing more
            logger.info("\n--- Building up leverage for emergency test ---")
            high_leverage_strategy = create_enhanced_strategy(
                ib=ib,
                config=config,
                target_leverage=2.8,  # High but below emergency threshold
                batch_execution=True
            )
            high_leverage_strategy.portfolio_weights = portfolio_weights
            
            result = high_leverage_strategy.rebalance(force=True)
            if result:
                logger.info("Successfully built up leverage")
                
                # Wait for orders to settle
                time.sleep(10)
                
                # Check new leverage
                new_leverage = high_leverage_strategy.portfolio_manager.get_portfolio_leverage()
                logger.info(f"New leverage after building: {new_leverage:.3f}x")
                
                # Now test emergency with lower threshold
                config.strategy.emergency_leverage_threshold = new_leverage - 0.5
                logger.info(f"Setting emergency threshold to {config.strategy.emergency_leverage_threshold}x")
                
                emergency_test_strategy = create_enhanced_strategy(
                    ib=ib,
                    config=config,
                    target_leverage=4.0,  # This should trigger emergency
                    batch_execution=True
                )
                emergency_test_strategy.portfolio_weights = portfolio_weights
                
                result = emergency_test_strategy.rebalance(force=True)
                logger.info(f"Emergency rebalance result: {result}")
            
        # Test 5.2: Test manual emergency liquidation function
        logger.info("\n--- TEST 5.2: Manual emergency liquidation ---")
        
        # Restore original threshold  
        config.strategy.emergency_leverage_threshold = original_threshold
        
        # Get current positions for liquidation test
        positions_before = strategy.portfolio_manager.get_positions()
        non_zero_positions = {s: p for s, p in positions_before.items() if p.quantity != 0}
        
        if non_zero_positions:
            logger.info(f"Testing emergency liquidation on {len(non_zero_positions)} positions")
            
            # Call emergency liquidation directly
            liquidation_result = strategy.portfolio_manager.emergency_liquidate_all()
            
            logger.info(f"Emergency liquidation result: Success={liquidation_result.success}")
            logger.info(f"Orders placed: {len(liquidation_result.orders_placed)}")
            logger.info(f"Orders failed: {len(liquidation_result.orders_failed)}")
            logger.info(f"Execution time: {liquidation_result.execution_time:.2f}s")
            
            if liquidation_result.errors:
                logger.warning("Liquidation errors:")
                for error in liquidation_result.errors:
                    logger.warning(f"  {error}")
            
            # Wait for orders to complete
            if liquidation_result.orders_placed:
                logger.info("Waiting 15 seconds for liquidation orders to complete...")
                time.sleep(15)
                
                # Check positions after liquidation
                positions_after = strategy.portfolio_manager.get_positions()
                remaining_positions = {s: p for s, p in positions_after.items() if abs(p.quantity) > 1}
                
                if remaining_positions:
                    logger.warning(f"⚠ {len(remaining_positions)} positions remain after liquidation:")
                    for symbol, pos in remaining_positions.items():
                        logger.warning(f"  {symbol}: {pos.quantity} shares")
                else:
                    logger.info("✓ All positions successfully liquidated")
                    
                # Check leverage after liquidation
                final_leverage = strategy.portfolio_manager.get_portfolio_leverage()
                logger.info(f"Final leverage after liquidation: {final_leverage:.3f}x")
                
        else:
            logger.info("No positions to liquidate - portfolio is already empty")

        # Test 5.3: Recovery after emergency liquidation
        logger.info("\n--- TEST 5.3: Recovery mechanisms ---")
        
        # Check account state after emergency
        account_summary_after = strategy.portfolio_manager.get_account_summary()
        logger.info(f"Account state after emergency test:")
        logger.info(f"  Net Liquidation: ${account_summary_after.get('NetLiquidation', 0):,.2f} CAD")
        logger.info(f"  Available Funds: ${account_summary_after.get('AvailableFunds', 0):,.2f} CAD")
        logger.info(f"  Buying Power: ${account_summary_after.get('BuyingPower', 0):,.2f} CAD")
        
        # Test normal rebalancing after emergency
        logger.info("Testing normal rebalancing after emergency...")
        normal_strategy = create_enhanced_strategy(
            ib=ib,
            config=config,
            target_leverage=1.1,  # Conservative leverage
            batch_execution=True
        )
        normal_strategy.portfolio_weights = portfolio_weights
        
        recovery_result = normal_strategy.rebalance(force=True)
        logger.info(f"Recovery rebalance result: {recovery_result}")
        
        if recovery_result:
            logger.info("✓ System successfully recovered from emergency liquidation")
        else:
            logger.warning("⚠ System recovery failed")

        logger.info("\n--- TEST 5 COMPLETED ---")
        return True

    except Exception as e:
        logger.error(f"Emergency liquidation test failed: {e}", exc_info=True)
        return False
    
    finally:
        if 'ib' in locals() and ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from TWS")

if __name__ == "__main__":
    success = test_emergency_liquidation()
    if success:
        logger.info("✓ Emergency liquidation test completed successfully")
    else:
        logger.error("✗ Emergency liquidation test failed")
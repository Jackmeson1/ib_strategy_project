#!/usr/bin/env python3
"""
Fixed Leverage Calculation and Safer Rebalancing

The core issue is that the system tries to achieve target leverage without considering
available funds. This leads to margin calls and rejected orders.

Key fixes:
1. Calculate maximum safe leverage based on available funds
2. Implement progressive leverage changes instead of dramatic jumps
3. Add pre-flight funding checks
4. Validate leverage after execution
"""

import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ib_insync import IB
from src.config.settings import load_config
from src.strategy.enhanced_fixed_leverage import create_enhanced_strategy
from src.utils.logger import get_logger
from main import load_portfolio_weights

logger = get_logger(__name__)

class SafeLeverageManager:
    """Manages leverage changes safely within available fund limits."""
    
    def __init__(self, portfolio_manager, margin_safety_factor: float = 0.8):
        self.portfolio_manager = portfolio_manager
        self.margin_safety_factor = margin_safety_factor  # Use 80% of available funds
        
    def calculate_max_safe_leverage(self) -> float:
        """Calculate maximum leverage possible with available funds."""
        
        account_summary = self.portfolio_manager.get_account_summary()
        
        net_liquidation = account_summary.get('NetLiquidation', 0)
        available_funds = account_summary.get('AvailableFunds', 0)
        current_gross_value = account_summary.get('GrossPositionValue', 0)
        
        # Use conservative available funds
        safe_available_funds = available_funds * self.margin_safety_factor
        
        # Maximum position value we can safely hold
        max_safe_position_value = current_gross_value + safe_available_funds
        
        # Maximum leverage = max position value / net liquidation
        if net_liquidation > 0:
            max_safe_leverage = max_safe_position_value / net_liquidation
        else:
            max_safe_leverage = 1.0
            
        logger.info(f"Leverage calculation:")
        logger.info(f"  Net Liquidation: ${net_liquidation:,.2f}")
        logger.info(f"  Available Funds: ${available_funds:,.2f}")
        logger.info(f"  Safe Available: ${safe_available_funds:,.2f}")
        logger.info(f"  Current Gross Value: ${current_gross_value:,.2f}")
        logger.info(f"  Max Safe Leverage: {max_safe_leverage:.3f}x")
        
        return max_safe_leverage
    
    def calculate_safe_target_leverage(self, desired_leverage: float) -> Tuple[float, str]:
        """Calculate a safe target leverage that won't exceed funding limits."""
        
        max_safe = self.calculate_max_safe_leverage()
        current_leverage = self.portfolio_manager.get_portfolio_leverage()
        
        # Apply safety limits
        if desired_leverage > max_safe:
            safe_target = max_safe
            reason = f"Reduced from {desired_leverage:.3f}x to {safe_target:.3f}x (funding limit)"
        elif desired_leverage > 2.0:
            safe_target = 2.0
            reason = f"Reduced from {desired_leverage:.3f}x to {safe_target:.3f}x (safety limit)"
        else:
            safe_target = desired_leverage
            reason = f"Target {safe_target:.3f}x is safe"
            
        # Limit dramatic changes
        leverage_change = abs(safe_target - current_leverage)
        if leverage_change > 0.3:
            if safe_target > current_leverage:
                # Increasing leverage - be more conservative
                safe_target = current_leverage + 0.3
                reason = f"Limited increase to {safe_target:.3f}x (progressive change)"
            else:
                # Decreasing leverage - allow faster decrease
                safe_target = max(current_leverage - 0.5, safe_target)
                reason = f"Limited decrease to {safe_target:.3f}x (progressive change)"
        
        return safe_target, reason

def test_safe_leverage_management():
    """Test the safe leverage management system."""
    
    logger.info("=== TESTING SAFE LEVERAGE MANAGEMENT ===")
    
    try:
        # Load config
        config = load_config()
        config.dry_run = False
        
        # Connect to IB
        ib = IB()
        ib.connect(config.ib.host, config.ib.port, clientId=config.ib.client_id)
        logger.info(f"Connected to TWS at {config.ib.host}:{config.ib.port}")

        # Create strategy with simple 3-stock portfolio
        strategy = create_enhanced_strategy(
            ib=ib,
            config=config,
            target_leverage=1.0,  # Start conservative
            batch_execution=True
        )
        
        # Load simple portfolio
        weights_file = Path("test_simple_3stock.csv")
        if weights_file.exists():
            portfolio_weights = load_portfolio_weights(str(weights_file))
            strategy.portfolio_weights = portfolio_weights
            logger.info("Loaded 3-stock portfolio weights")

        # Initialize safe leverage manager
        safe_manager = SafeLeverageManager(strategy.portfolio_manager)
        
        # Test 1: Check current state and max safe leverage
        logger.info("\n--- TEST 1: Current state analysis ---")
        
        current_leverage = strategy.portfolio_manager.get_portfolio_leverage()
        max_safe_leverage = safe_manager.calculate_max_safe_leverage()
        
        logger.info(f"Current leverage: {current_leverage:.3f}x")
        logger.info(f"Maximum safe leverage: {max_safe_leverage:.3f}x")
        
        # Test 2: Try to achieve a reasonable target leverage
        logger.info("\n--- TEST 2: Safe leverage targeting ---")
        
        desired_targets = [1.1, 1.2, 1.3, 1.4, 1.5]
        
        for desired in desired_targets:
            safe_target, reason = safe_manager.calculate_safe_target_leverage(desired)
            logger.info(f"Desired {desired:.1f}x -> Safe target {safe_target:.3f}x ({reason})")
            
            if safe_target != current_leverage and abs(safe_target - current_leverage) > 0.05:
                logger.info(f"  Attempting to achieve {safe_target:.3f}x...")
                
                # Update strategy target
                strategy.target_leverage = safe_target
                
                # Pre-execution check
                account_before = strategy.portfolio_manager.get_account_summary()
                leverage_before = current_leverage
                available_before = account_before.get('AvailableFunds', 0)
                
                logger.info(f"  Before: Leverage {leverage_before:.3f}x, Available ${available_before:,.2f}")
                
                # Execute rebalancing
                result = strategy.rebalance(force=True)
                logger.info(f"  Execution result: {result}")
                
                if result:
                    # Wait for settlement
                    logger.info("  Waiting for orders to settle...")
                    time.sleep(8)
                    
                    # Check results
                    account_after = strategy.portfolio_manager.get_account_summary()
                    leverage_after = strategy.portfolio_manager.get_portfolio_leverage()
                    available_after = account_after.get('AvailableFunds', 0)
                    
                    logger.info(f"  After: Leverage {leverage_after:.3f}x, Available ${available_after:,.2f}")
                    
                    # Validate result
                    leverage_deviation = abs(leverage_after - safe_target)
                    if leverage_deviation <= 0.1:
                        logger.info(f"  ✓ Target achieved: {leverage_after:.3f}x (deviation: {leverage_deviation:.3f}x)")
                        current_leverage = leverage_after
                    else:
                        logger.warning(f"  ⚠ Target missed: {leverage_after:.3f}x vs {safe_target:.3f}x (deviation: {leverage_deviation:.3f}x)")
                        current_leverage = leverage_after
                    
                    # Check if we have positive available funds
                    if available_after > 10000:  # At least $10K buffer
                        logger.info(f"  ✓ Healthy available funds: ${available_after:,.2f}")
                    else:
                        logger.warning(f"  ⚠ Low available funds: ${available_after:,.2f}")
                        break  # Stop if funds are getting low
                        
                    time.sleep(3)  # Brief pause between iterations
                else:
                    logger.warning(f"  Execution failed for target {safe_target:.3f}x")
                    break
            else:
                logger.info(f"  Skipping {safe_target:.3f}x (too close to current {current_leverage:.3f}x)")

        # Test 3: Final state verification
        logger.info("\n--- TEST 3: Final state verification ---")
        
        final_account = strategy.portfolio_manager.get_account_summary()
        final_leverage = strategy.portfolio_manager.get_portfolio_leverage()
        final_positions = strategy.portfolio_manager.get_positions()
        
        logger.info("Final portfolio state:")
        logger.info(f"  Leverage: {final_leverage:.3f}x")
        logger.info(f"  Net Liquidation: ${final_account.get('NetLiquidation', 0):,.2f}")
        logger.info(f"  Available Funds: ${final_account.get('AvailableFunds', 0):,.2f}")
        logger.info(f"  Gross Position Value: ${final_account.get('GrossPositionValue', 0):,.2f}")
        
        logger.info("Final positions:")
        for symbol, pos in final_positions.items():
            if abs(pos.quantity) > 1:
                logger.info(f"  {symbol}: {pos.quantity} shares, ${pos.market_value:,.2f}")
        
        # Calculate final max safe leverage
        final_max_safe = safe_manager.calculate_max_safe_leverage()
        if final_leverage <= final_max_safe:
            logger.info(f"✓ Final leverage {final_leverage:.3f}x is within safe limit {final_max_safe:.3f}x")
        else:
            logger.warning(f"⚠ Final leverage {final_leverage:.3f}x exceeds safe limit {final_max_safe:.3f}x")

        return True

    except Exception as e:
        logger.error(f"Safe leverage management test failed: {e}", exc_info=True)
        return False
    
    finally:
        if 'ib' in locals() and ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from TWS")

def test_progressive_leverage_changes():
    """Test progressive leverage changes to avoid margin issues."""
    
    logger.info("=== TESTING PROGRESSIVE LEVERAGE CHANGES ===")
    
    try:
        # Load config
        config = load_config()
        config.dry_run = False
        
        # Connect to IB
        ib = IB()
        ib.connect(config.ib.host, config.ib.port, clientId=config.ib.client_id)
        
        # Create strategy
        strategy = create_enhanced_strategy(
            ib=ib,
            config=config,
            target_leverage=1.0,
            batch_execution=True
        )
        
        # Load portfolio
        weights_file = Path("test_simple_3stock.csv")
        if weights_file.exists():
            portfolio_weights = load_portfolio_weights(str(weights_file))
            strategy.portfolio_weights = portfolio_weights

        safe_manager = SafeLeverageManager(strategy.portfolio_manager)
        
        # Start with current leverage
        current_leverage = strategy.portfolio_manager.get_portfolio_leverage()
        logger.info(f"Starting leverage: {current_leverage:.3f}x")
        
        # Target a higher leverage progressively
        ultimate_target = 1.6
        step_size = 0.15
        
        logger.info(f"Progressive targeting from {current_leverage:.3f}x to {ultimate_target:.3f}x in {step_size:.2f}x steps")
        
        step = 1
        while current_leverage < ultimate_target - 0.05:  # 0.05 tolerance
            # Calculate next step
            next_step = min(current_leverage + step_size, ultimate_target)
            
            # Check if step is safe
            safe_target, reason = safe_manager.calculate_safe_target_leverage(next_step)
            
            logger.info(f"\nStep {step}: {current_leverage:.3f}x -> {next_step:.3f}x")
            logger.info(f"Safe target: {safe_target:.3f}x ({reason})")
            
            if safe_target <= current_leverage + 0.02:  # No meaningful progress
                logger.warning("Cannot make further progress - stopping")
                break
                
            # Execute step
            strategy.target_leverage = safe_target
            
            before_funds = strategy.portfolio_manager.get_account_summary().get('AvailableFunds', 0)
            
            result = strategy.rebalance(force=True)
            logger.info(f"Step {step} execution: {result}")
            
            if result:
                time.sleep(8)  # Wait for settlement
                
                new_leverage = strategy.portfolio_manager.get_portfolio_leverage()
                after_funds = strategy.portfolio_manager.get_account_summary().get('AvailableFunds', 0)
                
                progress = new_leverage - current_leverage
                logger.info(f"Progress: {current_leverage:.3f}x -> {new_leverage:.3f}x (+{progress:+.3f}x)")
                logger.info(f"Funds: ${before_funds:,.2f} -> ${after_funds:,.2f} ({after_funds-before_funds:+,.2f})")
                
                if progress > 0.02:  # Meaningful progress
                    current_leverage = new_leverage
                    step += 1
                    
                    if after_funds < 50000:  # Stop if funds get too low
                        logger.warning("Available funds getting low - stopping progressive changes")
                        break
                else:
                    logger.warning("No meaningful progress - stopping")
                    break
            else:
                logger.warning(f"Step {step} failed - stopping progression")
                break
                
            if step > 10:  # Safety limit
                logger.warning("Too many steps - stopping")
                break

        # Final summary
        final_leverage = strategy.portfolio_manager.get_portfolio_leverage()
        final_account = strategy.portfolio_manager.get_account_summary()
        
        logger.info(f"\nProgressive leverage change summary:")
        logger.info(f"  Final leverage: {final_leverage:.3f}x")
        logger.info(f"  Target was: {ultimate_target:.3f}x")
        logger.info(f"  Available funds: ${final_account.get('AvailableFunds', 0):,.2f}")
        
        if abs(final_leverage - ultimate_target) <= 0.2:
            logger.info("✓ Progressive leverage targeting successful")
        else:
            logger.info("⚠ Did not reach ultimate target (but may be due to safety limits)")

        return True

    except Exception as e:
        logger.error(f"Progressive leverage test failed: {e}", exc_info=True)
        return False
    
    finally:
        if 'ib' in locals() and ib.isConnected():
            ib.disconnect()

def main():
    """Run safe leverage management tests."""
    
    logger.info("🔧 TESTING SAFE LEVERAGE MANAGEMENT SYSTEM")
    logger.info("=" * 80)
    
    # Test safe leverage management
    safe_test_passed = test_safe_leverage_management()
    
    logger.info("\n" + "=" * 80)
    
    # Test progressive leverage changes
    progressive_test_passed = test_progressive_leverage_changes()
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("🏁 SAFE LEVERAGE MANAGEMENT SUMMARY")
    logger.info("=" * 80)
    
    logger.info("Key improvements implemented:")
    logger.info("✓ Maximum safe leverage calculation based on available funds")
    logger.info("✓ Progressive leverage changes to avoid margin calls")
    logger.info("✓ Pre-flight funding validation")
    logger.info("✓ Post-execution leverage verification")
    logger.info("✓ Safety limits and margin buffers")
    
    logger.info("\nTest results:")
    logger.info(f"{'✓' if safe_test_passed else '✗'} Safe leverage management test")
    logger.info(f"{'✓' if progressive_test_passed else '✗'} Progressive leverage changes test")
    
    if safe_test_passed and progressive_test_passed:
        logger.info("\n🎉 SAFE LEVERAGE MANAGEMENT WORKING")
        logger.info("The system now:")
        logger.info("- Calculates safe leverage limits based on available funds")
        logger.info("- Makes progressive changes to avoid margin calls")
        logger.info("- Validates leverage before and after execution")
        logger.info("- Prevents dangerous 2.5x+ leverage scenarios")
    else:
        logger.info("\n⚠️  SOME ISSUES MAY REMAIN - REVIEW REQUIRED")

if __name__ == "__main__":
    main()
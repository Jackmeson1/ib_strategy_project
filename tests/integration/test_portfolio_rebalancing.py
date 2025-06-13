#!/usr/bin/env python3
"""
Test 6: Portfolio rebalancing logic

Tests the system's ability to accurately rebalance portfolios according to
target weights, handle different leverage scenarios, and maintain proper
allocation ratios.
"""

import time
from pathlib import Path

from ib_insync import IB

from src.config.settings import load_config
from src.strategy.enhanced_fixed_leverage import create_enhanced_strategy
from src.utils.logger import get_logger
from main import load_portfolio_weights

logger = get_logger(__name__)

def test_portfolio_rebalancing():
    """Test portfolio rebalancing logic."""
    logger.info("=" * 60)
    logger.info("TEST 6: Portfolio rebalancing logic")
    logger.info("=" * 60)

    try:
        # Load config
        config = load_config()
        config.dry_run = False  # Real orders for testing
        
        # Connect to IB
        ib = IB()
        ib.connect(config.ib.host, config.ib.port, clientId=config.ib.client_id)
        logger.info(f"Connected to TWS at {config.ib.host}:{config.ib.port}")

        # Test 6.1: Test rebalancing with 3-stock equal weight portfolio
        logger.info("\n--- TEST 6.1: Three-stock equal weight rebalancing ---")
        
        weights_file = Path("test_simple_3stock.csv")
        if not weights_file.exists():
            logger.error(f"Weights file not found: {weights_file}")
            return False

        portfolio_weights = load_portfolio_weights(str(weights_file))
        logger.info(f"Target weights: {[(symbol, w.weight) for symbol, w in portfolio_weights.items()]}")
        
        # Create strategy with moderate leverage
        strategy = create_enhanced_strategy(
            ib=ib,
            config=config,
            target_leverage=1.2,
            batch_execution=True
        )
        strategy.portfolio_weights = portfolio_weights

        # Get current state
        logger.info("Current portfolio state:")
        current_positions = strategy.portfolio_manager.get_positions()
        account_summary = strategy.portfolio_manager.get_account_summary()
        current_leverage = strategy.portfolio_manager.get_portfolio_leverage()
        
        logger.info(f"Current leverage: {current_leverage:.3f}x")
        logger.info(f"Available Funds: ${account_summary.get('AvailableFunds', 0):,.2f} CAD")
        
        for symbol, pos in current_positions.items():
            if abs(pos.quantity) > 1:
                logger.info(f"  {symbol}: {pos.quantity} shares @ ${pos.avg_cost:.2f}")

        # Calculate target positions
        target_positions = strategy.calculate_target_positions()
        logger.info(f"Target positions: {target_positions}")
        
        # Execute rebalancing
        logger.info("Executing rebalancing...")
        result = strategy.rebalance(force=True)
        logger.info(f"Rebalancing result: {result}")
        
        if result:
            # Wait for orders to settle
            time.sleep(10)
            
            # Check new positions and weights
            new_positions = strategy.portfolio_manager.get_positions()
            new_leverage = strategy.portfolio_manager.get_portfolio_leverage()
            
            logger.info("Post-rebalancing state:")
            logger.info(f"New leverage: {new_leverage:.3f}x (target: 1.2x)")
            
            # Calculate actual weights
            total_value = sum(abs(pos.market_value) for pos in new_positions.values() if abs(pos.quantity) > 1)
            
            logger.info("Actual weights vs target:")
            for symbol, weight_obj in portfolio_weights.items():
                target_weight = weight_obj.weight
                if symbol in new_positions and abs(new_positions[symbol].quantity) > 1:
                    actual_weight = abs(new_positions[symbol].market_value) / total_value
                    deviation = abs(actual_weight - target_weight)
                    logger.info(f"  {symbol}: Target {target_weight:.1%}, Actual {actual_weight:.1%}, Deviation {deviation:.1%}")
                else:
                    logger.info(f"  {symbol}: Target {target_weight:.1%}, Actual 0.0%, Deviation {target_weight:.1%}")

        # Test 6.2: Test leverage adjustment without changing weights
        logger.info("\n--- TEST 6.2: Leverage adjustment test ---")
        
        # Increase leverage to 1.5x with same weights
        high_leverage_strategy = create_enhanced_strategy(
            ib=ib,
            config=config,
            target_leverage=1.5,
            batch_execution=True
        )
        high_leverage_strategy.portfolio_weights = portfolio_weights
        
        logger.info("Increasing leverage to 1.5x...")
        leverage_result = high_leverage_strategy.rebalance(force=True)
        logger.info(f"Leverage adjustment result: {leverage_result}")
        
        if leverage_result:
            time.sleep(10)
            
            final_leverage = high_leverage_strategy.portfolio_manager.get_portfolio_leverage()
            logger.info(f"Final leverage: {final_leverage:.3f}x (target: 1.5x)")
            
            leverage_deviation = abs(final_leverage - 1.5)
            if leverage_deviation < 0.1:
                logger.info("✓ Leverage target achieved within tolerance")
            else:
                logger.warning(f"⚠ Leverage deviation {leverage_deviation:.3f} exceeds tolerance")

        # Test 6.3: Test weight redistribution
        logger.info("\n--- TEST 6.3: Weight redistribution test ---")
        
        # Create custom weights (unequal distribution)
        from src.core.types import PortfolioWeight
        custom_weights = {
            'SPY': PortfolioWeight(symbol='SPY', weight=0.5, sector='Index'),
            'QQQ': PortfolioWeight(symbol='QQQ', weight=0.3, sector='Technology'),
            'GLD': PortfolioWeight(symbol='GLD', weight=0.2, sector='Commodities')
        }
        
        logger.info("Testing custom weight distribution:")
        for symbol, weight_obj in custom_weights.items():
            logger.info(f"  {symbol}: {weight_obj.weight:.1%}")
        
        custom_strategy = create_enhanced_strategy(
            ib=ib,
            config=config,
            target_leverage=1.3,
            batch_execution=True
        )
        custom_strategy.portfolio_weights = custom_weights
        
        redistribution_result = custom_strategy.rebalance(force=True)
        logger.info(f"Redistribution result: {redistribution_result}")
        
        if redistribution_result:
            time.sleep(10)
            
            # Check final allocation
            final_positions = custom_strategy.portfolio_manager.get_positions()
            final_total_value = sum(abs(pos.market_value) for pos in final_positions.values() if abs(pos.quantity) > 1)
            
            logger.info("Final weight distribution:")
            for symbol, weight_obj in custom_weights.items():
                target_weight = weight_obj.weight
                if symbol in final_positions and abs(final_positions[symbol].quantity) > 1:
                    actual_weight = abs(final_positions[symbol].market_value) / final_total_value
                    deviation = abs(actual_weight - target_weight)
                    status = "✓" if deviation < 0.05 else "⚠"
                    logger.info(f"  {symbol}: {status} Target {target_weight:.1%}, Actual {actual_weight:.1%}")

        # Test 6.4: Test rebalancing tolerance
        logger.info("\n--- TEST 6.4: Rebalancing tolerance test ---")
        
        # Check if small deviations trigger rebalancing
        tolerance_strategy = create_enhanced_strategy(
            ib=ib,
            config=config,
            target_leverage=1.31,  # Very small change from 1.3
            batch_execution=True
        )
        tolerance_strategy.portfolio_weights = custom_weights
        
        logger.info("Testing small leverage change (1.3 -> 1.31)...")
        needs_rebalancing = tolerance_strategy.check_rebalance_needed()
        logger.info(f"Rebalancing needed: {needs_rebalancing}")
        
        if needs_rebalancing:
            logger.info("Small change triggered rebalancing (as expected)")
        else:
            logger.info("Small change within tolerance (good)")

        # Test 6.5: Test complete portfolio liquidation and rebuild
        logger.info("\n--- TEST 6.5: Complete liquidation and rebuild test ---")
        
        # First liquidate everything
        liquidation_strategy = create_enhanced_strategy(
            ib=ib,
            config=config,
            target_leverage=0.0,  # Full liquidation
            batch_execution=True
        )
        
        # Set minimal weights to trigger liquidation
        minimal_weights = {symbol: PortfolioWeight(symbol=symbol, weight=0.0, sector=w.sector) 
                          for symbol, w in custom_weights.items()}
        liquidation_strategy.portfolio_weights = minimal_weights
        
        logger.info("Attempting full liquidation (target leverage: 0.0x)...")
        liquidation_result = liquidation_strategy.rebalance(force=True)
        logger.info(f"Liquidation result: {liquidation_result}")
        
        if liquidation_result:
            time.sleep(15)  # Wait longer for liquidation
            
            # Check if positions are closed
            liquidated_positions = liquidation_strategy.portfolio_manager.get_positions()
            remaining_value = sum(abs(pos.market_value) for pos in liquidated_positions.values() 
                                if abs(pos.quantity) > 1)
            
            logger.info(f"Remaining position value: ${remaining_value:,.2f}")
            
            if remaining_value < 1000:  # Less than $1000 remaining
                logger.info("✓ Portfolio successfully liquidated")
                
                # Now rebuild with original weights
                logger.info("Rebuilding portfolio with original weights...")
                rebuild_strategy = create_enhanced_strategy(
                    ib=ib,
                    config=config,
                    target_leverage=1.0,
                    batch_execution=True
                )
                rebuild_strategy.portfolio_weights = portfolio_weights
                
                rebuild_result = rebuild_strategy.rebalance(force=True)
                logger.info(f"Rebuild result: {rebuild_result}")
                
                if rebuild_result:
                    time.sleep(10)
                    rebuild_leverage = rebuild_strategy.portfolio_manager.get_portfolio_leverage()
                    logger.info(f"Rebuilt portfolio leverage: {rebuild_leverage:.3f}x")
            else:
                logger.warning("⚠ Portfolio liquidation incomplete")

        logger.info("\n--- TEST 6 COMPLETED ---")
        return True

    except Exception as e:
        logger.error(f"Portfolio rebalancing test failed: {e}", exc_info=True)
        return False
    
    finally:
        if 'ib' in locals() and ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from TWS")

if __name__ == "__main__":
    success = test_portfolio_rebalancing()
    if success:
        logger.info("✓ Portfolio rebalancing test completed successfully")
    else:
        logger.error("✗ Portfolio rebalancing test failed")
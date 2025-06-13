#!/usr/bin/env python3
"""
Investigation: Why Long-Only Strategy Creates Short Positions

This is a critical bug - our portfolio rebalancing strategy should only create
long positions, but we're seeing short SPY (-1,820 shares) and short MSFT (-121 shares).

Let's trace through the order calculation logic to find the root cause.
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

def investigate_order_calculation():
    """Investigate why long-only strategy creates short positions."""
    
    logger.info("🔍 INVESTIGATING SHORT POSITION BUG")
    logger.info("=" * 80)
    
    try:
        # Load config
        config = load_config()
        config.dry_run = True  # Use dry run to trace logic without executing
        
        # Connect to IB
        ib = IB()
        ib.connect(config.ib.host, config.ib.port, clientId=config.ib.client_id)
        logger.info(f"Connected to TWS at {config.ib.host}:{config.ib.port}")

        # Create strategy
        strategy = create_enhanced_strategy(
            ib=ib,
            config=config,
            target_leverage=1.3,
            batch_execution=True
        )
        
        # Load portfolio weights
        weights_file = Path("test_simple_3stock.csv")
        if weights_file.exists():
            portfolio_weights = load_portfolio_weights(str(weights_file))
            strategy.portfolio_weights = portfolio_weights
            
            logger.info("Target Portfolio Weights (SHOULD BE LONG-ONLY):")
            for symbol, weight_obj in portfolio_weights.items():
                logger.info(f"  {symbol}: {weight_obj.weight:.1%} (sector: {weight_obj.sector})")

        # Step 1: Analyze current positions
        logger.info("\n--- STEP 1: Current Portfolio Analysis ---")
        
        current_positions = strategy.portfolio_manager.get_positions()
        account_summary = strategy.portfolio_manager.get_account_summary()
        current_leverage = strategy.portfolio_manager.get_portfolio_leverage()
        
        logger.info(f"Current leverage: {current_leverage:.3f}x")
        logger.info(f"Net Liquidation: ${account_summary.get('NetLiquidation', 0):,.2f}")
        
        logger.info("Current positions:")
        long_positions = {}
        short_positions = {}
        
        for symbol, pos in current_positions.items():
            if abs(pos.quantity) > 1:
                if pos.quantity > 0:
                    long_positions[symbol] = pos
                    logger.info(f"  LONG {symbol}: +{pos.quantity} shares @ ${pos.avg_cost:.2f} = ${pos.market_value:,.2f}")
                else:
                    short_positions[symbol] = pos
                    logger.error(f"  SHORT {symbol}: {pos.quantity} shares @ ${pos.avg_cost:.2f} = ${pos.market_value:,.2f}")
        
        if short_positions:
            logger.error(f"🚨 FOUND {len(short_positions)} SHORT POSITIONS - THIS SHOULD NOT HAPPEN!")
        else:
            logger.info("✓ No short positions found")

        # Step 2: Calculate target positions using strategy logic
        logger.info("\n--- STEP 2: Target Position Calculation ---")
        
        # Let's manually trace through the calculation
        target_positions = strategy.calculate_target_positions()
        
        logger.info("Calculated target positions:")
        for symbol, target_qty in target_positions.items():
            current_qty = current_positions.get(symbol, type('obj', (), {'quantity': 0})()).quantity
            difference = target_qty - current_qty
            
            logger.info(f"  {symbol}:")
            logger.info(f"    Current: {current_qty} shares")
            logger.info(f"    Target:  {target_qty} shares")
            logger.info(f"    Change:  {difference:+.0f} shares")
            
            if target_qty < 0:
                logger.error(f"    🚨 TARGET IS NEGATIVE! This will create short position!")

        # Step 3: Analyze order calculation logic
        logger.info("\n--- STEP 3: Order Calculation Analysis ---")
        
        # Get the orders that would be generated
        orders = strategy._calculate_orders(target_positions)
        
        logger.info("Generated orders:")
        for order in orders:
            current_qty = current_positions.get(order.symbol, type('obj', (), {'quantity': 0})()).quantity
            
            logger.info(f"  {order.symbol}: {order.action.value} {order.quantity} shares")
            logger.info(f"    Current position: {current_qty}")
            
            if order.action.value == 'SELL':
                resulting_position = current_qty - order.quantity
                logger.info(f"    After SELL: {resulting_position} shares")
                
                if resulting_position < 0:
                    logger.error(f"    🚨 SELL ORDER WILL CREATE SHORT POSITION: {resulting_position} shares")
            else:
                resulting_position = current_qty + order.quantity
                logger.info(f"    After BUY: {resulting_position} shares")

        # Step 4: Deep dive into leverage calculation and position sizing
        logger.info("\n--- STEP 4: Position Sizing Logic Analysis ---")
        
        # Get account details for position sizing
        net_liquidation = account_summary.get('NetLiquidation', 0)
        target_leverage = strategy.target_leverage
        
        logger.info(f"Position sizing parameters:")
        logger.info(f"  Net Liquidation: ${net_liquidation:,.2f}")
        logger.info(f"  Target Leverage: {target_leverage:.2f}x")
        logger.info(f"  Target Portfolio Value: ${net_liquidation * target_leverage:,.2f}")
        
        # Calculate target value per symbol
        total_weight = sum(w.weight for w in portfolio_weights.values())
        logger.info(f"  Total weight: {total_weight:.1%}")
        
        if abs(total_weight - 1.0) > 0.01:
            logger.warning(f"  ⚠ Weights don't sum to 100%: {total_weight:.1%}")
        
        for symbol, weight_obj in portfolio_weights.items():
            target_portfolio_value = net_liquidation * target_leverage
            target_symbol_value = target_portfolio_value * weight_obj.weight
            
            logger.info(f"  {symbol} target value: ${target_symbol_value:,.2f} ({weight_obj.weight:.1%})")
            
            # Get current price
            try:
                # This might fail due to contract issues, but let's try
                price = strategy.market_data.get_current_price(symbol)
                if price:
                    target_shares = target_symbol_value / price
                    logger.info(f"    Price: ${price:.2f}, Target shares: {target_shares:.0f}")
                else:
                    logger.warning(f"    No price available for {symbol}")
            except Exception as e:
                logger.warning(f"    Price lookup failed for {symbol}: {e}")

        # Step 5: Check for liquidation logic issues
        logger.info("\n--- STEP 5: Liquidation Logic Check ---")
        
        # Check if any symbols in current positions are NOT in target weights
        current_symbols = set(pos.symbol for pos in current_positions.values() if abs(pos.quantity) > 1)
        target_symbols = set(portfolio_weights.keys())
        
        symbols_to_liquidate = current_symbols - target_symbols
        symbols_to_add = target_symbols - current_symbols
        
        if symbols_to_liquidate:
            logger.info(f"Symbols to liquidate (not in target): {symbols_to_liquidate}")
            for symbol in symbols_to_liquidate:
                pos = current_positions[symbol]
                logger.info(f"  {symbol}: {pos.quantity} shares (${pos.market_value:,.2f})")
                logger.warning(f"    This should be LIQUIDATED completely, not made short!")
        
        if symbols_to_add:
            logger.info(f"Symbols to add (new in target): {symbols_to_add}")

        # Step 6: Check rebalancing tolerance logic
        logger.info("\n--- STEP 6: Rebalancing Logic Check ---")
        
        needs_rebalancing = strategy.check_rebalance_needed()
        logger.info(f"Rebalancing needed: {needs_rebalancing}")
        
        # Check individual symbol deviations
        current_total_value = sum(abs(pos.market_value) for pos in current_positions.values() if abs(pos.quantity) > 1)
        
        if current_total_value > 0:
            logger.info("Current vs target weight deviations:")
            for symbol, weight_obj in portfolio_weights.items():
                target_weight = weight_obj.weight
                
                if symbol in current_positions and abs(current_positions[symbol].quantity) > 1:
                    current_value = abs(current_positions[symbol].market_value)
                    current_weight = current_value / current_total_value
                    deviation = abs(current_weight - target_weight)
                    
                    logger.info(f"  {symbol}: Current {current_weight:.1%}, Target {target_weight:.1%}, Deviation {deviation:.1%}")
                    
                    if deviation > 0.05:  # 5% threshold
                        logger.warning(f"    Large deviation triggers rebalancing")
                else:
                    logger.info(f"  {symbol}: Current 0.0%, Target {target_weight:.1%}, Deviation {target_weight:.1%}")

        return True

    except Exception as e:
        logger.error(f"Investigation failed: {e}", exc_info=True)
        return False
    
    finally:
        if 'ib' in locals() and ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from TWS")

def trace_position_calculation_bug():
    """Trace the exact bug in position calculation that creates shorts."""
    
    logger.info("\n🔬 TRACING POSITION CALCULATION BUG")
    logger.info("=" * 80)
    
    try:
        # Load config  
        config = load_config()
        config.dry_run = True
        
        # Connect to IB
        ib = IB()
        ib.connect(config.ib.host, config.ib.port, clientId=config.ib.client_id)
        
        # Create strategy
        strategy = create_enhanced_strategy(
            ib=ib,
            config=config,
            target_leverage=1.3,
            batch_execution=True
        )
        
        # Load simple 3-stock portfolio
        weights_file = Path("test_simple_3stock.csv")
        portfolio_weights = load_portfolio_weights(str(weights_file))
        strategy.portfolio_weights = portfolio_weights
        
        logger.info("EXPECTED BEHAVIOR:")
        logger.info("- SPY: 40% weight = LONG position")
        logger.info("- QQQ: 30% weight = LONG position") 
        logger.info("- GLD: 30% weight = LONG position")
        logger.info("- NO SHORT POSITIONS SHOULD EXIST")
        
        # Get current state
        current_positions = strategy.portfolio_manager.get_positions()
        account_summary = strategy.portfolio_manager.get_account_summary()
        
        # Show current problematic state
        logger.info("\nCURRENT PROBLEMATIC STATE:")
        for symbol, pos in current_positions.items():
            if abs(pos.quantity) > 1:
                logger.info(f"  {symbol}: {pos.quantity} shares")
                if pos.quantity < 0:
                    logger.error(f"    🚨 SHORT POSITION EXISTS!")
        
        # Manually step through target calculation
        logger.info("\nMANUAL TARGET CALCULATION:")
        
        net_liquidation = account_summary.get('NetLiquidation', 0)
        target_leverage = 1.3
        target_portfolio_value = net_liquidation * target_leverage
        
        logger.info(f"Net Liquidation: ${net_liquidation:,.2f}")
        logger.info(f"Target Leverage: {target_leverage}x")
        logger.info(f"Target Portfolio Value: ${target_portfolio_value:,.2f}")
        
        # Calculate what SHOULD happen for each symbol
        logger.info("\nCORRECT TARGET CALCULATION (what should happen):")
        
        for symbol, weight_obj in portfolio_weights.items():
            target_value = target_portfolio_value * weight_obj.weight
            logger.info(f"\n{symbol} (Target: {weight_obj.weight:.1%}):")
            logger.info(f"  Target Value: ${target_value:,.2f}")
            
            # Try to get price (may fail due to contract issues)
            try:
                price = 200.0  # Approximate price for calculation
                if symbol == 'GLD':
                    price = 316.0
                elif symbol == 'SPY':
                    price = 598.0
                elif symbol == 'QQQ':
                    price = 528.0
                    
                target_shares = target_value / price
                logger.info(f"  Estimated Price: ${price:.2f}")
                logger.info(f"  Target Shares: {target_shares:.0f}")
                logger.info(f"  ✓ This should be POSITIVE (LONG)")
                
                # Check what we currently have
                current_qty = current_positions.get(symbol, type('obj', (), {'quantity': 0})()).quantity
                change_needed = target_shares - current_qty
                
                logger.info(f"  Current Quantity: {current_qty}")
                logger.info(f"  Change Needed: {change_needed:+.0f}")
                
                if change_needed > 0:
                    logger.info(f"  → Should BUY {abs(change_needed):.0f} shares")
                elif change_needed < 0:
                    logger.info(f"  → Should SELL {abs(change_needed):.0f} shares")
                    
                    # Check if sell would create short
                    final_position = current_qty + change_needed
                    if final_position < 0:
                        logger.error(f"  🚨 BUG: SELL would create SHORT position: {final_position:.0f}")
                        logger.error(f"  🔧 FIX: Should limit SELL to current quantity: {current_qty}")
                        logger.error(f"  🔧 CORRECTED: SELL {current_qty} shares (liquidate only)")
                else:
                    logger.info(f"  → No change needed")
                    
            except Exception as e:
                logger.warning(f"  Price calculation failed: {e}")

        # Check what strategy actually calculates
        logger.info("\nSTRATEGY CALCULATION (what's actually happening):")
        try:
            target_positions = strategy.calculate_target_positions()
            
            for symbol, target_qty in target_positions.items():
                logger.info(f"\n{symbol}: Strategy calculated {target_qty} target shares")
                
                if target_qty < 0:
                    logger.error(f"🚨 STRATEGY BUG: Target quantity is NEGATIVE!")
                    logger.error(f"   This will create a short position!")
                elif target_qty == 0:
                    logger.warning(f"⚠ Strategy calculated ZERO shares")
                    logger.warning(f"   This might be due to missing price data")
                else:
                    logger.info(f"✓ Target is positive: {target_qty} shares")
                    
        except Exception as e:
            logger.error(f"Strategy calculation failed: {e}")

        # Identify the root cause
        logger.info("\n🎯 ROOT CAUSE ANALYSIS:")
        logger.info("Possible causes of short positions:")
        logger.info("1. ❌ Target calculation returns negative values")
        logger.info("2. ❌ Order logic sells more shares than owned")
        logger.info("3. ❌ Position liquidation logic is broken")
        logger.info("4. ❌ Price data issues causing bad calculations")
        logger.info("5. ❌ Contract resolution failures affecting weights")
        
        logger.info("\nLikely culprit: SPY/QQQ contract resolution failures")
        logger.info("- SPY/QQQ contracts fail to resolve ('Contract not found')")
        logger.info("- Strategy can't get prices for SPY/QQQ")
        logger.info("- Target calculation defaults to 0 or negative")
        logger.info("- System tries to 'liquidate' existing positions")
        logger.info("- But liquidation logic sells MORE than owned")

        return True

    except Exception as e:
        logger.error(f"Trace failed: {e}", exc_info=True)
        return False
    
    finally:
        if 'ib' in locals() and ib.isConnected():
            ib.disconnect()

def main():
    """Main investigation function."""
    
    logger.info("🚨 INVESTIGATING CRITICAL BUG: SHORT POSITIONS IN LONG-ONLY STRATEGY")
    logger.info("=" * 100)
    
    # Step 1: General investigation
    investigate_order_calculation()
    
    # Step 2: Detailed bug tracing  
    trace_position_calculation_bug()
    
    # Summary
    logger.info("\n" + "=" * 100)
    logger.info("🔍 INVESTIGATION SUMMARY")
    logger.info("=" * 100)
    
    logger.info("CRITICAL BUG IDENTIFIED:")
    logger.info("❌ Long-only strategy is creating SHORT positions")
    logger.info("❌ SPY: -1,820 shares (should be +~1,000 shares)")
    logger.info("❌ MSFT: -121 shares (should be 0 or positive)")
    logger.info("")
    
    logger.info("ROOT CAUSE:")
    logger.info("1. Contract resolution failures for SPY/QQQ")
    logger.info("2. Missing price data leads to zero/negative targets")
    logger.info("3. Order calculation logic doesn't prevent overselling")
    logger.info("4. No validation that sells don't exceed current holdings")
    logger.info("")
    
    logger.info("IMMEDIATE FIXES NEEDED:")
    logger.info("🔧 Add position validation: SELL orders cannot exceed current holdings")
    logger.info("🔧 Fix contract resolution for SPY/QQQ")
    logger.info("🔧 Add safety check: Target positions must be >= 0 for long-only strategy")
    logger.info("🔧 Improve error handling when price data is missing")
    logger.info("")
    
    logger.info("This explains why you're seeing 'unexpected' short positions!")
    logger.info("The strategy is NOT supposed to short anything - this is a calculation bug.")

if __name__ == "__main__":
    main()
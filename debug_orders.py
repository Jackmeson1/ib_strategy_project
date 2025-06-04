#!/usr/bin/env python3
"""Debug script to understand why no orders are being generated."""

import sys
import os
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from rebalance import load_portfolio_weights
from src.config.settings import load_config
from src.core.connection import create_connection_manager
from src.strategy.fixed_leverage import FixedLeverageStrategy

def debug_order_generation():
    """Debug why no orders are being generated."""
    load_dotenv()
    config = load_config()
    
    connection_manager = create_connection_manager(config.ib)
    
    with connection_manager.connection() as ib:
        print("=== DEBUGGING ORDER GENERATION ===")
        
        # Load small test portfolio
        portfolio_weights = load_portfolio_weights("small_test_portfolio.csv")
        print(f"\n1. Target Portfolio Weights:")
        for symbol, weight in portfolio_weights.items():
            print(f"   {symbol}: {weight.weight:.2%}")
        
        # Initialize strategy
        strategy = FixedLeverageStrategy(
            ib, 
            config, 
            portfolio_weights=portfolio_weights,
            target_leverage=1.05
        )
        
        print(f"\n2. Current Portfolio:")
        current_positions = strategy.portfolio_manager.get_positions(force_refresh=True)
        account = strategy.get_account_summary()
        nlv_cad = account.get('NetLiquidation', 0)
        
        print(f"   Account Value: ${nlv_cad:,.2f} CAD")
        total_current_value = sum(pos.market_value for pos in current_positions.values())
        print(f"   Current Total Position Value: ${total_current_value:,.2f} USD")
        
        for symbol, pos in current_positions.items():
            if symbol in portfolio_weights:
                current_weight = pos.market_value / total_current_value if total_current_value > 0 else 0
                target_weight = portfolio_weights[symbol].weight
                print(f"   {symbol}: Current {current_weight:.2%} vs Target {target_weight:.2%}")
        
        print(f"\n3. Target Position Calculation:")
        try:
            target_positions = strategy.calculate_target_positions()
            print(f"   Target positions calculated: {len(target_positions)}")
            for symbol, shares in target_positions.items():
                current_shares = current_positions.get(symbol, type('obj', (object,), {'quantity': 0})).quantity
                difference = shares - current_shares
                print(f"   {symbol}: Current {current_shares:.0f} -> Target {shares:.0f} (Diff: {difference:+.0f})")
        except Exception as e:
            print(f"   ERROR in target calculation: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"\n4. Check Rebalance Need:")
        needs_rebalance = strategy.check_rebalance_needed(tolerance=0.05)
        print(f"   Needs rebalancing (5% tolerance): {needs_rebalance}")
        
        # Test with stricter tolerance
        needs_rebalance_strict = strategy.check_rebalance_needed(tolerance=0.01)
        print(f"   Needs rebalancing (1% tolerance): {needs_rebalance_strict}")

if __name__ == "__main__":
    debug_order_generation() 
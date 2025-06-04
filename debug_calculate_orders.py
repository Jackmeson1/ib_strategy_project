#!/usr/bin/env python3
"""Debug script to check why _calculate_orders returns empty list."""

import sys
import os
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from rebalance import load_portfolio_weights
from src.config.settings import load_config
from src.core.connection import create_connection_manager
from src.strategy.fixed_leverage import FixedLeverageStrategy

def debug_calculate_orders():
    """Debug why _calculate_orders returns empty list."""
    load_dotenv()
    config = load_config()
    
    connection_manager = create_connection_manager(config.ib)
    
    with connection_manager.connection() as ib:
        print("=== DEBUGGING _calculate_orders() ===")
        
        # Load small test portfolio
        portfolio_weights = load_portfolio_weights("small_test_portfolio.csv")
        
        # Initialize strategy
        strategy = FixedLeverageStrategy(
            ib, 
            config, 
            portfolio_weights=portfolio_weights,
            target_leverage=1.05
        )
        
        print("\n1. Getting target positions:")
        target_positions = strategy.calculate_target_positions()
        for symbol, shares in target_positions.items():
            print(f"   {symbol}: {shares} shares")
        
        print("\n2. Getting current positions:")
        current_positions = strategy.portfolio_manager.get_positions(force_refresh=True)
        for symbol, pos in current_positions.items():
            if symbol in target_positions:
                print(f"   {symbol}: {pos.quantity} shares")
        
        print("\n3. Manual order calculation:")
        orders = []
        for symbol, target_qty in target_positions.items():
            current_qty = current_positions.get(symbol, type('obj', (object,), {'quantity': 0})).quantity
            diff = target_qty - current_qty
            
            print(f"   {symbol}: Target {target_qty} - Current {current_qty} = Diff {diff}")
            
            if abs(diff) < 1:  # Skip negligible differences
                print(f"     -> SKIPPED (diff {diff} < 1)")
                continue
            
            print(f"     -> ORDER NEEDED: {'BUY' if diff > 0 else 'SELL'} {abs(int(diff))} shares")
            orders.append({
                'symbol': symbol,
                'action': 'BUY' if diff > 0 else 'SELL',
                'quantity': abs(int(diff))
            })
        
        print(f"\n4. Total orders calculated: {len(orders)}")
        
        print("\n5. Testing executor._calculate_orders():")
        calculated_orders = strategy.executor._calculate_orders(target_positions)
        print(f"   Executor calculated orders: {len(calculated_orders)}")
        for order in calculated_orders:
            print(f"   {order.symbol}: {order.action.value} {order.quantity}")

if __name__ == "__main__":
    debug_calculate_orders() 
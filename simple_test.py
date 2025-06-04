#!/usr/bin/env python3
"""Simple diagnostic script to understand IB account state."""

import sys
import os
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.config.settings import load_config
from src.core.connection import create_connection_manager

def diagnose_account():
    """Diagnose current account state."""
    load_dotenv()
    config = load_config()
    
    connection_manager = create_connection_manager(config.ib)
    
    with connection_manager.connection() as ib:
        print("=== IB ACCOUNT DIAGNOSTIC ===")
        
        # 1. Account Summary
        print("\n1. Account Summary:")
        account_values = ib.accountSummary()
        for item in account_values:
            if item.tag in ['NetLiquidation', 'TotalCashValue', 'GrossPositionValue', 'AvailableFunds']:
                print(f"   {item.tag}: {item.value} {item.currency}")
        
        # 2. Portfolio Items  
        print("\n2. Portfolio Items:")
        portfolio = ib.portfolio()
        print(f"   Total portfolio items: {len(portfolio)}")
        for item in portfolio:
            if item.position != 0:
                print(f"   {item.contract.symbol}: {item.position} shares, Value: {item.marketValue}")
        
        # 3. Positions
        print("\n3. Positions:")
        positions = ib.positions()
        print(f"   Total positions: {len(positions)}")
        for pos in positions:
            if pos.position != 0:
                print(f"   {pos.contract.symbol}: {pos.position} shares, Avg Cost: {pos.avgCost}")
        
        # 4. Open Orders
        print("\n4. Open Orders:")
        orders = ib.openOrders()
        print(f"   Open orders: {len(orders)}")
        for order in orders:
            print(f"   Order ID {order.orderId}: {order.action} {order.totalQuantity} {order.contract.symbol}")
        
        print("\n=== END DIAGNOSTIC ===")

if __name__ == "__main__":
    diagnose_account() 
#!/usr/bin/env python3
"""Debug script to understand position retrieval issues."""

import sys
import os
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.config.settings import load_config
from src.core.connection import create_connection_manager

def debug_positions():
    """Debug position retrieval issues."""
    load_dotenv()
    config = load_config()
    
    connection_manager = create_connection_manager(config.ib)
    
    with connection_manager.connection() as ib:
        print("=== POSITION RETRIEVAL DEBUG ===")
        
        print(f"\n1. Config Account ID: {config.ib.account_id}")
        
        print("\n2. All Positions from IB:")
        all_positions = ib.positions()
        print(f"   Total positions retrieved: {len(all_positions)}")
        
        for i, pos in enumerate(all_positions):
            print(f"   Position {i+1}:")
            print(f"     Account: '{pos.account}'")
            print(f"     Symbol: {pos.contract.symbol}")
            print(f"     Quantity: {pos.position}")
            print(f"     AvgCost: {pos.avgCost}")
        
        print("\n3. Account Matching Check:")
        matches = [p for p in all_positions if p.account == config.ib.account_id]
        print(f"   Positions matching config account ID: {len(matches)}")
        
        print("\n4. Portfolio method:")
        portfolio = ib.portfolio()
        print(f"   Portfolio items: {len(portfolio)}")
        for item in portfolio:
            if item.position != 0:
                print(f"     {item.contract.symbol}: {item.position} shares")
        
        print("\n5. Account Summary method:")
        try:
            account_items = ib.accountSummary(account=config.ib.account_id)
            for item in account_items:
                if item.tag == 'GrossPositionValue':
                    print(f"   GrossPositionValue: {item.value}")
                    break
        except Exception as e:
            print(f"   Error getting account summary: {e}")

if __name__ == "__main__":
    debug_positions() 
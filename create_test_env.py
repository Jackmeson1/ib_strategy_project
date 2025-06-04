#!/usr/bin/env python3
"""Create a test .env file for IB paper trading testing."""

env_content = """IB_GATEWAY_HOST=127.0.0.1
IB_GATEWAY_PORT=7497
IB_CLIENT_ID=1
IB_ACCOUNT_ID=DU7793356
DRY_RUN=false
DEFAULT_LEVERAGE=1.4
EMERGENCY_LEVERAGE_THRESHOLD=3.0
LEVERAGE_BUFFER=0.1
REBALANCE_TOLERANCE=0.05
PRIMARY_EXCHANGE=SMART
"""

with open('.env', 'w', encoding='utf-8') as f:
    f.write(env_content)

print("IB Paper Trading .env file created successfully!")
print("Account ID: DU7793356")
print("Port: 7497 (TWS Paper Trading)")
print("DRY_RUN: false (Real IB connection)") 
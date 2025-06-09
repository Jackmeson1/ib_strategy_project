# Interactive Brokers Setup

This short guide explains how to prepare your Interactive Brokers environment for API based trading.

## Requirements
- An Interactive Brokers account
- IB Gateway or Trader Workstation installed
- API access enabled in the client

## Quick Steps
1. Start IB Gateway or TWS.
2. Enable `API > Settings > Enable ActiveX and Socket Clients`.
3. Set the API port and note the generated client id.
4. Update `IB_GATEWAY_PORT` and `IB_ACCOUNT_ID` in your `.env` file.
5. Run `python main.py --status` to confirm connectivity.

# IB Strategy Project

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![IB API](https://img.shields.io/badge/IB%20API-Compatible-orange.svg)](https://interactivebrokers.github.io/)

Production-ready portfolio rebalancing for Interactive Brokers with parallel execution, atomic margin checks, and comprehensive safety features.

## Why This Tool?

- **No more hanging orders** - True parallel batch execution with thread pools
- **Safe by default** - Atomic margin validation before any trades execute  
- **Production tested** - Handle real money with confidence using our 5-layer safety system
- **Simple to use** - One command to rebalance your entire portfolio

## Quick Start

### 1. Install
```bash
git clone https://github.com/Jackmeson1/ib_strategy_project.git
cd ib_strategy_project
pip install -r requirements.txt
```

### 2. Configure
```bash
cp config/env.example .env
# Edit .env with your IB credentials
```

Key settings in `.env`:
```env
IB_GATEWAY_PORT=7497        # 7497 for paper, 7496 for live
IB_ACCOUNT_ID=DU1234567     # Your IB account
TARGET_LEVERAGE=1.4         # Target portfolio leverage
DRY_RUN=true               # Set false for live trading
```

### 3. Run
```bash
# Test mode (recommended first)
python main.py --dry-run

# Production mode with all safety features
python main.py --batch-execution --smart-orders --hanging-protection
```

## Core Features

### 🚀 Execution Modes

**Standard Mode** (default)
```bash
python main.py
```
- Sequential order execution
- Basic safety checks
- Good for simple portfolios

**Production Mode** 
```bash
python main.py --batch-execution --smart-orders --hanging-protection
```
- Parallel batch execution (no order hanging)
- Smart order routing (Market <$10K, Limit >$10K)
- 5-layer timeout protection
- Atomic margin validation

### 🛡️ Safety Features

- **Margin Buffer**: 20% safety cushion (configurable)
- **Position Limits**: Max 80% of net liquidation value
- **Emergency Stop**: Auto-liquidation at 3x leverage
- **Watchdog Timer**: Global timeout kills hung processes
- **Dry Run Mode**: Test everything without placing orders

### 📊 Portfolio Configuration

Define your target allocation in `portfolio.csv`:
```csv
symbol,weight,sector
SPY,0.50,Index
TLT,0.20,Bonds
GLD,0.10,Commodities
MSFT,0.10,Technology
NVDA,0.10,Technology
```

Or use the built-in 60/40 portfolio:
```bash
python main.py  # Uses default portfolio
```

## Common Use Cases

### Daily Rebalancing (Cron)
```bash
0 9 30 * * cd /path/to/project && python main.py --batch-execution --force
```

### Conservative Live Trading
```bash
python main.py --leverage 1.2 --margin-cushion 0.3 --max-parallel 2
```

### Multi-Account Setup
```env
IB_ACCOUNTS=DU1234567:USD,DU7654321:EUR
```

## Monitoring

Each run creates a snapshot in `portfolio_snapshots/`:
```json
{
  "timestamp": "2024-01-15T14:30:00",
  "execution_time": 45.2,
  "orders_executed": 12,
  "margin_utilization": 0.546,
  "leverage": {"current": 1.38, "target": 1.4}
}
```

Optional Telegram alerts:
```env
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

## Production Checklist

Before going live:
- [ ] Test extensively with `--dry-run`
- [ ] Verify IB Gateway connection
- [ ] Review position limits and leverage
- [ ] Set appropriate timeouts
- [ ] Configure monitoring/alerts
- [ ] Start with small positions

## Troubleshooting

**Connection Issues**
- Ensure IB Gateway/TWS is running
- Check API permissions are enabled
- Verify port matches your setup (7497/7496)

**Order Failures**
- Check margin requirements
- Verify symbols are correct
- Review position size limits

## Advanced Usage

See [docs/](docs/) for:
- [Interactive Brokers Setup Guide](docs/INTERACTIVE_BROKERS_SETUP.md)
- [IB API Best Practices](docs/IB_API_BEST_PRACTICES.md)
- [Portfolio Rebalancing Strategies](docs/PORTFOLIO_REBALANCING_STRATEGIES.md)
- [Migration Guide](docs/MIGRATION.md)

## Contributing

PRs welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## ⚠️ Risk Warning

Trading with leverage involves substantial risk. This software is provided as-is without warranties. Always test thoroughly and trade responsibly.

## License

MIT - see [LICENSE](LICENSE)

---

*Keywords: Interactive Brokers, IB API, portfolio rebalancing, algorithmic trading, Python*

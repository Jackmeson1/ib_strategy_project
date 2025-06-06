# IB Portfolio Rebalancing Tool

A production-ready portfolio rebalancing tool for Interactive Brokers with advanced batch execution, atomic margin checks, and comprehensive hanging protection.

## 🆕 P0 Production Fixes (Latest)

✅ **P0-A: True Batch Execution** - Fire-all-then-monitor with thread pools (no per-order hanging)
✅ **P0-B: Single Canonical Entrypoint** - `main.py` with feature-based execution control
✅ **P0-C: Fail-fast Timeouts & Alerts** - Global watchdog with configurable runtime limits
✅ **P0-D: Atomic Margin Check** - Batch-level margin validation before execution
✅ **P0-E: Config Isolation** - All sensitive values in `.env` with comprehensive template

## Overview

This tool manages leveraged portfolios with:
- **Fixed leverage** (default 1.4x, configurable)
- **Feature-based execution** (Standard vs Enhanced modes)
- **Atomic batch processing** with hanging protection
- **Portfolio weight management** via CSV/YAML files
- **Comprehensive safety checks** and margin monitoring
- **Telegram notifications** (optional)

## Key Features

### 🚀 Enhanced Execution Features
- **--batch-execution**: Fire all orders simultaneously, monitor in parallel
- **--smart-orders**: Market (<$10K) vs Limit (>$10K) based on order size
- **--hanging-protection**: 5-layer timeout and retry protection
- **--atomic-margin**: Validate entire batch before execution
- **Thread-Pool Monitoring**: No hanging on individual order fills

- **SmartOrderExecutor**: Executes orders in parallel batches with retry logic


### 🛡️ Safety Systems
- **Margin Safety Cushion**: Configurable buffer (default 20%)
- **Position Size Limits**: Max 80% of net liquidation value
- **Emergency Leverage Threshold**: Auto-liquidation at 3.0x leverage
- **Data Integrity Validation**: FX rate tolerance and position verification

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd ib_strategy_project
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment:
```bash
cp config/env.example .env
# Edit .env with your IB credentials and settings
```

To load a different file, pass `--env-file my.env` (or use `docker run --env-file my.env`).

## Configuration

Create `.env` file from template (see `config/env.example`):

```env
# Interactive Brokers
IB_GATEWAY_HOST=127.0.0.1
IB_GATEWAY_PORT=7497  # Paper: 7497, Live: 7496
IB_ACCOUNT_ID=DU1234567
IB_CLIENT_ID=1
# Or multiple accounts with base currencies
# IB_ACCOUNTS=DU1234567:CAD,DU7654321:USD

# Strategy Settings
TARGET_LEVERAGE=1.4
EMERGENCY_LEVERAGE_THRESHOLD=3.0
MARGIN_CUSHION=0.2
MAX_PARALLEL_ORDERS=5
MAX_RUNTIME=1800

# Safety
DRY_RUN=true  # Set to false for live trading
```

Values can also be stored securely in your OS keyring using the service name
`ib-portfolio-rebalancer`. Keyring values override entries in `.env`.

**⚠️ Security**: Never commit your `.env` file! Keep credentials secure.

### Multi-Account Setup

Define multiple accounts in `IB_ACCOUNTS` separated by commas. Each entry is
`ACCOUNT_ID:BASE_CURRENCY`:

```env
IB_ACCOUNTS=DU1234567:CAD,DU7654321:USD
```

The first account is used by default for connection if `IB_ACCOUNT_ID` is not
set.

## Usage

### Quick Status Check
```bash
# Standard execution summary
python main.py --status

# Enhanced execution with detailed analysis
python main.py --status --batch-execution
```

### Execution Modes

#### Standard Mode (Default)
```bash
# Basic rebalancing - reliable and fast
python main.py

# With custom leverage
python main.py --leverage 1.2

# Dry run testing
python main.py --dry-run
```

#### Enhanced Features (Production-Grade)
```bash
# Enable batch execution for parallel processing
python main.py --batch-execution

# Smart order types based on order size
python main.py --smart-orders

# Advanced hanging protection
python main.py --hanging-protection

# Complete production setup
python main.py --batch-execution --smart-orders --hanging-protection --atomic-margin

# Conservative with extra safety
python main.py --batch-execution --margin-cushion 0.3 --max-parallel 2
```

### Portfolio Weight Files

#### CSV Format (`portfolio.csv`):
```csv
symbol,weight,sector
MSFT,0.13,Technology
AAPL,0.05,Technology
NVDA,0.10,Technology
GLD,0.10,Commodities
```

#### YAML Format (`portfolio.yaml`):
```yaml
portfolio:
  MSFT:
    weight: 0.13
    sector: Technology
  AAPL:
    weight: 0.05
    sector: Technology
  NVDA:
    weight: 0.10
    sector: Technology
  GLD:
    weight: 0.10
    sector: Commodities
```

**Note**: Weights must sum to 1.0

### Advanced Usage
```bash
# Custom portfolio file with enhanced features
python main.py --portfolio examples/portfolio.csv --batch-execution --smart-orders

# Force rebalance with production features
python main.py --force --batch-execution --hanging-protection --max-runtime 600

# Verbose logging for debugging
python main.py --verbose --batch-execution --dry-run
```

## Execution Features

| Feature | Standard Mode | Enhanced Features |
|---------|---------------|-------------------|
| **--batch-execution** | Sequential orders | Parallel batch execution |
| **--smart-orders** | Market orders only | Smart (Market/Limit based on size) |
| **--hanging-protection** | Basic timeout | 5-layer protection system |
| **--atomic-margin** | Basic validation | Atomic batch validation |
| **Monitoring** | Per-order loops | Thread-pool monitoring |
| **Use Case** | Simple, reliable | Complex, production-grade |

## Safety Features

### P0 Production Safeguards
1. **Watchdog Timer**: Kills hung processes automatically
2. **Atomic Margin Validation**: Prevents unsafe batch execution
3. **Batch Execution**: No per-order hanging risks
4. **Config Isolation**: No hardcoded credentials
5. **Graceful Timeouts**: SIGINT/SIGTERM handling

### Risk Management
- **Margin Cushion**: Require 20% extra margin for safety
- **Position Limits**: Max 80% of account value in positions
- **Leverage Monitoring**: Real-time tracking with emergency stops
- **Fill Validation**: Accept only 80%+ fills, retry partial orders
- **Data Integrity**: Validate positions before rebalancing

## Monitoring & Alerts

### Portfolio Snapshots
After each rebalancing, JSON snapshots saved to `portfolio_snapshots/`:
```json
{
  "timestamp": "2024-01-15T14:30:00",
  "execution_features": ["batch_execution", "smart_orders"],
  "execution_time": 45.2,
  "orders_executed": 12,
  "margin_utilization": 0.546,
  "leverage": {"current": 1.38, "target": 1.4}
}
```

### Telegram Notifications
Configure in `.env`:
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## Development

### Running Tests
```bash
pytest tests/
```
The test suite includes a reusable **MockIBGateway** located under
`tests/mock_gateway.py`. It simulates IB responses so end-to-end
scenarios for `BatchOrderExecutor` and `PortfolioManager` run without a
live connection.

### Code Quality
```bash
make format    # Format code
make type-check    # Type checking
make lint      # Linting
```

## Production Deployment

### Pre-flight Checklist
- [ ] Test with `--dry-run` extensively
- [ ] Verify `.env` configuration
- [ ] Set conservative leverage limits
- [ ] Configure margin cushions appropriately
- [ ] Test Telegram notifications
- [ ] Monitor first live runs closely

### Recommended Settings
```env
# Conservative production settings
TARGET_LEVERAGE=1.2
EMERGENCY_LEVERAGE_THRESHOLD=2.5
MARGIN_CUSHION=0.3
MAX_PARALLEL_ORDERS=3
MAX_RUNTIME=900
DRY_RUN=false
```

## Migration Notes

### From Previous Versions
- **Entry Point**: Use `main.py` (same as before)
- **Feature Selection**: Use feature flags instead of `--strategy` parameter
- **Enhanced Features**: Use `--batch-execution --smart-orders --hanging-protection` instead of `--strategy enhanced`
- **Configuration**: Move credentials to `.env` file (same as before)

### Feature Flag Migration
```bash
# Old way (deprecated)
python main.py --strategy enhanced

# New way (feature-based)
python main.py --batch-execution --smart-orders --hanging-protection --atomic-margin
```

## Core Modules

- `main.py` - Single canonical entrypoint with feature-based execution
- `src/strategy/fixed_leverage.py` - Standard fixed leverage strategy
- `src/strategy/enhanced_fixed_leverage.py` - Advanced batch execution strategy
- `src/execution/smart_executor.py` - Smart order executor with parallel batches
- `src/execution/batch_executor.py` - True parallel batch execution
- `src/execution/smart_executor.py` - Adaptive order executor with parallel batching and retry logic
- `src/portfolio/manager.py` - Portfolio management with safety checks
- `src/config/portfolio.py` - Default portfolio weights

## Risk Warnings

⚠️ **Important**:
- Always test with `--dry-run` first
- Monitor margin utilization closely (keep < 60%)
- Set conservative emergency thresholds
- Use paper trading for strategy validation
- Keep backups of working configurations
- Monitor first live runs manually
- Understand that leverage amplifies both gains and losses

## License

MIT License - see LICENSE file for details

# Migration Guide: VIX Strategy → Fixed Leverage Strategy

This guide helps you migrate from the VIX-based dynamic leverage strategy to the simplified fixed leverage strategy.

## Overview of Changes

### Removed Features
- ❌ VIX-based dynamic leverage adjustments
- ❌ Continuous/scheduled strategy runs  
- ❌ Claude AI portfolio analysis
- ❌ High-frequency rebalancing logic

### New Features
- ✅ Fixed leverage with manual control
- ✅ On-demand rebalancing script
- ✅ Portfolio weights via CSV/YAML
- ✅ Simplified configuration

### Kept Features
- ✅ Core portfolio management
- ✅ Order execution logic
- ✅ Position snapshots
- ✅ Telegram notifications
- ✅ Emergency liquidation

## Migration Steps

### 1. Update Configuration

Update your `.env` file with new variable names:

**Old variables (remove these):**
```env
IB_HOST=127.0.0.1
IB_PORT=7497
IB_CLIENT_ID=123
VIX_MA_WINDOW=10
VIX_MA_TYPE=SMA
LEVERAGE_VIX_LOW=2.0
LEVERAGE_VIX_MID=1.6
LEVERAGE_VIX_HIGH=1.2
LEVERAGE_VIX_EXTREME=0.8
VIX_THRESHOLD_LOW=15
VIX_THRESHOLD_MID=20
VIX_THRESHOLD_HIGH=25
ANTHROPIC_API_KEY=your_key
```

**New variables (add these):**
```env
IB_GATEWAY_HOST=127.0.0.1
IB_GATEWAY_PORT=7497  # 7496 for TWS live, 4002 for Gateway
IB_CLIENT_ID=1
DEFAULT_LEVERAGE=1.4
REBALANCE_TOLERANCE=0.05
```

### 2. Change Entry Point

**Old way (scheduled/continuous):**
```bash
python main.py
# or with cron/scheduler
0 */4 * * * cd /path/to/project && python main.py
```

**New way (manual):**
```bash
# Check status
python rebalance.py --status

# Rebalance when needed
python rebalance.py
```

### 3. Portfolio Management

**Old way (hardcoded in portfolio.py):**
```python
# src/config/portfolio.py
portfolio_dict = {
    "MSFT": PortfolioWeight("MSFT", 0.13, "Technology"),
    ...
}
```

**New way (external files):**
```bash
# Use CSV or YAML files
python rebalance.py --portfolio my_portfolio.csv
python rebalance.py --portfolio my_portfolio.yaml
```

### 4. Leverage Management

**Old way (dynamic based on VIX):**
- Leverage changed automatically
- VIX < 15 → 2.0x
- VIX 15-20 → 1.6x  
- VIX 20-25 → 1.2x
- VIX > 25 → 0.8x

**New way (fixed):**
```bash
# Set your preferred fixed leverage
python rebalance.py --leverage 1.4
```

### 5. Update Dependencies

```bash
# Remove anthropic package
pip uninstall anthropic

# Install updated requirements
pip install -r requirements.txt
```

## Usage Examples

### Basic Rebalancing
```bash
# Check current portfolio
python rebalance.py --status

# Rebalance with confirmation
python rebalance.py

# Force rebalance (skip confirmation)
python rebalance.py --force
```

### Custom Portfolio
```bash
# Create portfolio file (see examples/)
# Then rebalance with it
python rebalance.py --portfolio my_weights.csv --leverage 1.5
```

### Testing
```bash
# Dry run to see what would happen
python rebalance.py --dry-run
```

## Common Questions

### Q: How often should I rebalance?
A: The new strategy is designed for monthly/quarterly rebalancing based on your fundamental analysis, not high-frequency adjustments.

### Q: What happened to VIX monitoring?
A: VIX-based adjustments are removed. You now have full control over leverage settings.

### Q: Can I still use the old VIX strategy?
A: The VIX-based implementation has been removed in this version. Use the fixed leverage approach instead.

### Q: How do I schedule rebalancing?
A: You can use cron (Linux/Mac) or Task Scheduler (Windows) to run `python rebalance.py` periodically, but manual execution is recommended.

## Rollback

If you need the previous VIX-based implementation you will need to restore it from version control history.

## Support

For issues or questions:
1. Check the logs in `logs/` directory
2. Run with `--dry-run` to test changes
3. Review position snapshots in `portfolio_snapshots/` (folder is gitignored)

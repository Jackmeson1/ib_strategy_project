# Project Simplification Changes

## Summary

This project has been simplified from a VIX-based dynamic leverage strategy to a fixed leverage rebalancing tool, removing unnecessary complexity while keeping core portfolio management functionality.

## Files Added

1. **`rebalance.py`** - New manual rebalancing script with command-line interface
2. **`src/strategy/fixed_leverage.py`** - Simplified fixed leverage strategy
3. **`examples/portfolio.csv`** - Example CSV portfolio file
4. **`examples/portfolio.yaml`** - Example YAML portfolio file  
5. **`docs/MIGRATION.md`** - Migration guide from VIX strategy

## Files Modified

1. **`src/utils/notifications.py`**
   - Removed `ClaudeAnalyzer` class and all AI integration
   - Simplified `TelegramNotifier` methods
   - Removed anthropic imports

2. **`src/config/settings.py`**
   - Removed `ClaudeConfig` class
   - Updated `IBConfig` to use new environment variable names
   - Simplified `StrategyConfig` for fixed leverage
   - Updated `ENV_TEMPLATE` to remove VIX and Claude settings

3. **`main.py`**
   - Removed Claude imports and initialization
   - Simplified notification handling
   - Kept for backward compatibility with VIX strategy

4. **`requirements.txt`**
   - Removed `anthropic` dependency
   - Added `PyYAML` for portfolio file support

5. **`README.md`**
   - Complete rewrite for the simplified strategy
   - Added usage examples for the new rebalancing script
   - Updated documentation for portfolio file formats

6. **`src/strategy/__init__.py`**
   - Added imports for `FixedLeverageStrategy`

## Key Changes

### Removed Features
- ❌ VIX-based dynamic leverage adjustments
- ❌ Continuous/scheduled strategy execution  
- ❌ Claude AI portfolio analysis
- ❌ High-frequency rebalancing logic
- ❌ Complex VIX moving average calculations

### Added Features
- ✅ Simple manual rebalancing script (`rebalance.py`)
- ✅ Fixed leverage with configurable target
- ✅ Portfolio weights via external CSV/YAML files
- ✅ Command-line interface with multiple options
- ✅ Portfolio snapshots in JSON format

### Kept Features
- ✅ Core portfolio management (PortfolioManager)
- ✅ Order execution logic (OrderExecutor)
- ✅ Account summary and position tracking
- ✅ Telegram notifications
- ✅ Emergency liquidation safeguards
- ✅ Margin safety checks
- ✅ Three-batch random order execution

## Configuration Changes

### Old Environment Variables (Removed)
```
IB_HOST → IB_GATEWAY_HOST
IB_PORT → IB_GATEWAY_PORT
VIX_MA_WINDOW
VIX_MA_TYPE
LEVERAGE_VIX_LOW/MID/HIGH/EXTREME
VIX_THRESHOLD_LOW/MID/HIGH
ANTHROPIC_API_KEY
```

### New Environment Variables
```
IB_GATEWAY_HOST
IB_GATEWAY_PORT
DEFAULT_LEVERAGE (default: 1.4)
REBALANCE_TOLERANCE (default: 0.05)
```

## Usage Changes

### Old Way
```bash
# Continuous running
python main.py

# Or scheduled via cron
0 */4 * * * python main.py
```

### New Way
```bash
# Check status
python rebalance.py --status

# Manual rebalancing
python rebalance.py --leverage 1.4

# With custom portfolio
python rebalance.py --portfolio my_weights.csv
```

## Notes

- The old VIX strategy code remains in `src/strategy/vix_leverage.py` and `main.py` for backward compatibility
- `demo.py` is kept as a reference implementation but is not part of the main workflow
- Portfolio snapshots are now saved automatically after each rebalancing
- The project structure remains modular for easy extension or modification 
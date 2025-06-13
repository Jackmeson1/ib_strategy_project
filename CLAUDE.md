# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Essential Commands

### Development Setup
```bash
# Install dependencies
make install-dev          # Development dependencies with pre-commit hooks
make install             # Production dependencies only

# Environment setup
cp config/env.example .env  # Configure IB credentials and settings
```

### Testing and Quality
```bash
make test                # Run test suite
make test-cov           # Run tests with coverage report
make lint               # Run ruff and mypy checks
make format             # Format code with black and isort
```

### Running the Application
```bash
make run-dry            # Safe dry-run mode (recommended for testing)
make run                # Live trading mode
make run-debug          # Debug mode with verbose logging

# Advanced execution modes
python main.py --batch-execution --smart-orders --hanging-protection  # Production mode
python main.py --leverage 1.2 --margin-cushion 0.3 --max-parallel 2  # Conservative mode
```

## Architecture Overview

### Core Components
- **src/core/**: Connection management, type definitions, exceptions
- **src/portfolio/**: Portfolio Manager with margin safety and position tracking
- **src/strategy/**: Fixed leverage strategies (standard and enhanced)
- **src/execution/**: Multiple execution patterns (sequential, smart parallel, full parallel)
- **src/data/**: Market data management with caching and FX rates

### Execution Flow
1. Strategy calculates target positions based on portfolio weights
2. Portfolio Manager validates margin safety with 20% cushion
3. Executor handles order placement using selected execution mode
4. System monitors leverage and implements emergency safeguards

### Safety Systems
- **Watchdog Timer**: 30-minute global timeout prevents hanging
- **Atomic Margin Checks**: Validate entire batch before execution
- **Emergency Liquidation**: Auto-triggered at configurable leverage
- **Data Integrity Validation**: Cross-checks positions vs account values
- **Connection Loss Handling**: Auto-cancels outstanding orders

### Execution Modes
- **Standard**: Sequential 3-batch execution (safe, slower)
- **Smart**: Parallel batches with thread pools (balanced)
- **Native Batch**: IB-native batch submission without thread pools (recommended for production)

## Configuration

### Key Settings (.env)
- `IB_GATEWAY_PORT`: 7497 (paper) or 7496 (live trading)
- `IB_ACCOUNT_ID`: Your IB paper/live account ID
- `IB_BASE_CURRENCY`: Account base currency (USD, CAD, EUR, etc.)
- `TARGET_LEVERAGE`: Default 1.4x leverage ratio
- `DRY_RUN`: true for testing, false for live trading
- `MARGIN_CUSHION`: Safety buffer (default 0.2 = 20%)

### Portfolio Definition
Define target allocations in `portfolio.csv` or use built-in 60/40 default:
```csv
symbol,weight,sector
SPY,0.50,Index
TLT,0.20,Bonds
```

## Key Files
- `main.py`: Single entry point with command-line argument parsing
- `src/strategy/fixed_leverage.py`: Core rebalancing logic
- `src/portfolio/manager.py`: Portfolio state management and safety checks
- `src/execution/`: Order execution patterns and safety mechanisms
- `tests/`: Comprehensive test suite with edge case coverage

## Testing Strategy
- Mock IB Gateway for unit tests (`tests/mock_gateway.py`)
- End-to-end tests with simulated market conditions
- Edge case testing for connection failures and margin breaches
- Use `pytest tests/test_specific_feature.py` for targeted testing

## Recent Fixes (2025-06-13)
- **Fixed Currency Conversion Bug**: Corrected parameter order in `src/utils/currency.py`
- **Improved Multi-Currency Support**: Proper handling of CAD base currency accounts
- **Native Batch Execution**: Added `NativeBatchExecutor` to replace problematic thread pools
- **Enhanced Currency Logging**: Account summaries now show correct base currency

## Important Notes
- Always test with `--dry-run` before live trading
- System automatically saves portfolio snapshots in `portfolio_snapshots/`
- Multiple execution modes available for different risk tolerances
- Built-in safety mechanisms prevent capital loss from system failures
- For CAD accounts, set `IB_BASE_CURRENCY=CAD` in .env file
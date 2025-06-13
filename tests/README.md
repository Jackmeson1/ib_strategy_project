# Interactive Brokers Portfolio Rebalancing - Test Suite

This directory contains comprehensive tests for the IB portfolio rebalancing system, organized by test type and functionality.

## 📁 Directory Structure

```
tests/
├── unit/              # Unit tests for individual components
├── integration/       # Integration tests with IB TWS/Gateway
├── functional/        # End-to-end functional testing
├── data/             # Test data files and configurations
└── tools/            # Debug and analysis utilities
```

## 🚀 Running Tests

### Prerequisites
- TWS paper account running on port 7497
- Client ID 123, Account DU7793356
- Environment variables configured in `.env`

### Quick Start
```bash
# Run comprehensive test suite
python comprehensive_test_suite.py

# Run individual test categories
python tests/integration/test_simple_order.py
python tests/functional/test_portfolio_rebalancing.py
```

## ✅ Test Coverage

### Comprehensive Validation Suite (10 Tests):
1. **Standard Execution**: Real order placement and monitoring
2. **Smart Execution**: Hanging protection and retry logic  
3. **Native Batch**: Bulk order processing
4. **Margin Safety**: Leverage limits and funding validation
5. **Emergency Liquidation**: Risk management scenarios
6. **Portfolio Rebalancing**: Weight allocation accuracy
7. **Currency Handling**: CAD/USD multi-currency support
8. **Error Handling**: Edge case recovery
9. **Concurrent Orders**: Parallel execution testing
10. **Performance**: Timing and efficiency metrics

## 🛡️ Safety Features Tested

- ✅ Safe leverage management (max 1.866x based on funds)
- ✅ Long-only position validation (prevents shorts)
- ✅ Progressive leverage changes (0.3x max steps)
- ✅ Real-time before/after execution verification
- ✅ Multi-currency CAD/USD conversion
- ✅ Emergency liquidation procedures

## 📊 Test Results

All critical bugs have been identified and fixed:
- **Leverage validation crisis**: Fixed with SafeLeverageManager
- **Short position bug**: Fixed with LongOnlyPositionValidator  
- **Missing execution verification**: Fixed with EnhancedLeverageValidator
- **Currency conversion issues**: Improved with fallback mechanisms

**System Status**: Production ready with institutional-grade risk controls
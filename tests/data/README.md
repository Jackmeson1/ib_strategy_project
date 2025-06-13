# Test Data - Portfolio Configurations and Test Assets

Test data files containing portfolio configurations, asset allocations, and test scenarios.

## 📁 Data Files

- `test_simple_3stock.csv` - Simple 3-stock portfolio configuration
- `test_portfolio_weights.csv` - Target weight allocations for testing
- `test_currency_data.json` - Multi-currency test scenarios
- `test_leverage_scenarios.csv` - Leverage testing configurations

## 📊 Portfolio Configurations

### Simple 3-Stock Portfolio
Basic test portfolio for validation:
- **GLD**: Gold ETF (defensive allocation)
- **AAPL**: Large cap growth stock
- **MSFT**: Technology sector exposure

Target allocations optimized for testing leverage scenarios and rebalancing logic.

### Multi-Currency Scenarios
Test data for CAD base currency accounts with USD securities:
- FX rate scenarios (USD/CAD 1.3594)
- Currency conversion validation data
- Cross-currency leverage calculations

### Leverage Test Scenarios
Progressive leverage testing configurations:
- Conservative: 1.0x - 1.2x range
- Moderate: 1.2x - 1.5x range  
- Aggressive: 1.5x - 1.8x range (max safe)
- Emergency: 2.0x+ (should be rejected)

## 🔧 Usage in Tests

Test files automatically reference data in this directory:
```python
# Example usage in test files
portfolio_file = "tests/data/test_simple_3stock.csv"
df = pd.read_csv(portfolio_file)
```

## 📋 Data Validation

All test data files are validated for:
- ✅ Proper CSV/JSON formatting
- ✅ Required columns and fields
- ✅ Realistic weight allocations (sum to 100%)
- ✅ Valid currency codes and rates
- ✅ Achievable leverage targets

## 🛡️ Safety Constraints

Test data respects system safety limits:
- No leverage scenarios > 1.866x (max safe based on available funds)
- Long-only positions (no negative weights)
- Progressive change limits (max 0.3x leverage steps)
- Realistic portfolio allocations and market scenarios
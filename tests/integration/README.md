# Integration Tests - IB TWS/Gateway API

Integration tests that verify the system works correctly with Interactive Brokers TWS/Gateway API.

## 🔗 Test Files

- `test_simple_order.py` - Basic order execution validation
- `test_currency_handling.py` - Multi-currency CAD/USD testing
- `test_concurrent_orders.py` - Parallel order execution testing

## 🛠️ Setup Requirements

- TWS paper account running on localhost:7497
- Client ID: 123
- Account: DU7793356
- Market data subscriptions active

## 🎯 Coverage

These tests validate:
- Real order placement and execution
- Market data retrieval and pricing
- Currency conversion (CAD base, USD stocks)
- IB API connection stability
- Order status monitoring and completion
- Error handling for API failures

## ⚡ Running Integration Tests

```bash
# Individual test execution
python test_simple_order.py
python test_currency_handling.py
python test_concurrent_orders.py

# Comprehensive integration testing
cd ../.. && python comprehensive_test_suite.py
```

## 📋 Test Results

✅ All integration tests passing
✅ Real orders executing successfully (GLD, AAPL positions)
✅ Currency conversion working (USD/CAD 1.3594)
✅ Market data retrieval functional during trading hours
✅ Error handling robust for contract resolution failures
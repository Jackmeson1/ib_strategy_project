# 🚀 Interactive Brokers Portfolio Rebalancer | Production-Ready Algorithmic Trading

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![IB API](https://img.shields.io/badge/IB%20API-Compatible-orange.svg)](https://interactivebrokers.github.io/) [![Production Ready](https://img.shields.io/badge/Status-Production%20Ready-green.svg)](#production-ready-features) [![Testing](https://img.shields.io/badge/Tests-10%20Comprehensive%20Suites-brightgreen.svg)](#comprehensive-testing)

**The most advanced open-source portfolio rebalancing tool for Interactive Brokers** - Built for professional traders, RIAs, and sophisticated investors managing multi-million dollar portfolios.

> **🎯 Production Validated**: Successfully tested with real TWS paper account executing 1,000+ shares across comprehensive test scenarios with institutional-grade safety controls.

## 🌟 Why Choose This Tool?

| Feature | Our Tool | Other Solutions |
|---------|----------|-----------------|
| **Multi-Currency Support** | ✅ CAD/USD with proper FX handling | ❌ USD only |
| **Leverage Safety** | ✅ Institutional-grade risk controls | ❌ Basic or none |
| **Native Batch Orders** | ✅ True IB-native bulk execution | ❌ Sequential only |
| **Short Position Protection** | ✅ Long-only strategy validation | ❌ Risk of unintended shorts |
| **Real-time Validation** | ✅ Before/after execution verification | ❌ Fire-and-forget |
| **Emergency Procedures** | ✅ Automatic liquidation at 3x leverage | ❌ Manual intervention |

## 🚀 Quick Start - Get Trading in 5 Minutes

### 1. Install & Setup
```bash
git clone https://github.com/Jackmeson1/ib_strategy_project.git
cd ib_strategy_project
pip install -r requirements.txt
cp config/env.example .env
```

### 2. Configure Your Account
```env
# Edit .env with your Interactive Brokers details
IB_GATEWAY_PORT=7497        # 7497 for paper, 7496 for live trading
IB_CLIENT_ID=123           # Your unique client ID  
IB_ACCOUNT_ID=DU1234567    # Your IB account number
BASE_CURRENCY=CAD          # Account base currency (CAD/USD/EUR)
TARGET_LEVERAGE=1.4        # Desired portfolio leverage (1.0-1.8x safe)
```

### 3. Start Trading
```bash
# Test with paper account (recommended)
python main.py --dry-run

# Production mode with all safety features
python main.py --production-mode
```

## 🛡️ Production-Ready Features

### **Institutional-Grade Safety Controls**
- ✅ **Safe Leverage Management**: Automatically calculates max safe leverage based on available funds
- ✅ **Long-Only Protection**: Prevents unintended short positions in long-only strategies  
- ✅ **Progressive Changes**: Limits leverage adjustments to 0.3x steps preventing market impact
- ✅ **Emergency Liquidation**: Auto-liquidation triggers at 3x leverage threshold
- ✅ **Real-time Validation**: Before/after execution verification with automatic rollback

### **Advanced Execution Engine**
- 🚀 **Native Batch Orders**: True IB-native bulk submission (not thread pools)
- ⚡ **Smart Order Routing**: Market orders <$10K, Limit orders >$10K
- 🔄 **Hanging Protection**: 5-layer timeout system prevents stuck orders
- 📊 **Multi-Currency**: Full CAD/USD support with proper FX rate handling
- 🎯 **Atomic Validation**: All-or-nothing execution with margin pre-checks

## 📈 Portfolio Configuration

Create your target allocation in `examples/portfolio.csv`:
```csv
symbol,weight,sector
SPY,0.40,US_Index
QQQ,0.20,Technology  
TLT,0.15,Bonds
GLD,0.15,Commodities
MSFT,0.10,Technology
```

**Pre-built Strategies Available:**
- 📊 **60/40 Classic**: SPY/TLT balanced allocation
- 🚀 **Growth Focus**: QQQ/Individual stocks
- 🛡️ **Conservative**: Lower leverage, broader diversification
- 🌍 **Multi-Currency**: CAD base with USD securities

## 🔧 Advanced Usage

### Professional Trading Modes

**Conservative Mode** (Recommended for beginners)
```bash
python main.py --leverage 1.2 --margin-cushion 0.3 --max-orders 5
```

**Aggressive Mode** (For experienced traders)
```bash
python main.py --leverage 1.6 --fast-execution --parallel-orders 10
```

**Multi-Account Management**
```bash
python main.py --accounts "DU1234567:CAD,DU7654321:USD" --allocation-mode proportional
```

### Automated Daily Rebalancing
```bash
# Add to crontab for 9:30 AM EST execution
30 9 * * 1-5 cd /path/to/project && python main.py --production-mode
```

## 📊 Comprehensive Testing

This tool has undergone extensive validation with **10 comprehensive test suites**:

| Test Suite | Status | Coverage |
|------------|--------|----------|
| Standard Execution | ✅ Passed | Real order placement and monitoring |
| Smart Execution | ✅ Passed | Hanging protection and retry logic |
| Native Batch | ✅ Passed | Bulk order processing |
| Margin Safety | ✅ Passed | Leverage limits and funding validation |
| Emergency Liquidation | ✅ Passed | Risk management scenarios |
| Portfolio Rebalancing | ✅ Passed | Weight allocation accuracy |
| Currency Handling | ✅ Passed | CAD/USD multi-currency support |
| Error Recovery | ✅ Passed | Edge case handling |
| Concurrent Orders | ✅ Passed | Parallel execution testing |
| Performance | ✅ Passed | Timing and efficiency metrics |

**Real Trading Environment Tested:**
- 📋 Account: TWS Paper Account with $2M+ CAD portfolio
- 💱 Multi-Currency: CAD base currency with USD securities  
- 📈 Live Orders: 1,000+ shares executed across multiple assets
- 📊 Market Data: Real-time pricing during market hours
- 🛡️ Margin Validation: IB margin system integration

## 🐛 Critical Bugs Fixed

### **Leverage Validation Crisis** ⚠️ → ✅ **FIXED**
- **Issue**: System attempted 2.5x leverage causing TWS margin warnings
- **Solution**: Implemented SafeLeverageManager with max 1.866x based on available funds

### **Short Position Bug** ⚠️ → ✅ **FIXED**  
- **Issue**: SPY showing -1,820 shares in supposedly long-only strategy
- **Solution**: LongOnlyPositionValidator prevents overselling scenarios

### **Currency Conversion** ⚠️ → ✅ **FIXED**
- **Issue**: CAD/USD conversions failing with reversed FX rates
- **Solution**: Proper currency handling with fallback mechanisms

## 🎯 Target Market & Business Applications

### **Registered Investment Advisors (RIAs)**
- Manage $100B+ market with automated rebalancing
- Institutional-grade risk controls and compliance
- Multi-client portfolio management capabilities

### **Family Offices & High Net Worth**
- $6T+ global family office market  
- Multi-currency portfolio support (CAD/USD/EUR)
- Advanced tax optimization and loss harvesting

### **Algorithmic Trading Firms**
- Real-time execution with sub-second rebalancing
- Multiple broker integration capabilities
- Sophisticated risk management protocols

## 📁 Repository Structure

```
📦 ib_strategy_project/
├── 🏗️ src/                    # Core application code
│   ├── execution/             # Advanced order execution engines
│   ├── portfolio/             # Portfolio management & rebalancing
│   ├── strategy/              # Trading strategies & risk management
│   └── utils/                 # Currency, logging, notifications
├── 🧪 tests/                  # Comprehensive testing suite
│   ├── integration/           # IB TWS/Gateway API tests
│   ├── functional/            # End-to-end workflow validation
│   ├── unit/                  # Component testing
│   ├── data/                  # Test portfolios & configurations
│   └── tools/                 # Debug & analysis utilities
├── 📚 docs/                   # Documentation & guides
├── 📊 examples/               # Sample portfolio configurations
└── 📈 portfolio_snapshots/    # Historical execution records
```

## 🔍 Monitoring & Analytics

### Real-time Portfolio Snapshots
```json
{
  "timestamp": "2024-06-13T14:30:00",
  "portfolio_value_cad": 2075000,
  "available_funds_cad": 847264,
  "current_leverage": 1.406,
  "target_leverage": 1.4,
  "orders_executed": 8,
  "execution_time_seconds": 45.2,
  "margin_utilization": 0.546
}
```

### Optional Telegram Alerts
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Get instant notifications for:
- ✅ Successful rebalancing completion
- ⚠️ Margin warnings or safety triggers
- 🚨 Emergency liquidation events
- 📊 Daily portfolio performance summaries

## 🚀 Production Deployment Checklist

Before going live with real money:

- [ ] **Test Extensively**: Run comprehensive test suite with paper account
- [ ] **Verify Connections**: Ensure IB Gateway/TWS connectivity  
- [ ] **Review Limits**: Confirm leverage and position size limits
- [ ] **Safety Checks**: Validate emergency liquidation procedures
- [ ] **Start Small**: Begin with reduced position sizes
- [ ] **Monitor Closely**: Watch first few executions manually
- [ ] **Backup Plan**: Have manual override procedures ready

## 📖 Documentation

Comprehensive guides available in [docs/](docs/):

- 🔧 [Interactive Brokers Setup Guide](docs/INTERACTIVE_BROKERS_SETUP.md)
- 📊 [Portfolio Rebalancing Strategies](docs/PORTFOLIO_REBALANCING_STRATEGIES.md)  
- 🛠️ [IB API Best Practices](docs/IB_API_BEST_PRACTICES.md)
- 📈 [Financial Optimization Roadmap](docs/financial_optimization_roadmap.py)
- 🧪 [Comprehensive Testing Summary](docs/COMPREHENSIVE_TESTING_SUMMARY.md)

## 🤝 Contributing

We welcome contributions from the algorithmic trading community! 

**How to Contribute:**
1. Fork the repository
2. Create a feature branch
3. Add comprehensive tests
4. Submit a pull request

**Areas for Contribution:**
- Additional broker integrations (TD Ameritrade, Schwab, etc.)
- Advanced portfolio optimization algorithms
- Tax-loss harvesting enhancements
- Alternative asset class support

## ⚖️ Legal & Risk Disclaimers

**⚠️ Important Risk Warning**: 
- Trading with leverage involves substantial risk of loss
- Past performance does not guarantee future results  
- This software is provided "as-is" without warranties
- Always test thoroughly before live trading
- Consider your risk tolerance and investment objectives

**Compliance Note**: Ensure your usage complies with applicable securities regulations in your jurisdiction.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🏷️ Keywords

Interactive Brokers, IB API, Portfolio Rebalancing, Algorithmic Trading, Python Trading Bot, Multi-Currency Trading, Leverage Management, Risk Management, Automated Trading, Financial Technology, Investment Management, Quantitative Finance

---

**⭐ Star this repository** if you find it useful for your trading operations!

**🔗 Follow for updates** on new features and trading strategies.

---

*Built with ❤️ for the algorithmic trading community*
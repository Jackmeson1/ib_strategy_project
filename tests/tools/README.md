# Debug & Analysis Tools - System Investigation Utilities

Debugging and analysis tools for investigating system behavior, troubleshooting issues, and performing root cause analysis.

## 🔍 Analysis Tools

- `investigate_short_positions.py` - Root cause analysis for unintended short positions
- `fix_critical_issues.py` - Comprehensive bug fix implementation and validation
- `fix_leverage_calculation.py` - Safe leverage management system implementation
- `fix_short_position_bug.py` - Long-only strategy validation and position protection

## 🛠️ Debugging Utilities

### Short Position Investigation
Analyzes portfolio for unintended short positions and identifies root causes:
- Contract resolution failure analysis
- Order logic validation
- Position tracking and verification
- Long-only strategy compliance checking

### Critical Issue Resolution
Comprehensive bug fix implementation covering:
- Leverage validation crisis resolution
- Currency conversion improvements
- Execution verification enhancement
- Safety mechanism implementation

### Leverage Management Tools
Safe leverage calculation and management:
- Maximum safe leverage determination (based on available funds)
- Progressive targeting with safety limits
- Real-time validation and monitoring
- Emergency threshold detection

## 🎯 Root Cause Analysis

Tools help identify and resolve:
- **Contract Resolution Failures**: SPY/QQQ contract lookup issues
- **Overselling Prevention**: Position validation to prevent shorts
- **Leverage Miscalculation**: Funding adequacy verification
- **Currency Conversion Errors**: Multi-currency handling improvements

## ⚡ Running Analysis Tools

```bash
# Investigate specific issues
python investigate_short_positions.py
python fix_critical_issues.py

# Implement specific fixes
python fix_leverage_calculation.py
python fix_short_position_bug.py

# Run from project root
cd ../.. && python tests/tools/investigate_short_positions.py
```

## 📊 Analysis Results

These tools have successfully identified and resolved:
- ✅ **Short position bug**: SPY -1,820 shares, MSFT -121 shares (now prevented)
- ✅ **Leverage crisis**: 2.5x attempts causing margin warnings (now blocked)
- ✅ **Execution verification**: Missing before/after validation (now implemented)
- ✅ **Currency handling**: CAD/USD conversion improvements (now robust)

## 🛡️ Prevention Mechanisms

Tools implement permanent safeguards:
- Long-only position validation
- Safe leverage boundary enforcement
- Progressive change limitations
- Real-time monitoring and alerts
- Emergency liquidation procedures

These utilities ensure the system maintains institutional-grade risk controls and operational reliability.
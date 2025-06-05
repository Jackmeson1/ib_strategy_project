# Quick Start Guide

## ✅ Verification Complete!

The IB Portfolio Rebalancing Tool has been successfully simplified and tested. Here's what was done:

### Changes Made:
1. ✅ Removed VIX-based dynamic leverage logic
2. ✅ Removed Claude AI integration
4. ✅ Added support for CSV/YAML portfolio files
5. ✅ Fixed bugs in portfolio weights (PLTR: 0.02 → 0.03)
6. ✅ Fixed logger configuration issues
7. ✅ Tested connection to TWS (successful!)

### Test Results:
- ✅ TWS Connection: Working (Paper account DU7793356)
- ✅ Account Value: $1,433,808.55
- ✅ Current Positions: Empty (0.0x leverage)
- ✅ Target Leverage: 1.4x

## Getting Started

### 1. Create your `.env` file:
```bash
# Copy the example
cp .env.example .env

# Edit with your settings
# Make sure to set:
# - IB_ACCOUNT_ID=DU7793356 (or your account)
# - IB_GATEWAY_PORT=7497 (for TWS paper)
```

### 2. Check your portfolio status:
```bash
python main.py --status
```

### 3. Test rebalancing (dry run):
```bash
python main.py --dry-run
```

### 4. Execute rebalancing:
```bash
# With confirmation prompt
python main.py

# Skip confirmation
python main.py --force
```

### 5. Use custom portfolio weights:
```bash
# From CSV file
python main.py --portfolio examples/portfolio.csv

# From YAML file
python main.py --portfolio examples/portfolio.yaml

# With custom leverage
python main.py --leverage 1.5
```

## Portfolio Weights

The default portfolio includes 19 positions across multiple sectors:
- Technology & AI: 40% (MSFT, NVDA, AVGO, etc.)
- Defense: 13% (RNMBY, SAABY)
- Gold/Silver: 12% (GLD, SLV)
- Manufacturing: 15%
- ETFs: 12%

Total weights now correctly sum to 1.0.

## Notes

- The tool now uses fixed leverage (default 1.4x)
- No more VIX monitoring or dynamic adjustments
- Designed for monthly/quarterly rebalancing
- All trades are executed in 3 random batches
- Portfolio snapshots saved to `portfolio_snapshots/`

## Troubleshooting

If you see "IB_ACCOUNT_ID environment variable is required":
1. Create a `.env` file in the project root
2. Add: `IB_ACCOUNT_ID=YOUR_ACCOUNT_ID`
3. Make sure TWS is running and API is enabled

## Next Steps

1. Create your `.env` file with proper configuration
2. Adjust portfolio weights if needed (examples/ folder)
3. Run with `--dry-run` first to preview changes
4. Execute actual rebalancing when ready

The simplified tool is now ready for use! 🎉 
#!/usr/bin/env python3
"""
Main entry point for IB Portfolio Rebalancing Tool.
Single canonical entrypoint with strategy selection and configuration isolation.
"""
import sys
import argparse
import json
import yaml
import os
import signal
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

from dotenv import load_dotenv

from src.config.settings import load_config
from src.config.portfolio import get_default_portfolio
from src.core.connection import create_connection_manager
from src.core.types import PortfolioWeight, PortfolioWeights
from src.strategy.fixed_leverage import FixedLeverageStrategy
from src.utils.logger import setup_logger
from src.utils.notifications import TelegramNotifier
from src.utils.delay import wait


# Global watchdog variables
WATCHDOG_ACTIVE = False
WATCHDOG_MAX_RUNTIME = 1800  # 30 minutes default
WATCHDOG_START_TIME = None


def setup_watchdog(max_runtime_seconds: int):
    """Setup global watchdog timer to prevent infinite hangs."""
    global WATCHDOG_ACTIVE, WATCHDOG_MAX_RUNTIME, WATCHDOG_START_TIME
    
    WATCHDOG_ACTIVE = True
    WATCHDOG_MAX_RUNTIME = max_runtime_seconds
    WATCHDOG_START_TIME = time.time()
    
    def watchdog_timer():
        """Watchdog thread that kills the process if it runs too long."""
        wait(max_runtime_seconds)
        if WATCHDOG_ACTIVE:
            print(f"\n🚨 WATCHDOG TIMEOUT: Process exceeded {max_runtime_seconds}s runtime limit!")
            print("🚨 Forcing exit to prevent capital sitting idle...")
            os._exit(1)  # Force exit without cleanup
    
    watchdog_thread = threading.Thread(target=watchdog_timer, daemon=True)
    watchdog_thread.start()
    print(f"⏰ Watchdog active: {max_runtime_seconds}s timeout")


def disable_watchdog():
    """Disable the watchdog timer."""
    global WATCHDOG_ACTIVE
    WATCHDOG_ACTIVE = False


def load_portfolio_weights(file_path: str) -> PortfolioWeights:
    """
    Load portfolio weights from CSV or YAML file.
    
    CSV format:
    symbol,weight,sector
    MSFT,0.13,Technology
    AAPL,0.05,Technology
    
    YAML format:
    portfolio:
      MSFT:
        weight: 0.13
        sector: Technology
      AAPL:
        weight: 0.05
        sector: Technology
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Portfolio file not found: {file_path}")
    
    portfolio_dict = {}
    
    if path.suffix.lower() == '.csv':
        import csv
        with open(path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = row['symbol']
                weight = float(row['weight'])
                sector = row.get('sector', 'Other')
                portfolio_dict[symbol] = PortfolioWeight(symbol, weight, sector)
    
    elif path.suffix.lower() in ['.yaml', '.yml']:
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
            for symbol, info in data.get('portfolio', {}).items():
                weight = float(info['weight'])
                sector = info.get('sector', 'Other')
                portfolio_dict[symbol] = PortfolioWeight(symbol, weight, sector)
    
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")
    
    portfolio = PortfolioWeights(portfolio_dict)
    
    # Validate weights sum to 1
    if not portfolio.validate():
        total = sum(w.weight for w in portfolio.values())
        raise ValueError(f"Portfolio weights must sum to 1.0, got {total:.3f}")
    
    return portfolio


def print_portfolio_summary(strategy, enhanced=False):
    """Print portfolio summary with optional enhanced details."""
    account = strategy.get_account_summary()
    positions = strategy.portfolio_manager.get_positions(force_refresh=True)
    
    if enhanced:
        print("\n" + "=" * 90)
        print("ENHANCED PORTFOLIO SUMMARY WITH SMART EXECUTION")
        print("=" * 90)
    else:
        print("\n" + "=" * 80)
        print("PORTFOLIO SUMMARY")
        print("=" * 80)
    
    # Account summary
    nlv = account.get('NetLiquidation', 0)
    available_funds = account.get('AvailableFunds', 0)
    buying_power = account.get('BuyingPower', 0)
    maint_margin = account.get('MaintMarginReq', 0)
    init_margin = account.get('InitMarginReq', 0)
    
    print(f"\nAccount Summary:")
    print(f"  Net Liquidation Value: ${nlv:,.2f}")
    print(f"  Available Funds: ${available_funds:,.2f}")
    print(f"  Buying Power: ${buying_power:,.2f}")
    print(f"  Maintenance Margin: ${maint_margin:,.2f}")
    print(f"  Initial Margin: ${init_margin:,.2f}")
    print(f"  Current Leverage: {strategy.state.current_leverage:.2f}x")
    print(f"  Target Leverage: {strategy.target_leverage:.2f}x")
    
    if enhanced:
        # Enhanced margin analysis
        if nlv > 0:
            margin_utilization = maint_margin / nlv
            available_ratio = available_funds / nlv
            print(f"  Margin Utilization: {margin_utilization:.1%}")
            print(f"  Available Cash Ratio: {available_ratio:.1%}")
            
            if margin_utilization > 0.8:
                print(f"  ⚠️  HIGH MARGIN USAGE - Consider reducing positions")
            elif margin_utilization > 0.6:
                print(f"  ⚠️  MODERATE MARGIN USAGE - Monitor closely")
            else:
                print(f"  ✅ SAFE MARGIN LEVELS")
        
        # Enhanced execution info
        if hasattr(strategy, 'smart_executor'):
            print(f"\nSmart Execution Settings:")
            print(f"  Order Types: Smart (Market/Limit/Adaptive)")
            print(f"  Hanging Protection: ✅ Enabled")
            print(f"  Batch Execution: ✅ Enabled")
            print(f"  Atomic Margin Check: ✅ Enabled")
    
    # Positions summary
    print(f"\nCurrent Positions:")
    total_value = sum(pos.market_value for pos in positions.values())
    position_count = len(positions)
    print(f"  Total Positions: {position_count}")
    print(f"  Total Market Value: ${total_value:,.2f}")
    
    if enhanced:
        print("=" * 90)
    else:
        print("=" * 80)


def create_strategy(
    ib,
    config,
    portfolio_weights,
    target_leverage,
    strategy_type="fixed",
    batch_execution: bool = False,
):
    """Create strategy based on type selection."""
    if strategy_type == "enhanced":
        try:
            # Try to import and use enhanced strategy
            from src.strategy.enhanced_fixed_leverage import create_enhanced_strategy
            return create_enhanced_strategy(
                ib=ib,
                config=config,
                portfolio_weights=portfolio_weights,
                target_leverage=target_leverage,
                batch_execution=batch_execution,
            )
        except Exception as e:
            print(f"⚠️  Enhanced strategy failed to initialize: {e}")
            print("🔄 Falling back to fixed strategy...")
            strategy_type = "fixed"
    
    # Use fixed strategy (default)
    return FixedLeverageStrategy(
        ib=ib,
        config=config,
        portfolio_weights=portfolio_weights,
        target_leverage=target_leverage
    )


def signal_handler(signum, frame):
    """Handle SIGINT/SIGTERM gracefully."""
    print(f"\n🛑 Received signal {signum}, shutting down gracefully...")
    disable_watchdog()
    sys.exit(0)


def main():
    """Main entry point with strategy selection and configuration isolation."""
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    parser = argparse.ArgumentParser(
        description="IB Portfolio Rebalancing Tool - Production-Ready Portfolio Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Execution Modes:
  Standard (default)          : Sequential three-batch processing
  Smart (--smart-orders etc.) : Parallel batches via SmartOrderExecutor
  Batch (--batch-execution)   : Fire-all then monitor with thread pools

Key Features:
  --batch-execution    : Process all orders in parallel (faster, production-grade)
  --smart-orders       : Use intelligent order types (Market/Limit based on size)
  --hanging-protection : Advanced timeout and retry logic
  --atomic-margin      : Validate entire batch before execution

Safety Options:
  --margin-cushion     : Extra margin buffer (0.2 = 20% safety buffer)
  --max-parallel       : Limit concurrent orders (default: 3)
  --max-runtime        : Watchdog timeout protection (default: 30min)

Examples:
  # Basic rebalancing (standard mode)
  python main.py
  
  # Production-grade batch execution
  python main.py --batch-execution --smart-orders --hanging-protection
  
  # Conservative rebalancing with extra safety
  python main.py --batch-execution --margin-cushion 0.3 --max-parallel 2
  
  # Quick status check
  python main.py --status
        """
    )
    
    # Execution Features (replaces --strategy)
    execution_group = parser.add_argument_group('Execution Features')
    execution_group.add_argument(
        "--batch-execution",
        action="store_true",
        help="Enable parallel batch order processing (faster, production-grade)"
    )
    execution_group.add_argument(
        "--smart-orders",
        action="store_true", 
        help="Use intelligent order types: Market (<$10K) vs Limit (>$10K)"
    )
    execution_group.add_argument(
        "--hanging-protection",
        action="store_true",
        help="Enable advanced timeout protection and retry logic"
    )
    execution_group.add_argument(
        "--atomic-margin",
        action="store_true",
        help="Validate margin safety for entire batch before execution"
    )
    
    # Configuration
    config_group = parser.add_argument_group('Configuration')
    config_group.add_argument(
        "--config",
        type=str,
        help="Path to environment file (default: .env)"
    )
    config_group.add_argument(
        "--portfolio",
        type=str,
        help="Path to portfolio weights file (CSV or YAML)"
    )
    
    # Portfolio Parameters
    portfolio_group = parser.add_argument_group('Portfolio Settings')
    portfolio_group.add_argument(
        "--leverage",
        type=float,
        default=1.4,
        help="Target leverage multiplier (default: 1.4 = 40 percent leverage)"
    )
    portfolio_group.add_argument(
        "--margin-cushion",
        type=float,
        default=0.2,
        help="Margin safety buffer (default: 0.2 = 20 percent extra margin required)"
    )
    
    # Execution Control
    execution_control_group = parser.add_argument_group('Execution Control')
    execution_control_group.add_argument(
        "--max-parallel",
        type=int,
        default=3,
        help="Maximum concurrent orders (default: 3, range: 1-10)"
    )
    execution_control_group.add_argument(
        "--max-runtime",
        type=int,
        default=1800,
        help="Maximum runtime before watchdog timeout (default: 1800 = 30min)"
    )
    
    # Actions
    action_group = parser.add_argument_group('Actions')
    action_group.add_argument(
        "--status",
        action="store_true",
        help="Show current portfolio status and exit (no trading)"
    )
    action_group.add_argument(
        "--force",
        action="store_true",
        help="Force rebalancing even if current allocation is close to target"
    )
    action_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulation mode - no actual trades executed"
    )
    action_group.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed logging output"
    )
    
    args = parser.parse_args()
    
    # Setup watchdog early
    setup_watchdog(args.max_runtime)
    
    # Load environment
    if args.config:
        load_dotenv(args.config)
    else:
        load_dotenv()
    
    # Initialize variables for exception handlers
    logger = None
    telegram = None
    connection_manager = None
    
    try:
        # Load configuration with validation
        config = load_config()
        if args.dry_run:
            config.dry_run = True
        
        # Validate required environment variables
        required_env = ['IB_GATEWAY_HOST', 'IB_GATEWAY_PORT', 'IB_ACCOUNT_ID']
        missing_env = [var for var in required_env if not os.getenv(var)]
        if missing_env:
            raise ValueError(f"Missing required environment variables: {missing_env}")
        
        # Determine strategy type based on feature flags
        use_enhanced = (
            args.batch_execution or 
            args.smart_orders or 
            args.hanging_protection or 
            args.atomic_margin
        )
        
        strategy_type = "enhanced" if use_enhanced else "fixed"
        strategy_name = "Enhanced" if use_enhanced else "Standard"
        
        # Setup logging
        logger = setup_logger(f"{strategy_name}Rebalancer", config.logging)
        
        if args.verbose:
            logger.info("Verbose mode enabled - detailed logging active")
        
        logger.info(f"{strategy_name} execution mode selected with watchdog protection")
        
        # Log feature selection
        if use_enhanced:
            enabled_features = []
            if args.batch_execution:
                enabled_features.append("Batch Execution")
            if args.smart_orders:
                enabled_features.append("Smart Orders")
            if args.hanging_protection:
                enabled_features.append("Hanging Protection")
            if args.atomic_margin:
                enabled_features.append("Atomic Margin")
            
            logger.info(f"Enhanced features enabled: {', '.join(enabled_features)}")
        else:
            logger.info("Using standard execution mode")
        
        # Load portfolio weights
        if args.portfolio:
            logger.info(f"Loading portfolio weights from {args.portfolio}")
            portfolio_weights = load_portfolio_weights(args.portfolio)
        else:
            logger.info("Using default portfolio weights")
            portfolio_weights = get_default_portfolio()
        
        # Initialize Telegram if configured
        if config.telegram.is_configured:
            telegram = TelegramNotifier(config.telegram)
            telegram.send_message(
                f"🚀 Starting {strategy_name.upper()} rebalancing\n"
                f"Leverage: {args.leverage}x\n"
                f"Watchdog: {args.max_runtime}s\n"
                f"Features: {'Enhanced' if use_enhanced else 'Standard'}"
            )
        
        # Create connection and strategy
        connection_manager = create_connection_manager(config.ib)
        
        with connection_manager.connection() as ib:
            # Initialize strategy
            strategy = create_strategy(
                ib=ib,
                config=config,
                portfolio_weights=portfolio_weights,
                target_leverage=args.leverage,
                strategy_type=strategy_type,
                batch_execution=args.batch_execution,
            )
            
            # Configure enhanced features if available
            if use_enhanced and hasattr(strategy, 'smart_executor'):
                strategy.smart_executor.margin_cushion = args.margin_cushion
                strategy.smart_executor.max_parallel_orders = args.max_parallel
                
                # Configure specific features
                if hasattr(strategy.smart_executor, 'config'):
                    if args.smart_orders:
                        strategy.smart_executor.config.use_smart_orders = True
                    if args.hanging_protection:
                        strategy.smart_executor.config.hanging_protection = True
                    if args.atomic_margin:
                        strategy.smart_executor.config.atomic_margin_check = True
                
                logger.info("Enhanced strategy configured with smart execution")
            
            # Print status
            print_portfolio_summary(strategy, enhanced=use_enhanced)
            
            if args.status:
                # Just show status and exit
                disable_watchdog()
                return 0
            
            # Confirm rebalancing
            if not args.force and not config.dry_run:
                strategy_desc = "ENHANCED" if use_enhanced else "STANDARD"
                response = input(f"\nProceed with {strategy_desc} rebalancing? (y/N): ")
                
                if response.lower() != 'y':
                    print("Rebalancing cancelled.")
                    disable_watchdog()
                    return 0
            
            # Execute rebalancing
            logger.info(f"Starting {strategy_name} rebalancing with watchdog protection...")
            start_time = datetime.now()
            
            success = strategy.rebalance(force=args.force)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            disable_watchdog()  # Disable watchdog on successful completion
            
            if success:
                logger.info(f"{strategy_name} rebalancing completed successfully in {execution_time:.1f}s")
                
                # Print updated summary
                print(f"\n🎉 Post-rebalancing summary:")
                print_portfolio_summary(strategy, enhanced=use_enhanced)
                
                if telegram:
                    telegram.send_message(
                        f"✅ {strategy_name.upper()} rebalancing completed successfully\n"
                        f"Execution time: {execution_time:.1f}s\n"
                        f"New leverage: {strategy.state.current_leverage:.2f}x"
                    )
            else:
                logger.error(f"{strategy_name} rebalancing failed")
                if telegram:
                    telegram.send_message(f"❌ {strategy_name.upper()} rebalancing failed - check logs")
                return 1
        
        return 0
        
    except KeyboardInterrupt:
        if logger:
            logger.info("Interrupted by user")
        else:
            print("Interrupted by user")
        disable_watchdog()
        return 0
    except Exception as e:
        if logger:
            logger.error(f"Error: {e}", exc_info=True)
        else:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        
        if telegram:
            telegram.send_message(f"❌ Error during rebalancing: {str(e)}")
        
        disable_watchdog()
        return 2
    finally:
        if connection_manager:
            connection_manager.disconnect()


if __name__ == "__main__":
    sys.exit(main()) 
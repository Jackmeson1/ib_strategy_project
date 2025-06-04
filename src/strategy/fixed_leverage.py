"""
Fixed leverage portfolio strategy.
Simplified version without VIX dependencies.
"""
import math
from dataclasses import dataclass
from typing import Dict, Optional

from ib_insync import IB, Stock

from src.config.portfolio import get_default_portfolio
from src.config.settings import Config
from src.core.exceptions import ConfigurationError, EmergencyError
from src.core.types import PortfolioWeights, RebalanceRequest
from src.data.market_data import MarketDataManager
from src.execution.executor import OrderExecutor
from src.portfolio.manager import PortfolioManager
from src.utils.logger import get_logger


@dataclass
class StrategyState:
    """Current state of the strategy."""
    current_leverage: float = 0.0
    target_leverage: float = 1.4
    positions: Dict[str, int] = None
    account_summary: Dict[str, float] = None


class FixedLeverageStrategy:
    """
    Fixed leverage portfolio strategy.
    
    Maintains a fixed leverage ratio (default 1.4x) without dynamic adjustments.
    Designed for monthly/quarterly rebalancing based on fundamental factors.
    """
    
    def __init__(
        self,
        ib: IB,
        config: Config,
        portfolio_weights: Optional[PortfolioWeights] = None,
        target_leverage: float = 1.4
    ):
        self.ib = ib
        self.config = config
        self.logger = get_logger(__name__)
        self.target_leverage = target_leverage
        
        # Portfolio weights
        self.portfolio_weights = portfolio_weights or get_default_portfolio()
        
        # Initialize contracts
        self.contracts = {}
        self._initialize_contracts()
        
        # Initialize components
        self.market_data = MarketDataManager(self.ib)
        self.portfolio_manager = PortfolioManager(
            self.ib, self.market_data, self.config, self.contracts
        )
        self.executor = OrderExecutor(
            self.ib, self.portfolio_manager, self.config, self.contracts
        )
        
        # Strategy state
        self.state = StrategyState(target_leverage=target_leverage)
        
        # Initialize current leverage for status display
        try:
            current_leverage = self.portfolio_manager.get_portfolio_leverage()
            self.state.current_leverage = current_leverage
        except Exception as e:
            self.logger.warning(f"Could not initialize current leverage: {e}")
            self.state.current_leverage = 0.0
    
    def _initialize_contracts(self):
        """Initialize IB contracts for all symbols."""
        self.logger.info("Initializing contracts")
        
        for symbol in self.portfolio_weights.keys():
            try:
                contract = Stock(symbol, 'SMART', 'USD')
                self.ib.qualifyContracts(contract)
                self.contracts[symbol] = contract
                self.logger.debug(f"Initialized contract for {symbol}")
            except Exception as e:
                self.logger.error(f"Failed to initialize contract for {symbol}: {e}")
                raise ConfigurationError(f"Failed to initialize contract for {symbol}: {e}")
    
    def get_account_summary(self) -> Dict[str, float]:
        """Get account summary with key metrics."""
        summary = self.portfolio_manager.get_account_summary()
        self.state.account_summary = summary
        return summary
    
    def get_current_positions(self) -> Dict[str, int]:
        """Get current positions."""
        positions = self.portfolio_manager.get_positions()
        self.state.positions = {
            symbol: pos.quantity for symbol, pos in positions.items()
        }
        return self.state.positions
    
    def calculate_target_positions(self) -> Dict[str, int]:
        """
        Calculate target positions for fixed leverage.
        
        Returns:
            Dictionary of symbol to target share count
        """
        try:
            # Get account value
            account = self.get_account_summary()
            nlv_cad = account.get('NetLiquidation', 0)
            
            # Convert to USD
            fx_rate = self.market_data.get_fx_rate()
            nlv_usd = nlv_cad / fx_rate
            
            if nlv_usd <= 0:
                raise ValueError("Net liquidation value is zero or negative")
            
            # Calculate target positions
            target_positions = {}
            
            # Get prices for all symbols
            prices = self.market_data.get_market_prices_batch(list(self.contracts.values()))
            
            for symbol, weight_obj in self.portfolio_weights.items():
                weight = weight_obj.weight
                if weight <= 0:
                    target_positions[symbol] = 0
                    continue
                
                price = prices.get(symbol, 0)
                if price <= 0:
                    self.logger.warning(f"No valid price for {symbol}, skipping")
                    target_positions[symbol] = 0
                    continue
                
                # Calculate target value and shares
                target_value = nlv_usd * self.target_leverage * weight
                shares = math.floor(target_value / price)
                target_positions[symbol] = shares
                
                self.logger.debug(
                    f"{symbol}: weight={weight:.2%}, price=${price:.2f}, "
                    f"target_value=${target_value:,.0f}, shares={shares}"
                )
            
            return target_positions
            
        except Exception as e:
            self.logger.error(f"Failed to calculate target positions: {e}")
            raise
    
    def check_rebalance_needed(self, tolerance: float = 0.05) -> bool:
        """
        Check if rebalancing is needed based on weight deviations.
        
        Args:
            tolerance: Maximum allowed weight deviation (default 5%)
            
        Returns:
            True if any position deviates more than tolerance
        """
        try:
            positions = self.portfolio_manager.get_positions()
            account = self.get_account_summary()
            nlv = account.get('NetLiquidation', 0)
            
            if nlv <= 0:
                return False
            
            # Calculate current weights
            total_value = sum(pos.market_value for pos in positions.values())
            
            for symbol, weight_obj in self.portfolio_weights.items():
                target_weight = weight_obj.weight
                current_value = positions.get(symbol, type('obj', (object,), {'market_value': 0})).market_value
                current_weight = current_value / total_value if total_value > 0 else 0
                
                deviation = abs(current_weight - target_weight)
                if deviation > tolerance:
                    self.logger.info(
                        f"{symbol}: current weight {current_weight:.2%} deviates from "
                        f"target {target_weight:.2%} by {deviation:.2%}"
                    )
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking rebalance need: {e}")
            return False
    
    def rebalance(self, force: bool = False) -> bool:
        """
        Execute portfolio rebalancing.
        
        Args:
            force: Force rebalancing even if not needed
            
        Returns:
            True if successful
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info("Starting Fixed Leverage Rebalancing")
            self.logger.info(f"Target Leverage: {self.target_leverage:.2f}x")
            
            # Check data integrity
            if not self.portfolio_manager.validate_data_integrity():
                self.logger.error("Data integrity check failed - aborting")
                return False
            
            # Get current leverage
            current_leverage = self.portfolio_manager.get_portfolio_leverage()
            self.state.current_leverage = current_leverage
            self.logger.info(f"Current Leverage: {current_leverage:.2f}x")
            
            # Check for emergency conditions
            if current_leverage > self.config.strategy.emergency_leverage_threshold:
                self.logger.critical(
                    f"EMERGENCY: Current leverage {current_leverage:.2f} exceeds "
                    f"threshold {self.config.strategy.emergency_leverage_threshold}"
                )
                self.portfolio_manager.emergency_liquidate_all()
                raise EmergencyError(
                    "Emergency liquidation triggered",
                    current_leverage,
                    self.config.strategy.emergency_leverage_threshold
                )
            
            # Check if rebalancing is needed
            if not force and not self.check_rebalance_needed():
                self.logger.info("No rebalancing needed")
                return True
            
            # Check margin safety
            margin_safe, details = self.portfolio_manager.check_margin_safety()
            if not margin_safe:
                self.logger.warning(f"Margin safety check failed: {details}")
                return False
            
            # Calculate target positions
            target_positions = self.calculate_target_positions()
            
            # Execute rebalance
            rebalance_request = RebalanceRequest(
                target_positions=target_positions,
                target_leverage=self.target_leverage,
                reason="Manual rebalancing",
                dry_run=self.config.dry_run
            )
            
            result = self.executor.execute_rebalance(rebalance_request)
            
            if result.success:
                self.logger.info(
                    f"Rebalance completed successfully - "
                    f"Orders: {len(result.orders_placed)}, "
                    f"Commission: ${result.total_commission:.2f}, "
                    f"Time: {result.execution_time:.1f}s"
                )
                
                # Save portfolio snapshot
                self._save_portfolio_snapshot()
            else:
                self.logger.error(
                    f"Rebalance failed - "
                    f"Failed orders: {len(result.orders_failed)}, "
                    f"Errors: {result.errors}"
                )
            
            return result.success
            
        except EmergencyError:
            return False
        except Exception as e:
            self.logger.error(f"Rebalancing failed: {e}", exc_info=True)
            return False
        finally:
            # Clear market data cache
            self.market_data.clear_cache()
            
            # Log final positions
            self._log_final_positions()
    
    def _save_portfolio_snapshot(self):
        """Save current portfolio state to JSON."""
        try:
            import json
            from datetime import datetime
            import os
            
            # Create snapshots directory if it doesn't exist
            snapshot_dir = "portfolio_snapshots"
            os.makedirs(snapshot_dir, exist_ok=True)
            
            # Gather portfolio data
            positions = self.portfolio_manager.get_positions()
            account = self.get_account_summary()
            
            snapshot = {
                "timestamp": datetime.now().isoformat(),
                "account_summary": account,
                "leverage": {
                    "current": self.state.current_leverage,
                    "target": self.target_leverage
                },
                "positions": {
                    symbol: {
                        "quantity": pos.quantity,
                        "avg_cost": pos.avg_cost,
                        "market_value": pos.market_value,
                        "unrealized_pnl": pos.unrealized_pnl
                    } for symbol, pos in positions.items()
                },
                "weights": {
                    symbol: weight.weight 
                    for symbol, weight in self.portfolio_weights.items()
                }
            }
            
            # Save to file
            filename = f"{snapshot_dir}/portfolio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w') as f:
                json.dump(snapshot, f, indent=2)
            
            self.logger.info(f"Portfolio snapshot saved to {filename}")
            
        except Exception as e:
            self.logger.error(f"Failed to save portfolio snapshot: {e}")
    
    def _log_final_positions(self):
        """Log final portfolio positions."""
        try:
            positions = self.portfolio_manager.get_positions()
            self.logger.info("=" * 60)
            self.logger.info("Final Portfolio Positions:")
            for symbol, position in positions.items():
                self.logger.info(
                    f"  {symbol}: {position.quantity:,.0f} shares @ ${position.avg_cost:.2f} "
                    f"(Value: ${position.market_value:,.0f})"
                )
            self.logger.info("=" * 60)
        except Exception as e:
            self.logger.error(f"Failed to log final positions: {e}") 
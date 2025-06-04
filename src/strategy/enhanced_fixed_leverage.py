"""
Enhanced Fixed Leverage Strategy with Smart Order Execution.
Addresses production-level execution issues with smart order management.
"""
from typing import Dict, Optional

from ib_insync import IB

from src.config.settings import Config
from src.core.types import PortfolioWeights, RebalanceRequest
from src.execution.smart_executor import SmartOrderExecutor
from src.strategy.fixed_leverage import FixedLeverageStrategy
from src.utils.logger import get_logger


class EnhancedFixedLeverageStrategy(FixedLeverageStrategy):
    """
    Enhanced Fixed Leverage Strategy with production-ready features:
    - Smart order execution with multiple order types
    - Margin safety checks before execution
    - Parallel order processing
    - Retry logic for partial fills
    - Position sizing based on available funds
    """
    
    def __init__(
        self,
        ib: IB,
        config: Config,
        portfolio_weights: Optional[PortfolioWeights] = None,
        target_leverage: float = 1.4
    ):
        # Initialize parent class
        super().__init__(ib, config, portfolio_weights, target_leverage)
        
        # Override executor with smart executor
        self.smart_executor = SmartOrderExecutor(
            ib=self.ib,
            portfolio_manager=self.portfolio_manager,
            config=self.config,
            contracts=self.contracts
        )
        
        self.logger = get_logger(__name__)
        self.logger.info("Enhanced Fixed Leverage Strategy initialized with Smart Executor")
    
    def rebalance(self, force: bool = False) -> bool:
        """
        Execute portfolio rebalancing with enhanced smart execution.
        
        Args:
            force: Force rebalancing even if not needed
            
        Returns:
            True if successful
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info("Starting Enhanced Fixed Leverage Rebalancing")
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
                return False
            
            # Check if rebalancing is needed
            if not force and not self.check_rebalance_needed():
                self.logger.info("No rebalancing needed")
                return True
            
            # Calculate target positions
            target_positions = self.calculate_target_positions()
            
            # Execute rebalance with smart executor
            rebalance_request = RebalanceRequest(
                target_positions=target_positions,
                target_leverage=self.target_leverage,
                reason="Enhanced manual rebalancing with smart execution",
                dry_run=self.config.dry_run
            )
            
            self.logger.info("Executing rebalance with Smart Order Executor")
            result = self.smart_executor.execute_rebalance(rebalance_request)
            
            if result.success:
                self.logger.info(
                    f"Enhanced rebalance completed successfully - "
                    f"Orders: {len(result.orders_placed)}, "
                    f"Commission: ${result.total_commission:.2f}, "
                    f"Time: {result.execution_time:.1f}s"
                )
                
                # Save portfolio snapshot
                self._save_portfolio_snapshot()
                
                # Log execution details
                self._log_execution_details(result)
                
            else:
                self.logger.error(
                    f"Enhanced rebalance failed - "
                    f"Failed orders: {len(result.orders_failed)}, "
                    f"Errors: {result.errors}"
                )
            
            return result.success
            
        except Exception as e:
            self.logger.error(f"Enhanced rebalancing failed: {e}", exc_info=True)
            return False
        finally:
            # Clear market data cache
            self.market_data.clear_cache()
            
            # Log final positions
            self._log_final_positions()
    
    def _log_execution_details(self, result):
        """Log detailed execution results."""
        try:
            self.logger.info("=" * 60)
            self.logger.info("ENHANCED EXECUTION DETAILS:")
            
            if result.orders_placed:
                self.logger.info(f"Successfully executed {len(result.orders_placed)} orders:")
                for trade in result.orders_placed:
                    self.logger.info(
                        f"  {trade.symbol}: {trade.action.value} {trade.quantity} @ ${trade.fill_price:.2f} "
                        f"(Status: {trade.status.value})"
                    )
            
            if result.orders_failed:
                self.logger.warning(f"Failed to execute {len(result.orders_failed)} orders:")
                for order in result.orders_failed:
                    self.logger.warning(f"  {order.symbol}: {order.action.value} {order.quantity}")
            
            if result.errors:
                self.logger.error("Execution errors:")
                for error in result.errors:
                    self.logger.error(f"  {error}")
            
            self.logger.info(f"Total execution time: {result.execution_time:.1f}s")
            self.logger.info(f"Total commission: ${result.total_commission:.2f}")
            self.logger.info("=" * 60)
            
        except Exception as e:
            self.logger.error(f"Failed to log execution details: {e}")


def create_enhanced_strategy(
    ib: IB,
    config: Config,
    portfolio_weights: Optional[PortfolioWeights] = None,
    target_leverage: float = 1.4
) -> EnhancedFixedLeverageStrategy:
    """
    Factory function to create enhanced strategy.
    
    Args:
        ib: IB connection
        config: Configuration
        portfolio_weights: Portfolio weights (optional)
        target_leverage: Target leverage (default 1.4)
        
    Returns:
        EnhancedFixedLeverageStrategy instance
    """
    return EnhancedFixedLeverageStrategy(
        ib=ib,
        config=config,
        portfolio_weights=portfolio_weights,
        target_leverage=target_leverage
    ) 
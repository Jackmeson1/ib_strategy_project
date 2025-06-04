"""
VIX-based dynamic leverage strategy.
"""
import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from ib_insync import IB, Stock

from src.config.portfolio import get_default_portfolio
from src.config.settings import Config
from src.core.exceptions import (
    ConfigurationError, EmergencyError, FatalError, MarketDataError
)
from src.core.types import (
    LeverageState, PortfolioWeights, RebalanceRequest, VIXData
)
from src.data.indicators import VIXIndicator
from src.data.market_data import MarketDataManager
from src.execution.executor import OrderExecutor
from src.portfolio.manager import PortfolioManager
from src.utils.logger import get_logger


@dataclass
class StrategyState:
    """Current state of the strategy."""
    vix_data: Optional[VIXData] = None
    leverage_state: Optional[LeverageState] = None
    last_rebalance_time: Optional[float] = None


class VIXLeverageStrategy:
    """
    Dynamic leverage strategy based on VIX levels.
    
    Adjusts portfolio leverage based on VIX moving average:
    - Low VIX (< 15): High leverage (2.0x)
    - Medium VIX (15-20): Moderate leverage (1.6x)
    - High VIX (20-25): Low leverage (1.2x)
    - Extreme VIX (> 25): Minimal leverage (0.8x)
    """
    
    def __init__(
        self,
        ib: IB,
        config: Config,
        portfolio_weights: Optional[PortfolioWeights] = None
    ):
        self.ib = ib
        self.config = config
        self.logger = get_logger(__name__)
        
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
        self.vix_indicator = VIXIndicator(
            ma_type=self.config.strategy.vix_ma_type,
            ma_window=self.config.strategy.vix_ma_window
        )
        
        # Strategy state
        self.state = StrategyState()
    
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
    
    def get_target_leverage(self, vix_level: float) -> float:
        """
        Calculate target leverage based on VIX level.
        
        Args:
            vix_level: Current VIX level
            
        Returns:
            Target leverage ratio
        """
        if vix_level < self.config.strategy.vix_threshold_low:
            return self.config.strategy.leverage_vix_low
        elif vix_level < self.config.strategy.vix_threshold_mid:
            return self.config.strategy.leverage_vix_mid
        elif vix_level < self.config.strategy.vix_threshold_high:
            return self.config.strategy.leverage_vix_high
        else:
            return self.config.strategy.leverage_vix_extreme
    
    def should_rebalance(self, current_leverage: float, target_leverage: float) -> bool:
        """
        Determine if rebalancing is needed.
        
        Args:
            current_leverage: Current portfolio leverage
            target_leverage: Target leverage
            
        Returns:
            True if rebalancing is needed
        """
        upper_bound = target_leverage + self.config.strategy.leverage_buffer
        lower_bound = target_leverage - self.config.strategy.leverage_buffer
        
        if current_leverage > upper_bound:
            self.logger.info(
                f"Rebalance needed: Current leverage {current_leverage:.2f} > upper bound {upper_bound:.2f}"
            )
            return True
        elif current_leverage < lower_bound:
            self.logger.info(
                f"Rebalance needed: Current leverage {current_leverage:.2f} < lower bound {lower_bound:.2f}"
            )
            return True
        
        return False
    
    def calculate_target_positions(self, target_leverage: float) -> Dict[str, int]:
        """
        Calculate target positions for given leverage.
        
        Args:
            target_leverage: Target leverage ratio
            
        Returns:
            Dictionary of symbol to target share count
        """
        try:
            # Get account value
            account = self.portfolio_manager.get_account_summary()
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
                target_value = nlv_usd * target_leverage * weight
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
    
    def run(self) -> bool:
        """
        Run the strategy once.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info("Starting VIX Leverage Strategy run")
            
            # Step 1: Get VIX data and calculate MA
            vix_df = self.market_data.get_vix_data(days=30)
            if vix_df is None:
                self.logger.warning("Unable to get VIX data - market may be closed")
                return False
            
            vix_data = self.vix_indicator.calculate_vix_ma(vix_df)
            if vix_data is None:
                self.logger.error("Failed to calculate VIX MA")
                return False
            
            self.state.vix_data = vix_data
            self.logger.info(
                f"VIX Analysis: Current={vix_data.close:.2f}, "
                f"{vix_data.ma_type.value}{vix_data.ma_window}={vix_data.ma_value:.2f}"
            )
            
            # Step 2: Determine target leverage
            target_leverage = self.get_target_leverage(vix_data.ma_value)
            self.logger.info(f"Target leverage based on VIX: {target_leverage:.2f}x")
            
            # Step 3: Check data integrity
            if not self.portfolio_manager.validate_data_integrity():
                self.logger.error("Data integrity check failed - aborting")
                return False
            
            # Step 4: Get current leverage
            current_leverage = self.portfolio_manager.get_portfolio_leverage()
            
            # Step 5: Check for emergency conditions
            if current_leverage > self.config.strategy.emergency_leverage_threshold:
                self.logger.critical(
                    f"EMERGENCY: Current leverage {current_leverage:.2f} exceeds "
                    f"threshold {self.config.strategy.emergency_leverage_threshold}"
                )
                result = self.portfolio_manager.emergency_liquidate_all()
                raise EmergencyError(
                    "Emergency liquidation triggered",
                    current_leverage,
                    self.config.strategy.emergency_leverage_threshold
                )
            
            # Step 6: Update leverage state
            self.state.leverage_state = LeverageState(
                current_leverage=current_leverage,
                target_leverage=target_leverage,
                vix_level=vix_data.close,
                vix_ma=vix_data.ma_value,
                requires_rebalance=self.should_rebalance(current_leverage, target_leverage),
                margin_safe=self.portfolio_manager.check_margin_safety()[0]
            )
            
            # Step 7: Check if rebalancing is needed
            if not self.state.leverage_state.requires_rebalance:
                self.logger.info("No rebalancing needed")
                return True
            
            # Step 8: Check margin safety
            if not self.state.leverage_state.margin_safe:
                self.logger.warning("Margin safety check failed - skipping rebalance")
                return False
            
            # Step 9: Calculate target positions
            target_positions = self.calculate_target_positions(target_leverage)
            
            # Step 10: Execute rebalance
            rebalance_request = RebalanceRequest(
                target_positions=target_positions,
                target_leverage=target_leverage,
                reason=f"VIX MA at {vix_data.ma_value:.2f}",
                dry_run=self.config.dry_run
            )
            
            result = self.executor.execute_rebalance(rebalance_request)
            
            if result.success:
                self.logger.info(
                    "Rebalance completed successfully",
                    orders_placed=len(result.orders_placed),
                    commission=f"${result.total_commission:.2f}",
                    execution_time=f"{result.execution_time:.1f}s"
                )
            else:
                self.logger.error(
                    "Rebalance failed",
                    orders_failed=len(result.orders_failed),
                    errors=result.errors
                )
            
            return result.success
            
        except EmergencyError:
            # Emergency already handled
            return False
        except Exception as e:
            self.logger.error(f"Strategy execution failed: {e}", exc_info=True)
            return False
        finally:
            # Clear market data cache
            self.market_data.clear_cache()
            
            # Log final positions
            try:
                positions = self.portfolio_manager.get_positions()
                self.logger.info("=" * 60)
                self.logger.info("Final Portfolio Positions:")
                for symbol, position in positions.items():
                    self.logger.info(
                        f"  {symbol}: {position.quantity:,.0f} shares @ ${position.avg_cost:.2f}"
                    )
                self.logger.info("=" * 60)
            except Exception as e:
                self.logger.error(f"Failed to log final positions: {e}") 
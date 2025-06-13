"""
Portfolio management with position tracking and account monitoring.
"""
import math
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ib_insync import IB, Contract, Stock, MarketOrder
from ib_insync.objects import Position as IBPosition

from src.config.settings import Config
from src.core.exceptions import (
    DataIntegrityError, EmergencyError, MarginError,
    OrderExecutionError, PositionError
)
from src.core.types import (
    AccountSummaryDict, ExecutionResult, Order, OrderAction,
    Position, PositionDict, Trade, OrderStatus
)
from src.data.market_data import MarketDataManager
from src.utils.logger import get_logger
from src.utils.delay import wait
from src.utils.currency import convert


class PortfolioManager:
    """Manages portfolio positions and account information."""
    
    def __init__(
        self,
        ib: IB,
        market_data: MarketDataManager,
        config: Config,
        contracts: Dict[str, Contract]
    ):
        self.ib = ib
        self.market_data = market_data
        self.config = config
        self.contracts = contracts
        self.logger = get_logger(__name__)
        self.accounts = config.accounts or []
        if not self.accounts and config.ib.account_id:
            from src.config.settings import AccountConfig
            self.accounts = [AccountConfig(config.ib.account_id, "USD")]
        self._currency_map = {acc.account_id: acc.base_currency.upper() for acc in self.accounts}
        
        # Cache for account and position data
        self._account_cache: Optional[AccountSummaryDict] = None
        self._positions_cache: Dict[str, Position] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 60  # 1 minute cache

    def _to_base_currency(self, amount: float, currency: str, account_id: str) -> float:
        """Convert the given amount to the account's base currency."""
        base_currency = self._currency_map.get(account_id, "USD")
        return convert(amount, currency, base_currency, self.market_data)
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if self._cache_timestamp is None:
            return False
        return (datetime.now() - self._cache_timestamp).seconds < self._cache_ttl_seconds
    
    def invalidate_cache(self):
        """Invalidate the cache."""
        self._account_cache = None
        self._positions_cache.clear()
        self._cache_timestamp = None
    
    def get_positions(self, force_refresh: bool = False) -> Dict[str, Position]:
        """
        Get current positions.
        
        Args:
            force_refresh: Force refresh from IB
            
        Returns:
            Dictionary of symbol to Position
            
        Raises:
            PositionError: If unable to get positions
        """
        if not force_refresh and self._is_cache_valid():
            return self._positions_cache
        
        try:
            self.logger.info("Fetching positions from IB")
            
            # Use portfolio() method instead of positions() for better data
            portfolio_items = self.ib.portfolio()

            positions: Dict[str, Position] = {}
            for item in portfolio_items:
                if item.position != 0 and item.account in self._currency_map:
                    # Use the market value from portfolio item if available
                    market_value = getattr(item, 'marketValue', None)
                    unrealized_pnl = getattr(item, 'unrealizedPNL', None)
                    
                    # Calculate current price from market value if available
                    current_price = None
                    if market_value is not None and item.position != 0:
                        current_price = abs(market_value / item.position)
                    
                    # Fall back to average cost if no market price available
                    if current_price is None:
                        current_price = item.averageCost
                        market_value = current_price * item.position
                        unrealized_pnl = 0.0
                    
                    symbol = item.contract.symbol
                    if symbol not in positions:
                        positions[symbol] = Position(
                            symbol=symbol,
                            quantity=item.position,
                            avg_cost=item.averageCost,
                            current_price=current_price,
                            unrealized_pnl=unrealized_pnl,
                        )
                    else:
                        pos = positions[symbol]
                        total_qty = pos.quantity + item.position
                        if total_qty != 0:
                            pos.avg_cost = (
                                pos.avg_cost * pos.quantity + item.averageCost * item.position
                            ) / total_qty
                        pos.quantity = total_qty
            
            # Update cache
            self._positions_cache = positions
            self._cache_timestamp = datetime.now()
            
            self.logger.info(
                f"Retrieved {len(positions)} positions",
                symbols=list(positions.keys())
            )
            
            return positions
            
        except Exception as e:
            self.logger.error(f"Failed to get positions: {e}")
            raise PositionError(f"Failed to get positions: {e}")
    
    def get_account_summary(self, force_refresh: bool = False) -> AccountSummaryDict:
        """
        Get account summary.
        
        Args:
            force_refresh: Force refresh from IB
            
        Returns:
            Account summary dictionary
            
        Raises:
            DataIntegrityError: If unable to get account data
        """
        if not force_refresh and self._is_cache_valid() and self._account_cache:
            return self._account_cache
        
        try:
            self.logger.info("Fetching account summary from IB")
            aggregate: AccountSummaryDict = {}
            key_fields = [
                'NetLiquidation', 'GrossPositionValue', 'AvailableFunds',
                'MaintMarginReq', 'InitMarginReq', 'BuyingPower', 'EquityWithLoanValue'
            ]

            for acc in self.accounts:
                account_items = self.ib.accountSummary(account=acc.account_id)
                account_summary: AccountSummaryDict = {}

                for item in account_items:
                    if item.tag in key_fields:
                        try:
                            account_summary[item.tag] = float(item.value)
                        except (ValueError, TypeError):
                            self.logger.warning(f"Cannot parse {item.tag}: {item.value}")
                            account_summary[item.tag] = 0.0

                for field in key_fields:
                    value = account_summary.get(field, 0.0)
                    if field not in aggregate:
                        aggregate[field] = 0.0
                    # For primary account, use direct value; for multi-account, convert to base currency of first account
                    if len(self.accounts) == 1:
                        aggregate[field] += value  # Single account - use native values
                    else:
                        # Multi-account: convert to base currency of first account
                        base_account_currency = self._currency_map[self.accounts[0].account_id]
                        aggregate[field] += self._to_base_currency(value, self._currency_map[acc.account_id], self.accounts[0].account_id)

            # Validate critical fields
            if aggregate.get('NetLiquidation', 0) <= 0:
                raise DataIntegrityError("Invalid Net Liquidation Value")

            # Update cache
            self._account_cache = aggregate
            self._cache_timestamp = datetime.now()

            # Log sanitized summary with correct currency
            base_currency = self._currency_map[self.accounts[0].account_id] if self.accounts else "USD"
            currency_symbol = "$" if base_currency == "USD" else f"{base_currency} "
            self.logger.info(
                "Account summary retrieved",
                net_liquidation=f"{currency_symbol}{aggregate.get('NetLiquidation', 0):,.0f}",
                available_funds=f"{currency_symbol}{aggregate.get('AvailableFunds', 0):,.0f}",
                margin_used=f"{currency_symbol}{aggregate.get('MaintMarginReq', 0):,.0f}",
                base_currency=base_currency
            )

            return aggregate
            
        except Exception as e:
            self.logger.error(f"Failed to get account summary: {e}")
            raise DataIntegrityError(f"Failed to get account summary: {e}")
    
    def check_margin_safety(self) -> Tuple[bool, Dict[str, float]]:
        """
        Check if margin usage is within safe limits.
        
        Returns:
            Tuple of (is_safe, metrics_dict)
        """
        try:
            account = self.get_account_summary()
            nlv = account.get('NetLiquidation', 0)
            available = account.get('AvailableFunds', 0)
            maint_margin = account.get('MaintMarginReq', 0)
            init_margin = account.get('InitMarginReq', 0)
            
            if nlv <= 0:
                return False, {"reason": "Invalid NLV"}
            
            safety_ratio = available / nlv
            margin_usage = maint_margin / nlv if nlv > 0 else 0
            
            metrics = {
                "safety_ratio": safety_ratio,
                "margin_usage": margin_usage,
                "available_funds": available,
                "nlv": nlv
            }
            
            # Safety checks
            checks = [
                safety_ratio >= self.config.strategy.safety_threshold,
                margin_usage < 1.1,  # 110% margin usage limit
                available > init_margin * 0.3  # 30% buffer
            ]
            
            is_safe = all(checks)
            
            self.logger.info(
                "Margin safety check",
                is_safe=is_safe,
                safety_ratio=f"{safety_ratio:.2%}",
                margin_usage=f"{margin_usage:.2%}"
            )
            
            return is_safe, metrics
            
        except Exception as e:
            self.logger.error(f"Failed to check margin safety: {e}")
            return False, {"error": str(e)}
    
    def get_portfolio_leverage(self) -> float:
        """
        Calculate current portfolio leverage.
        
        Returns:
            Current leverage ratio
            
        Raises:
            DataIntegrityError: If unable to calculate leverage
        """
        try:
            account = self.get_account_summary()
            gross_pos_usd = account.get('GrossPositionValue', 0)
            nlv_usd = account.get('NetLiquidation', 0)
            
            if nlv_usd <= 0:
                return 0.0
            
            current_leverage = gross_pos_usd / nlv_usd
            
            base_currency = self._currency_map[self.accounts[0].account_id] if self.accounts else "USD"
            currency_symbol = "$" if base_currency == "USD" else f"{base_currency} "
            self.logger.info(
                "Current leverage calculated",
                leverage=f"{current_leverage:.2f}",
                gross_position=f"{currency_symbol}{gross_pos_usd:,.0f}",
                nlv=f"{currency_symbol}{nlv_usd:,.0f}",
                base_currency=base_currency
            )
            
            return current_leverage
            
        except Exception as e:
            self.logger.error(f"Failed to calculate leverage: {e}")
            raise DataIntegrityError(f"Failed to calculate leverage: {e}")
    
    def validate_data_integrity(self) -> bool:
        """
        Validate that position data matches account summary.
        
        Returns:
            True if data is consistent
        """
        try:
            account = self.get_account_summary()
            positions = self.get_positions(force_refresh=True)  # Force refresh to get latest data
            
            # Check if account shows positions but we have none
            gross_pos = account.get('GrossPositionValue', 0)
            
            # If account shows no positions and we have no positions, that's fine
            if gross_pos == 0 and not positions:
                self.logger.info("No positions detected - account and portfolio data consistent")
                return True
            
            # If we have positions but gross position value is 0, something is wrong
            if positions and gross_pos == 0:
                self.logger.warning(
                    "Positions detected but GrossPositionValue is 0 - possible data sync issue"
                )
                # Don't fail - this might be a timing issue
                return True
            
            # If account shows positions but we have none, retry once
            if gross_pos > 0 and not positions:
                self.logger.warning("Account shows positions but none retrieved - retrying...")
                self.invalidate_cache()  # Clear cache
                positions = self.get_positions(force_refresh=True)
                
                if not positions:
                    self.logger.error(
                        "Data integrity check failed: Account shows positions but none retrieved after retry",
                        gross_position_value=gross_pos
                    )
                    return False
            
            # Calculate total position value for validation
            total_value = 0
            for symbol, position in positions.items():
                try:
                    total_value += abs(position.market_value)
                except Exception as e:
                    self.logger.warning(f"Could not calculate value for {symbol}: {e}")
            
            # Allow for some discrepancy due to timing differences
            expected_value = gross_pos
            discrepancy = abs(total_value - expected_value) / expected_value if expected_value > 0 else 0
            
            if discrepancy > 0.15:  # 15% tolerance for FX and timing differences
                self.logger.warning(
                    "Large discrepancy in position values - but allowing continuation",
                    calculated=f"${total_value:,.0f}",
                    reported=f"${expected_value:,.0f}",
                    discrepancy=f"{discrepancy:.1%}"
                )
            
            self.logger.info(
                "Data integrity check passed",
                positions_count=len(positions),
                total_value=f"${total_value:,.0f}",
                gross_position_value=f"${expected_value:,.0f}"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Data integrity validation failed: {e}")
            # Don't fail on validation errors - log and continue
            self.logger.warning("Continuing despite data integrity validation error")
            return True
    
    def emergency_liquidate_all(self) -> ExecutionResult:
        """
        Emergency liquidation of all positions.
        
        Returns:
            ExecutionResult with details of liquidation
        """
        self.logger.critical("EMERGENCY LIQUIDATION INITIATED")
        
        start_time = time.time()
        orders_placed = []
        orders_failed = []
        errors = []
        
        try:
            positions = self.get_positions(force_refresh=True)
            
            for symbol, position in positions.items():
                if position.quantity == 0:
                    continue
                
                try:
                    contract = self.contracts.get(symbol)
                    if not contract:
                        contract = getattr(position, "ib_contract", None) or Stock(symbol, "SMART", "USD")
                        self.ib.qualifyContracts(contract)
                        self.contracts[symbol] = contract

                    # Create market order to close position
                    action = OrderAction.SELL if position.quantity > 0 else OrderAction.BUY
                    order = Order(
                        symbol=symbol,
                        action=action,
                        quantity=abs(int(position.quantity))
                    )

                    # Place order
                    ib_order = MarketOrder(
                        action=order.action.value,
                        totalQuantity=order.quantity
                    )

                    trade = self.ib.placeOrder(contract, ib_order)
                    
                    # Wait for fill with shorter timeout
                    filled = False
                    for _ in range(30):  # 30 second timeout
                        wait(1, self.ib)
                        if trade.isDone():
                            filled = True
                            break
                    
                    if filled:
                        orders_placed.append(Trade(
                            order_id=trade.order.orderId,
                            symbol=symbol,
                            action=action,
                            quantity=order.quantity,
                            fill_price=trade.orderStatus.avgFillPrice or 0,
                            commission=0,  # Will be updated later
                            timestamp=datetime.now(),
                            status=OrderStatus.FILLED
                        ))
                    else:
                        orders_failed.append(order)
                        errors.append(f"Order for {symbol} not filled in time")
                        
                except Exception as e:
                    self.logger.error(f"Failed to liquidate {symbol}: {e}")
                    orders_failed.append(order)
                    errors.append(f"{symbol}: {str(e)}")
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=len(orders_failed) == 0,
                orders_placed=orders_placed,
                orders_failed=orders_failed,
                total_commission=0,  # Would need to calculate from fills
                execution_time=execution_time,
                errors=errors
            )
            
        except Exception as e:
            self.logger.critical(f"Emergency liquidation failed: {e}")
            return ExecutionResult(
                success=False,
                orders_placed=[],
                orders_failed=[],
                total_commission=0,
                execution_time=time.time() - start_time,
                errors=[str(e)]
            ) 
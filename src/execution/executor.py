"""
Order execution with batch processing, retries, and partial fill handling.
"""
import random
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ib_insync import IB, Contract, MarketOrder, LimitOrder, Trade as IBTrade

from src.config.settings import Config
from src.core.exceptions import (
    EmergencyError, OrderExecutionError, RetryableError
)
from src.core.types import (
    ExecutionResult, Order, OrderAction, OrderStatus,
    RebalanceRequest, Trade
)
from src.portfolio.manager import PortfolioManager
from src.utils.logger import get_logger
from src.utils.delay import wait


class OrderExecutor:
    """Handles order execution with safety checks and batch processing."""
    
    def __init__(
        self,
        ib: IB,
        portfolio_manager: PortfolioManager,
        config: Config,
        contracts: Dict[str, Contract]
    ):
        self.ib = ib
        self.portfolio_manager = portfolio_manager
        self.config = config
        self.contracts = contracts
        self.logger = get_logger(__name__)
        
        # Execution parameters
        self.max_order_timeout = 300  # 5 minutes
        self.batch_size = 5
        self.batch_delay = 2  # seconds between batches
        self.max_retries = 3
    
    def execute_rebalance(self, request: RebalanceRequest) -> ExecutionResult:
        """
        Execute portfolio rebalance with three-batch random grouping.
        
        Args:
            request: Rebalance request with target positions
            
        Returns:
            ExecutionResult with execution details
            
        Raises:
            EmergencyError: If emergency leverage threshold exceeded
        """
        start_time = time.time()
        self.logger.info(
            "Starting rebalance execution",
            target_leverage=request.target_leverage,
            reason=request.reason,
            dry_run=request.dry_run
        )
        
        # Check initial leverage
        initial_leverage = self.portfolio_manager.get_portfolio_leverage()
        if initial_leverage > self.config.strategy.emergency_leverage_threshold:
            raise EmergencyError(
                "Initial leverage exceeds emergency threshold",
                initial_leverage,
                self.config.strategy.emergency_leverage_threshold
            )
        
        # Validate data integrity
        if not self.portfolio_manager.validate_data_integrity():
            self.logger.error("Data integrity check failed, aborting rebalance")
            return ExecutionResult(
                success=False,
                orders_placed=[],
                orders_failed=[],
                total_commission=0,
                execution_time=time.time() - start_time,
                errors=["Data integrity validation failed"]
            )
        
        # Calculate required orders
        orders = self._calculate_orders(request.target_positions)
        if not orders:
            self.logger.info("No orders needed for rebalance")
            return ExecutionResult(
                success=True,
                orders_placed=[],
                orders_failed=[],
                total_commission=0,
                execution_time=time.time() - start_time,
                errors=[]
            )
        
        # Execute in three random batches
        if request.dry_run:
            self.logger.info("DRY RUN: Would execute orders", orders=len(orders))
            return ExecutionResult(
                success=True,
                orders_placed=[],
                orders_failed=[],
                total_commission=0,
                execution_time=time.time() - start_time,
                errors=[]
            )
        
        return self._execute_three_batch_rebalance(
            orders,
            initial_leverage,
            request.target_leverage
        )
    
    def _calculate_orders(self, target_positions: Dict[str, int]) -> List[Order]:
        """Calculate orders needed to reach target positions."""
        orders = []
        current_positions = self.portfolio_manager.get_positions()
        
        for symbol, target_qty in target_positions.items():
            current_qty = current_positions.get(symbol, 0).quantity if symbol in current_positions else 0
            diff = target_qty - current_qty
            
            if abs(diff) < 1:  # Skip negligible differences
                continue
            
            action = OrderAction.BUY if diff > 0 else OrderAction.SELL
            order = Order(
                symbol=symbol,
                action=action,
                quantity=abs(int(diff))
            )
            orders.append(order)
            
            self.logger.debug(
                f"Order calculated for {symbol}",
                current=current_qty,
                target=target_qty,
                action=action.value,
                quantity=order.quantity
            )
        
        return orders
    
    def _execute_three_batch_rebalance(
        self,
        orders: List[Order],
        initial_leverage: float,
        target_leverage: float
    ) -> ExecutionResult:
        """Execute orders in three random batches with leverage monitoring."""
        start_time = time.time()
        all_trades = []
        all_failed = []
        all_errors = []
        total_commission = 0
        
        # Randomly shuffle and split into 3 batches
        random.shuffle(orders)
        batch_size = len(orders) // 3 + 1
        batches = [
            orders[i:i + batch_size]
            for i in range(0, len(orders), batch_size)
        ][:3]  # Ensure max 3 batches
        
        for batch_idx, batch in enumerate(batches):
            self.logger.info(f"Executing batch {batch_idx + 1}/{len(batches)} with {len(batch)} orders")
            
            # Execute batch
            batch_result = self._execute_batch(batch)
            all_trades.extend(batch_result.orders_placed)
            all_failed.extend(batch_result.orders_failed)
            all_errors.extend(batch_result.errors)
            total_commission += batch_result.total_commission
            
            # Wait between batches
            if batch_idx < len(batches) - 1:
                wait(self.batch_delay, self.ib)
            
            # Check leverage after each batch
            try:
                current_leverage = self.portfolio_manager.get_portfolio_leverage()
                self.logger.info(
                    f"Leverage after batch {batch_idx + 1}",
                    current=f"{current_leverage:.2f}",
                    initial=f"{initial_leverage:.2f}",
                    target=f"{target_leverage:.2f}"
                )
                
                # Emergency check
                if current_leverage > self.config.strategy.emergency_leverage_threshold:
                    self.logger.critical(
                        "EMERGENCY: Leverage exceeded threshold after batch",
                        current_leverage=current_leverage,
                        threshold=self.config.strategy.emergency_leverage_threshold
                    )
                    # Trigger emergency liquidation
                    emergency_result = self.portfolio_manager.emergency_liquidate_all()
                    all_errors.append(f"Emergency liquidation triggered at leverage {current_leverage:.2f}")
                    return ExecutionResult(
                        success=False,
                        orders_placed=all_trades,
                        orders_failed=all_failed + emergency_result.orders_failed,
                        total_commission=total_commission,
                        execution_time=time.time() - start_time,
                        errors=all_errors + emergency_result.errors
                    )
                
                # Verify leverage is moving in the right direction
                if not (min(initial_leverage, target_leverage) <= current_leverage <= max(initial_leverage, target_leverage)):
                    self.logger.warning(
                        "Leverage outside expected range",
                        current=current_leverage,
                        expected_range=f"[{min(initial_leverage, target_leverage):.2f}, {max(initial_leverage, target_leverage):.2f}]"
                    )
                    
            except Exception as e:
                self.logger.error(f"Failed to check leverage after batch: {e}")
                all_errors.append(f"Leverage check failed: {str(e)}")
        
        execution_time = time.time() - start_time
        success = len(all_failed) == 0 and len(all_errors) == 0
        
        return ExecutionResult(
            success=success,
            orders_placed=all_trades,
            orders_failed=all_failed,
            total_commission=total_commission,
            execution_time=execution_time,
            errors=all_errors
        )
    
    def _execute_batch(self, orders: List[Order]) -> ExecutionResult:
        """Execute a batch of orders."""
        start_time = time.time()
        trades = []
        failed = []
        errors = []
        commission = 0
        
        for order in orders:
            for attempt in range(self.max_retries):
                try:
                    trade = self._execute_single_order(order)
                    if trade:
                        trades.append(trade)
                        commission += trade.commission
                        break
                except RetryableError as e:
                    if attempt < self.max_retries - 1:
                        self.logger.warning(
                            f"Retryable error for {order.symbol}, attempt {attempt + 1}/{self.max_retries}",
                            error=str(e)
                        )
                        wait(2 ** attempt, self.ib)  # Exponential backoff
                    else:
                        failed.append(order)
                        errors.append(f"{order.symbol}: {str(e)}")
                except Exception as e:
                    self.logger.error(f"Failed to execute order for {order.symbol}: {e}")
                    failed.append(order)
                    errors.append(f"{order.symbol}: {str(e)}")
                    break
        
        return ExecutionResult(
            success=len(failed) == 0,
            orders_placed=trades,
            orders_failed=failed,
            total_commission=commission,
            execution_time=time.time() - start_time,
            errors=errors
        )
    
    def _execute_single_order(self, order: Order) -> Optional[Trade]:
        """Execute a single order."""
        if order.symbol not in self.contracts:
            raise OrderExecutionError(f"No contract found for {order.symbol}")
        
        contract = self.contracts[order.symbol]
        
        # Create IB order
        ib_order = MarketOrder(
            action=order.action.value,
            totalQuantity=order.quantity
        )
        
        # Place order
        ib_trade = self.ib.placeOrder(contract, ib_order)
        
        # Wait for execution
        timeout = min(self.max_order_timeout, 60)  # Max 60s per order
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            wait(0.5, self.ib)
            
            if ib_trade.isDone():
                # Order completed
                if ib_trade.orderStatus.status == "Filled":
                    return self._create_trade_from_ib(order, ib_trade)
                elif ib_trade.orderStatus.status == "Cancelled":
                    raise OrderExecutionError(f"Order cancelled: {ib_trade.orderStatus.status}")
                else:
                    raise OrderExecutionError(f"Order failed: {ib_trade.orderStatus.status}")
            
            # Check for partial fills
            if ib_trade.orderStatus.filled > 0:
                self.logger.info(
                    f"Partial fill for {order.symbol}",
                    filled=ib_trade.orderStatus.filled,
                    remaining=ib_trade.orderStatus.remaining
                )
        
        # Timeout - check if partially filled
        if ib_trade.orderStatus.filled > 0:
            self.logger.warning(f"Order for {order.symbol} partially filled on timeout")
            return self._create_trade_from_ib(order, ib_trade)
        else:
            # Cancel the order
            self.ib.cancelOrder(ib_trade.order)
            raise RetryableError(f"Order timeout for {order.symbol}")
    
    def _create_trade_from_ib(self, order: Order, ib_trade: IBTrade) -> Trade:
        """Create Trade object from IB trade."""
        return Trade(
            order_id=ib_trade.order.orderId,
            symbol=order.symbol,
            action=order.action,
            quantity=ib_trade.orderStatus.filled,
            fill_price=ib_trade.orderStatus.avgFillPrice or 0,
            commission=sum(fill.commissionReport.commission for fill in ib_trade.fills) if ib_trade.fills else 0,
            timestamp=datetime.now(),
            status=OrderStatus(ib_trade.orderStatus.status)
        ) 
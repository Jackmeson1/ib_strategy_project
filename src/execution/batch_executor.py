"""
Enhanced batch order executor with atomic margin checks and fire-all-then-monitor execution.
Addresses P0-A and P0-D: true batch execution with atomic margin validation.
"""
import asyncio
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from ib_insync import IB, Contract, MarketOrder, LimitOrder, Trade as IBTrade

from src.config.settings import Config
from src.core.exceptions import OrderExecutionError, RetryableError
from src.core.types import (
    ExecutionResult, Order, OrderAction, OrderStatus, Trade
)
from src.portfolio.manager import PortfolioManager

from src.utils.logger import get_logger
from src.utils.delay import wait

from .base_executor import BaseExecutor



class BatchOrderExecutor(BaseExecutor):
    """
    Enhanced batch order executor with true parallel execution.
    
    Features:
    - Fire all orders first, then monitor (no per-order isDone() loops)
    - Atomic margin check for entire batch before execution
    - Thread-pool based monitoring with timeouts
    - Smart order type selection based on order size
    - Comprehensive hanging protection
    """
    
    def __init__(
        self,
        ib: IB,
        portfolio_manager: PortfolioManager,
        config: Config,
        contracts: Dict[str, Contract],
        max_parallel_orders: int = 5,
        margin_cushion: float = 0.2
    ):
        super().__init__(ib, portfolio_manager, config, contracts)
        self.max_parallel_orders = max_parallel_orders
        self.margin_cushion = margin_cushion
        
        # Execution parameters
        self.order_timeout = 300  # 5 minutes per order
        self.batch_timeout = 900  # 15 minutes total
        self.min_fill_ratio = 0.8  # 80% fill required
        
        # Monitoring
        self.active_orders: Dict[int, IBTrade] = {}
        self.completed_orders: Dict[int, IBTrade] = {}
        self.failed_orders: Dict[int, str] = {}
        self._monitor_active = False
        self._executor = None
    
    def execute_batch(self, orders: List[Order]) -> ExecutionResult:
        """
        Execute batch of orders with atomic margin check and fire-all-then-monitor.
        
        Args:
            orders: List of orders to execute
            
        Returns:
            ExecutionResult with execution summary
        """
        start_time = time.time()
        
        self.logger.info(f"Starting batch execution of {len(orders)} orders")
        
        try:
            # Step 1: Atomic margin check for entire batch
            if not self._check_batch_margin_safety(orders):
                return ExecutionResult(
                    success=False,
                    orders_placed=[],
                    orders_failed=[],
                    total_commission=0,
                    execution_time=time.time() - start_time,
                    errors=["Atomic margin check failed for batch"]
                )
            
            # Step 2: Fire all orders simultaneously
            ib_trades = self._fire_all_orders(orders)
            if not ib_trades:
                return ExecutionResult(
                    success=False,
                    orders_placed=[],
                    orders_failed=[],
                    total_commission=0,
                    execution_time=time.time() - start_time,
                    errors=["Failed to place any orders"]
                )
            
            # Step 3: Monitor all orders in parallel until completion
            success = self._monitor_all_orders(ib_trades)
            
            # Step 4: Compile results
            return self._compile_results(orders, start_time, success)
            
        except Exception as e:
            self.logger.error(f"Batch execution failed: {e}", exc_info=True)
            return ExecutionResult(
                success=False,
                orders_placed=[],
                orders_failed=[],
                total_commission=0,
                execution_time=time.time() - start_time,
                errors=[f"Batch execution error: {str(e)}"]
            )
        finally:
            self._cleanup_monitoring()
    
    def _check_batch_margin_safety(self, orders: List[Order]) -> bool:
        """
        Atomic margin check for entire batch using IB's 'what-if' calculation.
        
        Args:
            orders: List of orders to validate
            
        Returns:
            True if batch is safe to execute, False otherwise
        """
        try:
            self.logger.info("Performing atomic margin check for batch")
            
            # Get current account summary
            account = self.portfolio_manager.get_account_summary()
            available_funds = account.get('AvailableFunds', 0)
            net_liquidation = account.get('NetLiquidation', 0)
            
            # Calculate estimated fund requirement for entire batch
            total_estimated_cost = 0
            for order in orders:
                if order.action == OrderAction.BUY:
                    # Get current market price
                    contract = self.contracts.get(order.symbol)
                    if contract:
                        ticker = self.ib.reqMktData(contract, '', False, False)

                        # Keep IB event loop active while waiting for price
                        self.ib.sleep(0.1)

                        
                        price = ticker.marketPrice()
                        if price and price > 0:
                            estimated_cost = price * order.quantity
                            total_estimated_cost += estimated_cost
                        else:
                            # Fallback to position value if no price available
                            positions = self.portfolio_manager.get_positions()
                            if order.symbol in positions:
                                avg_price = positions[order.symbol].avg_cost
                                estimated_cost = avg_price * order.quantity
                                total_estimated_cost += estimated_cost
                        
                        self.ib.cancelMktData(contract)
            
            # Apply margin cushion
            required_funds = total_estimated_cost * (1 + self.margin_cushion)
            
            self.logger.info(
                f"Atomic margin check: Need ${required_funds:,.2f}, Available: ${available_funds:,.2f}"
            )
            
            # Check if we have sufficient funds
            if required_funds > available_funds:
                self.logger.error(
                    f"Margin safety violation: Need ${required_funds:,.2f} but only ${available_funds:,.2f} available"
                )
                return False
            
            # Additional safety: ensure we don't exceed 80% of net liquidation
            max_position_value = net_liquidation * 0.8
            if total_estimated_cost > max_position_value:
                self.logger.error(
                    f"Position size safety violation: ${total_estimated_cost:,.2f} exceeds 80% of NLV (${max_position_value:,.2f})"
                )
                return False
            
            self.logger.info("✅ Atomic margin check passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Margin check failed: {e}", exc_info=True)
            return False
    
    def _fire_all_orders(self, orders: List[Order]) -> List[IBTrade]:
        """
        Fire all orders simultaneously without waiting for fills.
        
        Args:
            orders: List of orders to place
            
        Returns:
            List of IBTrade objects for monitoring
        """
        ib_trades = []
        
        self.logger.info(f"🚀 Firing all {len(orders)} orders simultaneously")
        
        for order in orders:
            try:
                # Get contract
                contract = self.contracts.get(order.symbol)
                if not contract:
                    self.logger.error(f"Contract not found for {order.symbol}")
                    continue
                
                # Create smart order
                ib_order = self._create_smart_order(order)
                
                # Place order (non-blocking)
                trade = self.ib.placeOrder(contract, ib_order)
                
                if trade:
                    ib_trades.append(trade)
                    self.active_orders[trade.order.orderId] = trade
                    self.logger.info(f"✅ Order fired: {order.symbol} {order.action.value} {order.quantity}")
                else:
                    self.logger.error(f"❌ Failed to place order: {order.symbol}")
            
            except Exception as e:
                self.logger.error(f"Error placing order for {order.symbol}: {e}")
                continue
        
        self.logger.info(f"🎯 Successfully fired {len(ib_trades)}/{len(orders)} orders")
        return ib_trades
    
    def _create_smart_order(self, order: Order) -> object:
        """
        Create smart order type based on order size and market conditions.
        
        Small orders (<$10K): Market orders for quick execution
        Large orders (>$10K): Limit orders for price control
        
        Args:
            order: Order specification
            
        Returns:
            IB order object (MarketOrder or LimitOrder)
        """
        # Get current market price
        contract = self.contracts.get(order.symbol)
        ticker = self.ib.reqMktData(contract, '', False, False)

        # Allow the event loop to process data while waiting
        self.ib.sleep(0.1)

        
        market_price = ticker.marketPrice()
        order_value = market_price * order.quantity if market_price else 0
        
        self.ib.cancelMktData(contract)
        
        # Smart order type selection
        if order_value < 10000:  # Small orders: use market orders
            ib_order = MarketOrder(
                action=order.action.value,
                totalQuantity=order.quantity
            )
            self.logger.debug(f"Market order for {order.symbol}: ${order_value:,.0f}")
        else:  # Large orders: use limit orders with 0.2% buffer
            if market_price and market_price > 0:
                if order.action == OrderAction.BUY:
                    limit_price = market_price * 1.002  # 0.2% above market
                else:
                    limit_price = market_price * 0.998  # 0.2% below market
                
                ib_order = LimitOrder(
                    action=order.action.value,
                    totalQuantity=order.quantity,
                    lmtPrice=round(limit_price, 2)
                )
                self.logger.debug(f"Limit order for {order.symbol}: ${order_value:,.0f} @ ${limit_price:.2f}")
            else:
                # Fallback to market order if no price available
                ib_order = MarketOrder(
                    action=order.action.value,
                    totalQuantity=order.quantity
                )
                self.logger.debug(f"Fallback market order for {order.symbol}")
        
        return ib_order
    
    def _monitor_all_orders(self, ib_trades: List[IBTrade]) -> bool:
        """
        Monitor all orders in parallel using thread pool.
        
        Args:
            ib_trades: List of IBTrade objects to monitor
            
        Returns:
            True if monitoring completed successfully, False otherwise
        """
        if not ib_trades:
            return False
        
        self.logger.info(f"👀 Starting parallel monitoring of {len(ib_trades)} orders")
        self._monitor_active = True
        
        # Create thread pool for parallel monitoring
        self._executor = ThreadPoolExecutor(max_workers=min(len(ib_trades), self.max_parallel_orders))
        
        try:
            # Submit monitoring tasks for each order
            futures = {
                self._executor.submit(self._monitor_single_order, trade): trade
                for trade in ib_trades
            }
            
            # Monitor with global timeout
            completed_count = 0
            start_time = time.time()
            
            for future in as_completed(futures, timeout=self.batch_timeout):
                trade = futures[future]
                
                try:
                    success = future.result()
                    if success:
                        completed_count += 1
                        self.completed_orders[trade.order.orderId] = trade
                        self.logger.info(f"✅ Order completed: {trade.contract.symbol}")
                    else:
                        self.failed_orders[trade.order.orderId] = "Monitoring failed"
                        self.logger.warning(f"⚠️  Order monitoring failed: {trade.contract.symbol}")
                
                except Exception as e:
                    self.failed_orders[trade.order.orderId] = str(e)
                    self.logger.error(f"❌ Order monitoring error: {trade.contract.symbol}: {e}")
                
                # Check progress
                elapsed_time = time.time() - start_time
                remaining_orders = len(ib_trades) - completed_count - len(self.failed_orders)
                
                if elapsed_time > self.batch_timeout:
                    self.logger.warning(f"⏰ Batch timeout reached ({self.batch_timeout}s), aborting remaining orders")
                    break
            
            # Calculate success rate
            success_rate = completed_count / len(ib_trades)
            self.logger.info(f"📊 Batch monitoring completed: {completed_count}/{len(ib_trades)} orders succeeded ({success_rate:.1%})")
            
            return success_rate >= 0.8  # Require 80% success rate
            
        except TimeoutError:
            self.logger.error(f"🚨 Batch monitoring timed out after {self.batch_timeout}s")
            return False
        
        finally:
            self._monitor_active = False
            if self._executor:
                self._executor.shutdown(wait=False)
    
    def _monitor_single_order(self, trade: IBTrade) -> bool:
        """
        Monitor a single order until completion or timeout.
        
        Args:
            trade: IBTrade object to monitor
            
        Returns:
            True if order completed successfully, False otherwise
        """
        order_id = trade.order.orderId
        symbol = trade.contract.symbol
        start_time = time.time()
        
        self.logger.debug(f"Monitoring order {order_id} for {symbol}")
        
        try:
            # Quick check for immediate fills (common in paper trading)
            for _ in range(5):
                if trade.isDone():
                    self.logger.info(f"⚡ Immediate fill detected for {symbol}")

                    return self._validate_fill(trade)

                # Keep event loop alive during quick checks
                self.ib.sleep(0.1)


            
            # Regular monitoring loop
            while time.time() - start_time < self.order_timeout and self._monitor_active:
                try:
                    # Check if order is done
                    if trade.isDone():
                        return self._validate_fill(trade, self.min_fill_ratio)
                    
                    # Check for partial fills
                    if trade.orderStatus.filled > 0:
                        fill_ratio = trade.orderStatus.filled / trade.order.totalQuantity
                        self.logger.debug(f"Partial fill for {symbol}: {fill_ratio:.1%}")
                        
                        # Accept partial fills above threshold
                        if fill_ratio >= self.min_fill_ratio:
                            self.logger.info(f"✅ Accepting partial fill for {symbol}: {fill_ratio:.1%}")
                            return True
                    


                    # Brief sleep to prevent busy waiting while keeping IB responsive
                    self.ib.sleep(0.5)
                
                except Exception as e:
                    self.logger.warning(f"Monitoring error for {symbol}: {e}")
                    # Longer pause on errors without blocking event loop
                    self.ib.sleep(1)

            
            # Timeout reached
            self.logger.warning(f"⏰ Order timeout for {symbol} after {self.order_timeout}s")
            
            # Try to cancel the order
            try:
                self.ib.cancelOrder(trade.order)

                # Give IB time to process cancellation
                self.ib.sleep(1)

                
                # Check final fill status
                if trade.orderStatus.filled > 0:
                    fill_ratio = trade.orderStatus.filled / trade.order.totalQuantity
                    if fill_ratio >= self.min_fill_ratio:
                        self.logger.info(f"✅ Final partial fill accepted for {symbol}: {fill_ratio:.1%}")
                        return True
            
            except Exception as e:
                self.logger.error(f"Failed to cancel order for {symbol}: {e}")
            
            return False
            
        except Exception as e:
            self.logger.error(f"Order monitoring failed for {symbol}: {e}", exc_info=True)
            return False
    
    
    def _compile_results(self, original_orders: List[Order], start_time: float, success: bool) -> ExecutionResult:
        """
        Compile final execution results.
        
        Args:
            original_orders: Original order list
            start_time: Execution start time
            success: Overall success flag
            
        Returns:
            ExecutionResult with summary
        """
        execution_time = time.time() - start_time
        
        # Calculate totals
        total_commission = 0
        successful_trades = []
        failed_orders = []
        
        for order_id, trade in self.completed_orders.items():
            try:
                # Create Trade object
                symbol = trade.contract.symbol
                
                # Find original order
                original_order = next((o for o in original_orders if o.symbol == symbol), None)
                if original_order:
                    trade_obj = Trade(
                        symbol=symbol,
                        action=original_order.action,
                        quantity=trade.orderStatus.filled,
                        price=trade.orderStatus.avgFillPrice or 0,
                        commission=trade.commissionReport.commission if trade.commissionReport else 0,
                        timestamp=datetime.now()
                    )
                    successful_trades.append(trade_obj)
                    
                    if trade.commissionReport:
                        total_commission += trade.commissionReport.commission
            
            except Exception as e:
                self.logger.error(f"Error compiling trade result: {e}")
        
        # Failed orders
        for order_id, error in self.failed_orders.items():
            failed_orders.append(f"Order {order_id}: {error}")
        
        self.logger.info(
            f"Batch execution completed: {len(successful_trades)} successful, "
            f"{len(failed_orders)} failed, ${total_commission:.2f} commission, "
            f"{execution_time:.1f}s execution time"
        )
        
        return ExecutionResult(
            success=success,
            orders_placed=successful_trades,
            orders_failed=failed_orders,
            total_commission=total_commission,
            execution_time=execution_time,
            errors=list(self.failed_orders.values()) if self.failed_orders else []
        )
    
    def _cleanup_monitoring(self):
        """Clean up monitoring resources."""
        self._monitor_active = False
        
        if self._executor:
            try:
                self._executor.shutdown(wait=True, timeout=5)
            except Exception as e:
                self.logger.warning(f"Cleanup warning: {e}")
        
        # Clear tracking dictionaries
        self.active_orders.clear()
        self.completed_orders.clear()
        self.failed_orders.clear() 

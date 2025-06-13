"""
Native batch order executor using IB's built-in batch capabilities.
Replaces ThreadPoolExecutor with IB's native order handling.
"""

import time
from datetime import datetime
from typing import Dict, List

from ib_insync import IB, Contract, LimitOrder, MarketOrder
from ib_insync import Trade as IBTrade

from src.config.settings import Config
from src.core.types import ExecutionResult, Order, OrderAction, OrderStatus, Trade
from src.portfolio.manager import PortfolioManager
from src.utils.delay import wait

from .base_executor import BaseExecutor


class NativeBatchExecutor(BaseExecutor):
    """
    Native batch order executor using IB's built-in capabilities.
    
    Features:
    - Submit all orders to TWS/Gateway at once (true batch)
    - Let IB handle concurrency internally
    - Monitor all orders using IB's event system
    - No thread pools - just efficient event-driven monitoring
    - Simpler and more reliable than ThreadPoolExecutor approach
    """

    def __init__(
        self,
        ib: IB,
        portfolio_manager: PortfolioManager,
        config: Config,
        contracts: Dict[str, Contract],
        margin_cushion: float = 0.2,
    ):
        super().__init__(ib, portfolio_manager, config, contracts)
        self.margin_cushion = margin_cushion

        # Execution parameters
        self.order_timeout = 300  # 5 minutes per order
        self.batch_timeout = 600  # 10 minutes total batch timeout
        self.min_fill_ratio = 0.8  # 80% fill required

        # Order tracking
        self.active_trades: Dict[int, IBTrade] = {}
        self.completed_trades: List[IBTrade] = []
        self.failed_trades: Dict[int, str] = {}

    def execute_batch(self, orders: List[Order]) -> ExecutionResult:
        """
        Execute batch of orders using IB's native batch capabilities.
        
        Args:
            orders: List of orders to execute
            
        Returns:
            ExecutionResult with execution summary
        """
        start_time = time.time()
        
        self.logger.info(f"🚀 Starting native batch execution of {len(orders)} orders")
        
        try:
            # Step 1: Pre-flight margin check
            if not self._check_batch_margin_safety(orders):
                return ExecutionResult(
                    success=False,
                    orders_placed=[],
                    orders_failed=[],
                    total_commission=0,
                    execution_time=time.time() - start_time,
                    errors=["Batch margin check failed"],
                )

            # Step 2: Submit all orders to IB at once (true batch)
            submitted_trades = self._submit_batch_orders(orders)
            if not submitted_trades:
                return ExecutionResult(
                    success=False,
                    orders_placed=[],
                    orders_failed=[],
                    total_commission=0,
                    execution_time=time.time() - start_time,
                    errors=["Failed to submit any orders"],
                )

            # Step 3: Monitor using IB's event system
            success = self._monitor_batch_completion(submitted_trades)

            # Step 4: Compile results
            return self._compile_results(orders, start_time, success)

        except Exception as e:
            self.logger.error(f"Native batch execution failed: {e}", exc_info=True)
            return ExecutionResult(
                success=False,
                orders_placed=[],
                orders_failed=[],
                total_commission=0,
                execution_time=time.time() - start_time,
                errors=[f"Batch execution error: {str(e)}"],
            )
        finally:
            self._cleanup()

    def _check_batch_margin_safety(self, orders: List[Order]) -> bool:
        """
        Check margin safety for entire batch.
        
        Args:
            orders: List of orders to validate
            
        Returns:
            True if batch is safe to execute
        """
        try:
            self.logger.info("Checking batch margin safety")
            
            account = self.portfolio_manager.get_account_summary()
            available_funds = account.get("AvailableFunds", 0)
            net_liquidation = account.get("NetLiquidation", 0)
            
            # Calculate total estimated cost for all BUY orders
            total_buy_cost = 0
            for order in orders:
                if order.action == OrderAction.BUY:
                    contract = self.contracts.get(order.symbol)
                    if contract:
                        # Get quick price estimate
                        ticker = self.ib.reqMktData(contract, "", False, False)
                        wait(0.1, self.ib)  # Brief wait for price
                        
                        price = ticker.marketPrice() or ticker.last or ticker.midpoint()
                        if price and price > 0:
                            total_buy_cost += price * order.quantity
                        
                        self.ib.cancelMktData(contract)
            
            # Apply margin cushion
            required_funds = total_buy_cost * (1 + self.margin_cushion)
            
            self.logger.info(
                f"Margin check: Need {required_funds:,.2f}, Available: {available_funds:,.2f}"
            )
            
            # Safety checks
            margin_safe = required_funds <= available_funds
            position_safe = total_buy_cost <= net_liquidation * 0.8  # Max 80% of NLV
            
            if not margin_safe:
                self.logger.error(f"Insufficient funds: need {required_funds:,.2f}, have {available_funds:,.2f}")
                return False
                
            if not position_safe:
                self.logger.error(f"Position too large: {total_buy_cost:,.2f} exceeds 80% of NLV")
                return False
            
            self.logger.info("✅ Batch margin check passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Margin check failed: {e}")
            return False

    def _submit_batch_orders(self, orders: List[Order]) -> List[IBTrade]:
        """
        Submit all orders to IB at once (true batch submission).
        
        Args:
            orders: List of orders to submit
            
        Returns:
            List of IBTrade objects
        """
        submitted_trades = []
        
        self.logger.info(f"📤 Submitting batch of {len(orders)} orders to IB")
        
        # Submit all orders rapidly in sequence
        # IB handles the concurrency internally
        for order in orders:
            try:
                contract = self.contracts.get(order.symbol)
                if not contract:
                    self.logger.error(f"Contract not found for {order.symbol}")
                    self.failed_trades[0] = f"Contract not found: {order.symbol}"
                    continue
                
                # Create appropriate order type
                ib_order = self._create_smart_order(order, contract)
                
                # Submit to IB (non-blocking)
                trade = self.ib.placeOrder(contract, ib_order)
                
                if trade:
                    submitted_trades.append(trade)
                    self.active_trades[trade.order.orderId] = trade
                    self.logger.info(f"✅ Submitted: {order.symbol} {order.action.value} {order.quantity}")
                else:
                    self.logger.error(f"❌ Failed to submit: {order.symbol}")
                    
            except Exception as e:
                self.logger.error(f"Error submitting {order.symbol}: {e}")
                self.failed_trades[0] = f"{order.symbol}: {str(e)}"
        
        self.logger.info(f"📊 Successfully submitted {len(submitted_trades)}/{len(orders)} orders")
        return submitted_trades

    def _create_smart_order(self, order: Order, contract: Contract) -> object:
        """
        Create smart order type based on order size.
        
        Args:
            order: Order specification
            contract: IB contract
            
        Returns:
            IB order object
        """
        # Get current market price for smart order sizing
        ticker = self.ib.reqMktData(contract, "", False, False)
        wait(0.1, self.ib)
        
        market_price = ticker.marketPrice() or ticker.last or ticker.midpoint()
        order_value = market_price * order.quantity if market_price else 0
        
        self.ib.cancelMktData(contract)
        
        # Smart order type selection
        if order_value < 10000:  # Small orders: market orders for speed
            ib_order = MarketOrder(
                action=order.action.value,
                totalQuantity=order.quantity
            )
            self.logger.debug(f"Market order: {order.symbol} (${order_value:,.0f})")
        else:  # Large orders: limit orders for control
            if market_price and market_price > 0:
                # Add small buffer for limit orders
                if order.action == OrderAction.BUY:
                    limit_price = market_price * 1.002  # 0.2% above market
                else:
                    limit_price = market_price * 0.998  # 0.2% below market
                    
                ib_order = LimitOrder(
                    action=order.action.value,
                    totalQuantity=order.quantity,
                    lmtPrice=round(limit_price, 2)
                )
                self.logger.debug(f"Limit order: {order.symbol} @ ${limit_price:.2f}")
            else:
                # Fallback to market order
                ib_order = MarketOrder(
                    action=order.action.value,
                    totalQuantity=order.quantity
                )
        
        return ib_order

    def _monitor_batch_completion(self, trades: List[IBTrade]) -> bool:
        """
        Monitor batch completion using IB's event system.
        No thread pools - just efficient polling.
        
        Args:
            trades: List of trades to monitor
            
        Returns:
            True if batch completed successfully
        """
        if not trades:
            return False
            
        self.logger.info(f"👀 Monitoring batch of {trades} orders")
        
        start_time = time.time()
        completed_count = 0
        
        # Monitor until all done or timeout
        while (time.time() - start_time) < self.batch_timeout:
            all_done = True
            
            for trade in trades:
                if trade.order.orderId in self.active_trades:
                    # Check if this trade is done
                    if trade.isDone():
                        # Move to completed
                        del self.active_trades[trade.order.orderId]
                        
                        # Validate fill
                        if self._validate_fill(trade):
                            self.completed_trades.append(trade)
                            completed_count += 1
                            self.logger.info(f"✅ Completed: {trade.contract.symbol}")
                        else:
                            self.failed_trades[trade.order.orderId] = "Insufficient fill"
                            self.logger.warning(f"⚠️ Poor fill: {trade.contract.symbol}")
                    else:
                        all_done = False
            
            if all_done:
                break
                
            # Efficient wait that keeps IB responsive
            wait(0.5, self.ib)
        
        # Handle any remaining orders (timeout)
        for trade in trades:
            if trade.order.orderId in self.active_trades:
                self.logger.warning(f"⏰ Timeout: {trade.contract.symbol}")
                try:
                    self.ib.cancelOrder(trade.order)
                    wait(1, self.ib)  # Give time for cancellation
                    
                    # Check if partially filled
                    if trade.orderStatus.filled > 0:
                        fill_ratio = trade.orderStatus.filled / trade.order.totalQuantity
                        if fill_ratio >= self.min_fill_ratio:
                            self.completed_trades.append(trade)
                            completed_count += 1
                            self.logger.info(f"✅ Partial fill accepted: {trade.contract.symbol}")
                        else:
                            self.failed_trades[trade.order.orderId] = f"Timeout with poor fill: {fill_ratio:.1%}"
                    else:
                        self.failed_trades[trade.order.orderId] = "Timeout with no fill"
                except Exception as e:
                    self.logger.error(f"Cancel failed for {trade.contract.symbol}: {e}")
                    self.failed_trades[trade.order.orderId] = f"Cancel failed: {str(e)}"
        
        success_rate = completed_count / len(trades) if trades else 0
        self.logger.info(f"📊 Batch monitoring completed: {completed_count}/{len(trades)} ({success_rate:.1%})")
        
        return success_rate >= 0.8  # Require 80% success

    def _validate_fill(self, trade: IBTrade) -> bool:
        """
        Validate that trade fill meets minimum requirements.
        
        Args:
            trade: IBTrade to validate
            
        Returns:
            True if fill is acceptable
        """
        filled = trade.orderStatus.filled
        total = trade.order.totalQuantity
        
        if total == 0:
            return False
            
        fill_ratio = filled / total
        return fill_ratio >= self.min_fill_ratio

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
        
        # Build successful trades
        successful_trades = []
        total_commission = 0
        
        for trade in self.completed_trades:
            try:
                symbol = trade.contract.symbol
                
                # Find original order
                original_order = next((o for o in original_orders if o.symbol == symbol), None)
                if original_order:
                    trade_obj = Trade(
                        order_id=trade.order.orderId,
                        symbol=symbol,
                        action=original_order.action,
                        quantity=trade.orderStatus.filled,
                        fill_price=trade.orderStatus.avgFillPrice or 0,
                        commission=trade.commissionReport.commission if trade.commissionReport else 0,
                        timestamp=datetime.now(),
                        status=OrderStatus.FILLED,
                    )
                    successful_trades.append(trade_obj)
                    
                    if trade.commissionReport:
                        total_commission += trade.commissionReport.commission
                        
            except Exception as e:
                self.logger.error(f"Error compiling trade result: {e}")
        
        # Build failed orders list
        failed_orders = [f"Order {order_id}: {error}" for order_id, error in self.failed_trades.items()]
        
        self.logger.info(
            f"Native batch execution completed: {len(successful_trades)} successful, "
            f"{len(failed_orders)} failed, {total_commission:.2f} commission, "
            f"{execution_time:.1f}s execution time"
        )
        
        return ExecutionResult(
            success=success,
            orders_placed=successful_trades,
            orders_failed=failed_orders,
            total_commission=total_commission,
            execution_time=execution_time,
            errors=list(self.failed_trades.values()) if self.failed_trades else [],
        )

    def _cleanup(self):
        """Clean up tracking data."""
        self.active_trades.clear()
        self.completed_trades.clear()
        self.failed_trades.clear()
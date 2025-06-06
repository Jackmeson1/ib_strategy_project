"""
Smart Order Executor with enhanced order management, margin control, and retry logic.
Addresses production-level issues with market orders, sequential execution, and partial fills.
"""
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from ib_insync import IB, Contract, LimitOrder, MarketOrder
from ib_insync import Trade as IBTrade

from src.config.settings import Config
from src.core.types import ExecutionResult, Order, OrderAction, OrderStatus, RebalanceRequest, Trade
from src.portfolio.manager import PortfolioManager
from .base_executor import BaseExecutor


class OrderType(Enum):
    """Enhanced order types for smart execution."""
    MARKET = "MKT"
    LIMIT = "LMT"
    STOP = "STP"
    BRACKET = "BRACKET"


class OrderPriority(Enum):
    """Order execution priority levels."""
    HIGH = "HIGH"      # Large positions, immediate execution needed
    MEDIUM = "MEDIUM"   # Standard rebalancing
    LOW = "LOW"        # Small adjustments


@dataclass
class SmartOrder:
    """Enhanced order with retry logic and execution parameters."""
    base_order: Order
    order_type: OrderType = OrderType.LIMIT
    priority: OrderPriority = OrderPriority.MEDIUM
    limit_price: Optional[float] = None
    max_retries: int = 3
    retry_count: int = 0
    timeout_seconds: int = 120
    partial_fill_threshold: float = 0.8  # Consider 80%+ fill as success

    # Execution tracking
    total_filled: int = 0
    remaining_quantity: int = 0
    average_fill_price: float = 0.0
    ib_trades: List[IBTrade] = None

    def __post_init__(self):
        if self.ib_trades is None:
            self.ib_trades = []
        self.remaining_quantity = self.base_order.quantity


@dataclass
class MarginCheck:
    """Margin and buying power validation."""
    available_funds: float
    required_funds: float
    margin_cushion: float
    is_safe: bool
    warning_message: Optional[str] = None


class SmartOrderExecutor(BaseExecutor):
    """
    Production-ready order executor with:
    - Smart order types (Limit, Market, Stop)
    - Parallel execution within batches
    - Retry logic for partial fills
    - Margin control and safety checks
    - Position sizing based on available funds
    """

    def __init__(
        self,
        ib: IB,
        portfolio_manager: PortfolioManager,
        config: Config,
        contracts: Dict[str, Contract]
    ):

        super().__init__(ib, portfolio_manager, config, contracts)
        

        # Execution parameters
        self.max_parallel_orders = 3  # Conservative parallel execution
        self.margin_cushion = 0.2     # 20% margin safety buffer

        # Order management
        self.active_orders: Dict[str, SmartOrder] = {}
        self.execution_lock = threading.Lock()

    def execute_rebalance(self, request: RebalanceRequest) -> ExecutionResult:
        """
        Execute rebalance with smart order management.
        
        Args:
            request: Rebalance request with target positions
            
        Returns:
            ExecutionResult with detailed execution info
        """
        start_time = time.time()
        self.logger.info(
            "Starting smart rebalance execution",
            target_leverage=request.target_leverage,
            reason=request.reason,
            dry_run=request.dry_run
        )

        try:
            # 1. Pre-flight margin check
            margin_check = self._check_margin_safety(request.target_positions)
            if not margin_check.is_safe:
                self.logger.error(f"Margin check failed: {margin_check.warning_message}")
                return ExecutionResult(
                    success=False,
                    orders_placed=[],
                    orders_failed=[],
                    total_commission=0,
                    execution_time=time.time() - start_time,
                    errors=[f"Margin safety violation: {margin_check.warning_message}"]
                )

            # 2. Calculate smart orders with position sizing
            smart_orders = self._calculate_smart_orders(
                request.target_positions,
                margin_check.available_funds
            )

            if not smart_orders:
                self.logger.info("No orders needed for rebalance")
                return ExecutionResult(
                    success=True,
                    orders_placed=[],
                    orders_failed=[],
                    total_commission=0,
                    execution_time=time.time() - start_time,
                    errors=[]
                )

            if request.dry_run:
                self.logger.info("DRY RUN: Would execute smart orders", orders=len(smart_orders))
                for order in smart_orders:
                    self.logger.info(
                        f"  {order.base_order.symbol}: {order.base_order.action.value} "
                        f"{order.base_order.quantity} shares ({order.order_type.value})"
                    )
                return ExecutionResult(
                    success=True,
                    orders_placed=[],
                    orders_failed=[],
                    total_commission=0,
                    execution_time=time.time() - start_time,
                    errors=[]
                )

            # 3. Execute with smart batching and retry logic
            return self._execute_smart_batches(smart_orders, request.target_leverage)

        except Exception as e:
            self.logger.error(f"Smart rebalance execution failed: {e}", exc_info=True)
            return ExecutionResult(
                success=False,
                orders_placed=[],
                orders_failed=[],
                total_commission=0,
                execution_time=time.time() - start_time,
                errors=[str(e)]
            )

    def _check_margin_safety(self, target_positions: Dict[str, int]) -> MarginCheck:
        """
        Comprehensive margin and buying power check before execution.
        
        Args:
            target_positions: Target positions to achieve
            
        Returns:
            MarginCheck with safety assessment
        """
        try:
            account = self.portfolio_manager.get_account_summary()
            current_positions = self.portfolio_manager.get_positions()

            available_funds = account.get('AvailableFunds', 0)
            buying_power = account.get('BuyingPower', 0)
            nlv = account.get('NetLiquidation', 0)

            # Calculate required funds for new positions
            required_funds = 0
            for symbol, target_qty in target_positions.items():
                current_qty = current_positions.get(symbol, type('obj', (object,), {'quantity': 0})).quantity
                qty_diff = target_qty - current_qty

                if qty_diff > 0:  # Only count additional purchases
                    # Get current market price
                    contract = self.contracts.get(symbol)
                    if contract:
                        ticker = self.ib.reqMktData(contract, '', False, False)
                        self.ib.sleep(1)  # Wait for price

                        current_price = None
                        if ticker.last and ticker.last > 0:
                            current_price = ticker.last
                        elif ticker.close and ticker.close > 0:
                            current_price = ticker.close

                        self.ib.cancelMktData(contract)

                        if current_price:
                            required_funds += qty_diff * current_price

            # Apply margin cushion
            cushioned_required = required_funds * (1 + self.margin_cushion)

            # Safety checks
            is_safe = True
            warning_message = None

            if cushioned_required > available_funds:
                is_safe = False
                warning_message = (
                    f"Insufficient funds: Need ${cushioned_required:,.0f} "
                    f"but only ${available_funds:,.0f} available"
                )
            elif cushioned_required > buying_power * 0.8:  # Use max 80% of buying power
                is_safe = False
                warning_message = (
                    f"Would use {cushioned_required/buying_power:.1%} of buying power, "
                    f"exceeds 80% safety limit"
                )
            elif available_funds < nlv * 0.1:  # Keep 10% cash cushion
                is_safe = False
                warning_message = (
                    f"Insufficient cash cushion: ${available_funds:,.0f} is less than "
                    f"10% of account value ${nlv * 0.1:,.0f}"
                )

            self.logger.info(
                "Margin safety check",
                required_funds=f"${required_funds:,.0f}",
                available_funds=f"${available_funds:,.0f}",
                margin_cushion=f"{self.margin_cushion:.1%}",
                is_safe=is_safe
            )

            return MarginCheck(
                available_funds=available_funds,
                required_funds=required_funds,
                margin_cushion=self.margin_cushion,
                is_safe=is_safe,
                warning_message=warning_message
            )

        except Exception as e:
            self.logger.error(f"Margin check failed: {e}")
            return MarginCheck(
                available_funds=0,
                required_funds=0,
                margin_cushion=0,
                is_safe=False,
                warning_message=f"Margin check error: {str(e)}"
            )

    def _calculate_smart_orders(
        self,
        target_positions: Dict[str, int],
        available_funds: float
    ) -> List[SmartOrder]:
        """
        Calculate smart orders with position sizing and order type optimization.
        
        Args:
            target_positions: Target positions to achieve
            available_funds: Available funds for trading
            
        Returns:
            List of SmartOrder objects with optimal execution parameters
        """
        smart_orders = []
        current_positions = self.portfolio_manager.get_positions()

        # Calculate total required funds first
        total_required = 0
        order_requirements = []

        for symbol, target_qty in target_positions.items():
            current_qty = current_positions.get(symbol, type('obj', (object,), {'quantity': 0})).quantity
            qty_diff = target_qty - current_qty

            if abs(qty_diff) < 1:  # Skip negligible differences
                continue

            # Get current price for position sizing
            contract = self.contracts.get(symbol)
            if not contract:
                self.logger.warning(f"No contract found for {symbol}")
                continue

            # Get market data
            ticker = self.ib.reqMktData(contract, '', False, False)
            self.ib.sleep(0.5)

            current_price = None
            if ticker.last and ticker.last > 0:
                current_price = ticker.last
            elif ticker.close and ticker.close > 0:
                current_price = ticker.close

            self.ib.cancelMktData(contract)

            if not current_price:
                self.logger.warning(f"No price data for {symbol}")
                continue

            if qty_diff > 0:  # Only count purchases for fund requirements
                required = qty_diff * current_price
                total_required += required
                order_requirements.append((symbol, qty_diff, current_price, required))
            else:
                order_requirements.append((symbol, qty_diff, current_price, 0))

        # Apply position sizing if needed
        scaling_factor = 1.0
        if total_required > available_funds * 0.8:  # Use max 80% of available funds
            scaling_factor = (available_funds * 0.8) / total_required
            self.logger.warning(
                f"Position sizing applied: {scaling_factor:.2%} of original order sizes",
                total_required=f"${total_required:,.0f}",
                available=f"${available_funds:,.0f}"
            )

        # Create smart orders
        for symbol, qty_diff, current_price, required in order_requirements:
            # Apply scaling
            scaled_qty = int(qty_diff * scaling_factor) if qty_diff > 0 else qty_diff

            if abs(scaled_qty) < 1:
                continue

            action = OrderAction.BUY if scaled_qty > 0 else OrderAction.SELL
            base_order = Order(
                symbol=symbol,
                action=action,
                quantity=abs(scaled_qty)
            )

            # Determine order type and priority based on size and volatility
            order_value = abs(scaled_qty) * current_price
            order_type = self._determine_order_type(order_value, symbol)
            priority = self._determine_priority(order_value)

            # Set limit price for limit orders (conservative pricing)
            limit_price = None
            if order_type == OrderType.LIMIT:
                if action == OrderAction.BUY:
                    limit_price = current_price * 1.002  # 0.2% above market for buys
                else:
                    limit_price = current_price * 0.998  # 0.2% below market for sells

            smart_order = SmartOrder(
                base_order=base_order,
                order_type=order_type,
                priority=priority,
                limit_price=limit_price,
                max_retries=3 if order_value > 10000 else 2,  # More retries for large orders
                timeout_seconds=180 if order_value > 25000 else 120
            )

            smart_orders.append(smart_order)

            self.logger.info(
                f"Smart order created for {symbol}",
                action=action.value,
                quantity=abs(scaled_qty),
                order_type=order_type.value,
                priority=priority.value,
                value=f"${order_value:,.0f}"
            )

        return smart_orders

    def _determine_order_type(self, order_value: float, symbol: str) -> OrderType:
        """Determine optimal order type based on order size and market conditions."""
        if order_value > 50000 or order_value > 10000:  # Large orders use limit with wider spread
            return OrderType.LIMIT
        else:  # Small orders can use market
            return OrderType.MARKET

    def _determine_priority(self, order_value: float) -> OrderPriority:
        """Determine execution priority based on order size."""
        if order_value > 50000:
            return OrderPriority.HIGH
        elif order_value > 10000:
            return OrderPriority.MEDIUM
        else:
            return OrderPriority.LOW

    def _execute_smart_batches(
        self,
        smart_orders: List[SmartOrder],
        target_leverage: float
    ) -> ExecutionResult:
        """Execute smart orders in optimized batches with parallel processing.

        Each batch uses :func:`_execute_parallel_batch`, which places multiple
        orders concurrently using a thread pool limited by ``max_parallel_orders``.
        """
        start_time = time.time()
        all_trades = []
        all_failed = []
        all_errors = []
        total_commission = 0

        # Sort orders by priority
        smart_orders.sort(key=lambda x: (x.priority.value, -x.base_order.quantity))

        # Create batches with parallel execution capability
        batch_size = min(self.max_parallel_orders, len(smart_orders))
        batches = [
            smart_orders[i:i + batch_size]
            for i in range(0, len(smart_orders), batch_size)
        ]

        for batch_idx, batch in enumerate(batches):
            self.logger.info(f"Executing smart batch {batch_idx + 1}/{len(batches)} with {len(batch)} orders")

            # Execute batch with parallel processing
            batch_result = self._execute_parallel_batch(batch)
            all_trades.extend(batch_result.orders_placed)
            all_failed.extend(batch_result.orders_failed)
            all_errors.extend(batch_result.errors)
            total_commission += batch_result.total_commission

            # Brief pause between batches
            if batch_idx < len(batches) - 1:

                # Use IB.sleep so the event loop remains active during pauses
                self.ib.sleep(2)
            

            # Monitor leverage after each batch
            try:
                current_leverage = self.portfolio_manager.get_portfolio_leverage()
                self.logger.info(f"Leverage after batch {batch_idx + 1}: {current_leverage:.2f}x")

                if current_leverage > self.config.strategy.emergency_leverage_threshold:
                    self.logger.critical("Emergency leverage threshold exceeded")
                    break

            except Exception as e:
                self.logger.error(f"Failed to check leverage: {e}")

        success = len(all_failed) == 0 and len(all_errors) == 0

        return ExecutionResult(
            success=success,
            orders_placed=all_trades,
            orders_failed=all_failed,
            total_commission=total_commission,
            execution_time=time.time() - start_time,
            errors=all_errors
        )

    def _execute_parallel_batch(self, smart_orders: List[SmartOrder]) -> ExecutionResult:
        """Execute a batch of orders concurrently using a thread pool.

        Orders are submitted to a :class:`ThreadPoolExecutor` with at most
        ``self.max_parallel_orders`` workers so that multiple orders can be
        placed in parallel while avoiding excessive concurrency on the IB
        connection.
        """

        start_time = time.time()
        trades: List[Trade] = []
        failed: List[Order] = []
        errors: List[str] = []
        commission = 0

        max_order_timeout = max(order.timeout_seconds for order in smart_orders)

        self.logger.info(
            f"Starting parallel batch with {len(smart_orders)} orders"
        )

        with ThreadPoolExecutor(max_workers=min(len(smart_orders), self.max_parallel_orders)) as executor:
            future_map = {
                executor.submit(
                    self._execute_single_smart_order_with_timeout,
                    order,
                    max_order_timeout,
                ): order
                for order in smart_orders
            }

            for future in as_completed(future_map):
                order = future_map[future]
                try:
                    result = future.result()
                    if result:
                        trades.append(result)
                    else:
                        failed.append(order.base_order)
                        errors.append(f"Failed to execute {order.base_order.symbol}")
                except Exception as e:  # pragma: no cover - defensive
                    self.logger.error(f"Error executing {order.base_order.symbol}: {e}")
                    failed.append(order.base_order)
                    errors.append(f"{order.base_order.symbol}: {str(e)}")

        batch_time = time.time() - start_time
        self.logger.info(
            f"Parallel batch completed in {batch_time:.1f}s: Success: {len(trades)}, Failed: {len(failed)}"
        )

        return ExecutionResult(
            success=len(failed) == 0,
            orders_placed=trades,
            orders_failed=failed,
            total_commission=commission,
            execution_time=batch_time,
            errors=errors,
        )

    def _execute_single_smart_order_with_timeout(self, smart_order: SmartOrder, max_timeout: int) -> Optional[Trade]:
        """Execute single order with additional timeout protection."""
        def timeout_handler(signum, frame):
            raise TimeoutError(f"Order execution timeout for {smart_order.base_order.symbol}")

        # Set up timeout protection (Unix-like systems only)
        old_handler = None
        try:
            if hasattr(signal, 'SIGALRM'):
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(max_timeout + 30)  # Extra 30s buffer
        except (AttributeError, OSError):
            # Windows or other systems without SIGALRM
            pass

        try:
            return self._execute_single_smart_order(smart_order)
        except TimeoutError as e:
            self.logger.error(f"Timeout executing {smart_order.base_order.symbol}: {e}")
            return None
        finally:
            # Clean up timeout
            try:
                if hasattr(signal, 'SIGALRM') and old_handler is not None:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
            except (AttributeError, OSError):
                pass

    def _execute_single_smart_order(self, smart_order: SmartOrder) -> Optional[Trade]:
        """Execute a single smart order with retry logic and partial fill handling - fixed hanging issues."""
        order_placed = False
        current_ib_trade = None

        for attempt in range(smart_order.max_retries + 1):
            try:
                self.logger.info(f"Executing {smart_order.base_order.symbol} (attempt {attempt + 1}/{smart_order.max_retries + 1})")

                # Cancel any previous order if it exists and isn't filled
                if current_ib_trade and not order_placed:
                    try:
                        self.ib.cancelOrder(current_ib_trade.order)
                        self.logger.info(
                            f"Cancelled previous order for {smart_order.base_order.symbol}"
                        )
                        # Keep event loop responsive while waiting
                        self.ib.sleep(0.5)
                    except Exception as e:
                        self.logger.warning(f"Failed to cancel previous order: {e}")

                # Create appropriate IB order
                ib_order = self._create_ib_order(smart_order)

                # Place order
                contract = self.contracts[smart_order.base_order.symbol]
                current_ib_trade = self.ib.placeOrder(contract, ib_order)
                order_placed = True

                self.logger.info(
                    f"Order placed for {smart_order.base_order.symbol}: "
                    f"{ib_order.action} {ib_order.totalQuantity} @ {getattr(ib_order, 'lmtPrice', 'MARKET')}"
                )

                # Wait for execution with timeout
                filled_trade = self._wait_for_fill(current_ib_trade, smart_order.timeout_seconds)

                if filled_trade:
                    self.logger.info(f"Successfully executed {smart_order.base_order.symbol}")
                    return filled_trade
                else:
                    # Check for partial fill
                    partial_result = self._handle_partial_fill(smart_order, current_ib_trade)
                    if partial_result:
                        # If partial fill is acceptable, return what we got
                        self.logger.info(f"Accepting partial fill for {smart_order.base_order.symbol}")
                        return self._create_trade_from_partial(smart_order, current_ib_trade)

                    # Order failed or timed out - prepare for retry
                    smart_order.retry_count += 1
                    if smart_order.retry_count <= smart_order.max_retries:
                        self.logger.warning(
                            f"Order {smart_order.base_order.symbol} failed/timed out, "
                            f"will retry (attempt {smart_order.retry_count + 1})"
                        )

                        # Cancel the timed-out order before retrying
                        try:
                            if current_ib_trade:
                                self.ib.cancelOrder(current_ib_trade.order)
                                # Allow IB event loop to process cancellation
                                self.ib.sleep(1)
                        except Exception as e:
                            self.logger.warning(f"Failed to cancel timed-out order: {e}")

                        order_placed = False
                        # Short pause before retry while keeping IB responsive
                        self.ib.sleep(2)
                        continue
                    else:
                        self.logger.error(f"Max retries exceeded for {smart_order.base_order.symbol}")
                        break

            except Exception as e:
                self.logger.error(f"Error executing {smart_order.base_order.symbol}: {e}")
                smart_order.retry_count += 1

                # Cancel any stuck order
                if current_ib_trade and order_placed:
                    try:
                        self.ib.cancelOrder(current_ib_trade.order)
                        self.logger.info(f"Cancelled order due to error: {smart_order.base_order.symbol}")
                    except Exception as cancel_error:
                        self.logger.warning(f"Failed to cancel order after error: {cancel_error}")

                if smart_order.retry_count <= smart_order.max_retries:
                    order_placed = False
                    # Give IB time after error before retrying
                    self.ib.sleep(3)
                    continue
                else:
                    self.logger.error(f"Max retries exceeded for {smart_order.base_order.symbol} after error")
                    break

        # Clean up any remaining order
        if current_ib_trade and order_placed:
            try:
                self.ib.cancelOrder(current_ib_trade.order)
                self.logger.info(f"Final cleanup: cancelled order for {smart_order.base_order.symbol}")
            except Exception as e:
                self.logger.warning(f"Failed final order cleanup: {e}")

        return None

    def _create_ib_order(self, smart_order: SmartOrder):
        """Create appropriate IB order based on smart order configuration."""
        quantity = smart_order.remaining_quantity
        action = smart_order.base_order.action.value

        if smart_order.order_type == OrderType.MARKET:
            return MarketOrder(action=action, totalQuantity=quantity)

        elif smart_order.order_type == OrderType.LIMIT:
            return LimitOrder(
                action=action,
                totalQuantity=quantity,
                lmtPrice=smart_order.limit_price
            )

        else:  # Fallback to market
            return MarketOrder(action=action, totalQuantity=quantity)

    def _wait_for_fill(self, ib_trade: IBTrade, timeout_seconds: int) -> Optional[Trade]:
        """Wait for order to fill with timeout - fixed to prevent hanging."""
        start_time = time.time()
        check_interval = 0.5  # Check every 0.5 seconds instead of 1 second
        max_immediate_checks = 5  # Check immediately filled orders quickly

        # First, do a few quick checks for immediate fills (market orders)
        last_status = getattr(ib_trade.orderStatus, 'status', None)
        last_update = time.time()
        last_refresh = 0.0
        refresh_interval = 15  # Minimum seconds between reqIds calls
        stall_threshold = 10   # Time without status change before refresh

        for quick_check in range(max_immediate_checks):
            self.ib.sleep(0.1)  # Very brief pause

            # Refresh connection if no status update
            if (
                time.time() - last_update > stall_threshold
                and time.time() - last_refresh > refresh_interval
            ):
                self.logger.debug("Refreshing connection via reqIds")
                self.ib.reqIds(-1)
                last_refresh = time.time()

            # Check if already filled
            if hasattr(ib_trade.orderStatus, 'status'):
                status = ib_trade.orderStatus.status
                if status != last_status:
                    last_update = time.time()
                    last_status = status
                self.logger.debug(f"Order status check {quick_check + 1}: {status}")

                if status == 'Filled':
                    self.logger.info(f"Order {ib_trade.contract.symbol} filled immediately")
                    return self._create_trade_from_ib(ib_trade)
                elif status in ['Cancelled', 'ApiCancelled', 'Inactive']:
                    self.logger.warning(f"Order {ib_trade.contract.symbol} cancelled/inactive: {status}")
                    return None

        # If not immediately filled, do regular monitoring with timeout
        while time.time() - start_time < timeout_seconds:
            self.ib.sleep(check_interval)

            # Refresh connection if status hasn't changed
            if (
                time.time() - last_update > stall_threshold
                and time.time() - last_refresh > refresh_interval
            ):
                self.logger.debug("Refreshing connection via reqIds")
                self.ib.reqIds(-1)
                last_refresh = time.time()

            # Check order status
            if hasattr(ib_trade.orderStatus, 'status'):
                status = ib_trade.orderStatus.status
                filled = getattr(ib_trade.orderStatus, 'filled', 0)
                remaining = getattr(ib_trade.orderStatus, 'remaining', 0)

                if status != last_status:
                    last_update = time.time()
                    last_status = status

                self.logger.debug(
                    f"Order {ib_trade.contract.symbol}: status={status}, "
                    f"filled={filled}, remaining={remaining}"
                )

                if status == 'Filled':
                    self.logger.info(f"Order {ib_trade.contract.symbol} completed")
                    return self._create_trade_from_ib(ib_trade)
                elif status in ['Cancelled', 'ApiCancelled', 'Inactive']:
                    self.logger.warning(f"Order {ib_trade.contract.symbol} cancelled: {status}")
                    return None
                elif filled > 0 and remaining == 0:
                    # Sometimes status doesn't update but fill info does
                    self.logger.info(f"Order {ib_trade.contract.symbol} detected as filled via fill count")
                    return self._create_trade_from_ib(ib_trade)

            # Check using isDone() as backup
            try:
                if ib_trade.isDone():
                    if hasattr(ib_trade.orderStatus, 'status') and ib_trade.orderStatus.status == 'Filled':
                        return self._create_trade_from_ib(ib_trade)
                    else:
                        self.logger.warning(f"Order {ib_trade.contract.symbol} done but not filled")
                        break
            except Exception as e:
                self.logger.warning(f"Error checking isDone() for {ib_trade.contract.symbol}: {e}")

        # Timeout reached
        self.logger.warning(
            f"Order {ib_trade.contract.symbol} timed out after {timeout_seconds}s. "
            f"Final status: {getattr(ib_trade.orderStatus, 'status', 'Unknown')}"
        )
        return None

    def _handle_partial_fill(self, smart_order: SmartOrder, ib_trade: IBTrade) -> bool:
        """Determine if partial fill is acceptable."""
        if hasattr(ib_trade.orderStatus, 'filled'):
            filled_qty = ib_trade.orderStatus.filled
            fill_ratio = filled_qty / smart_order.base_order.quantity

            if fill_ratio >= smart_order.partial_fill_threshold:
                self.logger.info(
                    f"Accepting partial fill for {smart_order.base_order.symbol}: "
                    f"{filled_qty}/{smart_order.base_order.quantity} ({fill_ratio:.1%})"
                )
                return True
            else:
                # Update remaining quantity for retry
                smart_order.total_filled += filled_qty
                smart_order.remaining_quantity = smart_order.base_order.quantity - smart_order.total_filled
                return False

        return False

    def _create_trade_from_partial(self, smart_order: SmartOrder, ib_trade: IBTrade) -> Trade:
        """Create trade object from partial fill."""
        filled_qty = getattr(ib_trade.orderStatus, 'filled', 0)
        avg_price = getattr(ib_trade.orderStatus, 'avgFillPrice', 0)

        return Trade(
            order_id=ib_trade.order.orderId,
            symbol=smart_order.base_order.symbol,
            action=smart_order.base_order.action,
            quantity=filled_qty,
            fill_price=avg_price,
            commission=0,  # Commission would be calculated separately
            timestamp=datetime.now(),
            status=OrderStatus.PARTIALLY_FILLED
        )


    def _create_trade_from_ib(self, ib_trade: IBTrade) -> Trade:
        """Create trade object from completed IB trade - enhanced error handling."""
        try:
            # Get order details with fallback values
            order_id = getattr(ib_trade.order, 'orderId', 0)
            symbol = getattr(ib_trade.contract, 'symbol', 'UNKNOWN')
            action_str = getattr(ib_trade.order, 'action', 'BUY')

            # Get fill details with validation
            filled_qty = getattr(ib_trade.orderStatus, 'filled', 0)
            avg_price = getattr(ib_trade.orderStatus, 'avgFillPrice', 0.0)

            # Validate fill data
            if filled_qty <= 0:
                self.logger.warning(f"Invalid filled quantity for {symbol}: {filled_qty}")
                filled_qty = getattr(ib_trade.order, 'totalQuantity', 0)

            if avg_price <= 0:
                self.logger.warning(f"Invalid fill price for {symbol}: {avg_price}")
                # Try to get a reasonable price estimate
                try:
                    ticker = self.ib.reqMktData(ib_trade.contract, '', False, False)
                    self.ib.sleep(0.5)
                    if ticker.last and ticker.last > 0:
                        avg_price = ticker.last
                    elif ticker.close and ticker.close > 0:
                        avg_price = ticker.close
                    self.ib.cancelMktData(ib_trade.contract)
                except Exception as e:
                    self.logger.warning(f"Could not get market price for {symbol}: {e}")
                    avg_price = 1.0  # Fallback

            # Determine order status
            status = OrderStatus.FILLED
            if hasattr(ib_trade.orderStatus, 'status'):
                if ib_trade.orderStatus.status == 'PartiallyFilled':
                    status = OrderStatus.PARTIALLY_FILLED

            trade = Trade(
                order_id=order_id,
                symbol=symbol,
                action=OrderAction.BUY if action_str == 'BUY' else OrderAction.SELL,
                quantity=int(filled_qty),
                fill_price=float(avg_price),
                commission=0,  # Would be updated from execution reports
                timestamp=datetime.now(),
                status=status
            )

            self.logger.debug(f"Created trade: {symbol} {action_str} {filled_qty} @ ${avg_price:.2f}")
            return trade

        except Exception as e:
            self.logger.error(f"Error creating trade from IB trade: {e}")
            # Return a minimal trade object as fallback
            return Trade(
                order_id=0,
                symbol="ERROR",
                action=OrderAction.BUY,
                quantity=0,
                fill_price=0.0,
                commission=0,
                timestamp=datetime.now(),
                status=OrderStatus.FILLED
            )


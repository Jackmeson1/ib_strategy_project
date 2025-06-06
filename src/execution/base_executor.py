from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from ib_insync import IB, Contract, Trade as IBTrade

from src.config.settings import Config
from src.core.types import Order, OrderAction, OrderStatus, Trade
from src.portfolio.manager import PortfolioManager
from src.utils.logger import get_logger


class BaseExecutor:
    """Common functionality for all order executors."""

    def __init__(
        self,
        ib: IB,
        portfolio_manager: PortfolioManager,
        config: Config,
        contracts: Dict[str, Contract],
    ) -> None:
        self.ib = ib
        self.portfolio_manager = portfolio_manager
        self.config = config
        self.contracts = contracts
        self.logger = get_logger(self.__class__.__name__)

    def _create_trade_from_ib(self, ib_trade: IBTrade, order: Optional[Order] = None) -> Trade:
        """Construct a :class:`Trade` object from an IB trade."""
        symbol = order.symbol if order else getattr(ib_trade.contract, "symbol", "")
        action_str = getattr(ib_trade.order, "action", "BUY")
        action = order.action if order else (OrderAction.BUY if action_str == "BUY" else OrderAction.SELL)
        quantity = getattr(ib_trade.orderStatus, "filled", 0)
        avg_price = getattr(ib_trade.orderStatus, "avgFillPrice", 0.0)
        commission = sum(getattr(fill.commissionReport, "commission", 0) for fill in getattr(ib_trade, "fills", []))
        status_str = getattr(ib_trade.orderStatus, "status", "Filled")
        try:
            status = OrderStatus(status_str)
        except ValueError:
            status = OrderStatus.FILLED

        return Trade(
            order_id=getattr(ib_trade.order, "orderId", 0),
            symbol=symbol,
            action=action,
            quantity=int(quantity),
            fill_price=float(avg_price),
            commission=float(commission),
            timestamp=datetime.now(),
            status=status,
        )

    def _validate_fill(self, ib_trade: IBTrade, min_fill_ratio: float) -> bool:
        """Validate that the fill ratio of an IB trade meets expectations."""
        try:
            status = getattr(ib_trade.orderStatus, "status", "")
            if status in ["Filled", "PartiallyFilled"]:
                filled_qty = getattr(ib_trade.orderStatus, "filled", 0)
                total_qty = getattr(ib_trade.order, "totalQuantity", 0)
                fill_ratio = filled_qty / total_qty if total_qty else 0

                if fill_ratio >= min_fill_ratio:
                    self.logger.info(
                        f"Valid fill for {ib_trade.contract.symbol}: {filled_qty}/{total_qty}"
                    )
                    return True
                self.logger.warning(
                    f"Insufficient fill for {ib_trade.contract.symbol}: {fill_ratio:.1%} < {min_fill_ratio:.1%}"
                )
                return False

            self.logger.warning(
                f"Invalid status for {ib_trade.contract.symbol}: {status}"
            )
            return False
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.error(f"Fill validation failed: {exc}")
            return False

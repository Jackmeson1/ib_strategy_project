"""
Type definitions for the Dynamic Leverage Bot.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, TypedDict, Union

import pandas as pd


class OrderAction(Enum):
    """Order action types."""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    """Order status types."""
    PENDING = "PendingSubmit"
    SUBMITTED = "Submitted"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    PARTIAL = "PartiallyFilled"
    PARTIALLY_FILLED = "PartiallyFilled"
    INACTIVE = "Inactive"


class MAType(Enum):
    """Moving average types."""
    SMA = "SMA"
    EMA = "EMA"
    HMA = "HMA"
    WMA = "WMA"


class PositionDict(TypedDict):
    """Type definition for position data."""
    position: float
    avgCost: float


class AccountSummaryDict(TypedDict, total=False):
    """Type definition for account summary data."""
    NetLiquidation: float
    GrossPositionValue: float
    AvailableFunds: float
    MaintMarginReq: float
    InitMarginReq: float
    BuyingPower: float
    EquityWithLoanValue: float


@dataclass
class Position:
    """Enhanced position data."""
    symbol: str
    quantity: float
    avg_cost: float
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    
    @property
    def market_value(self) -> float:
        """Calculate market value."""
        if self.current_price is not None:
            return self.quantity * self.current_price
        return self.quantity * self.avg_cost
    
    @property
    def cost_basis(self) -> float:
        """Calculate cost basis."""
        return self.quantity * self.avg_cost


@dataclass
class Order:
    """Order data."""
    symbol: str
    action: OrderAction
    quantity: int
    order_type: str = "MARKET"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    
    def __post_init__(self):
        if self.quantity <= 0:
            raise ValueError("Order quantity must be positive")


@dataclass
class Trade:
    """Trade execution data."""
    order_id: int
    symbol: str
    action: OrderAction
    quantity: int
    fill_price: float
    commission: float
    timestamp: datetime
    status: OrderStatus


@dataclass
class MarketData:
    """Market data snapshot."""
    symbol: str
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    volume: Optional[int]
    timestamp: datetime
    
    @property
    def midpoint(self) -> Optional[float]:
        """Calculate midpoint price."""
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return None
    
    @property
    def spread(self) -> Optional[float]:
        """Calculate bid-ask spread."""
        if self.bid is not None and self.ask is not None:
            return self.ask - self.bid
        return None


@dataclass
class VIXData:
    """VIX data with calculated indicators."""
    date: datetime
    close: float
    ma_value: float
    ma_type: MAType
    ma_window: int


@dataclass
class LeverageState:
    """Current leverage state."""
    current_leverage: float
    target_leverage: float
    vix_level: float
    vix_ma: float
    requires_rebalance: bool
    margin_safe: bool


@dataclass
class PortfolioWeight:
    """Portfolio weight definition."""
    symbol: str
    weight: float
    sector: Optional[str] = None
    
    def __post_init__(self):
        if not 0 <= self.weight <= 1:
            raise ValueError(f"Weight must be between 0 and 1, got {self.weight}")


class PortfolioWeights(Dict[str, PortfolioWeight]):
    """Portfolio weights container."""
    
    def validate(self) -> bool:
        """Validate that weights sum to approximately 1."""
        total = sum(w.weight for w in self.values())
        return abs(total - 1.0) < 0.001
    
    def get_weight(self, symbol: str) -> float:
        """Get weight for a symbol."""
        return self.get(symbol, PortfolioWeight(symbol, 0.0)).weight


@dataclass
class ExecutionResult:
    """Result of order execution."""
    success: bool
    orders_placed: List[Trade]
    orders_failed: List[Order]
    total_commission: float
    execution_time: float
    errors: List[str]


@dataclass
class RebalanceRequest:
    """Request to rebalance portfolio."""
    target_positions: Dict[str, int]
    target_leverage: float
    reason: str
    dry_run: bool = False
    force: bool = False 
"""
Custom exceptions for the Dynamic Leverage Bot.
Provides clear categorization of errors and better error handling.
"""
from typing import Optional


class BaseBotError(Exception):
    """Base exception for all bot-related errors."""
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.details = details or {}


class ConfigurationError(BaseBotError):
    """Raised when there's a configuration issue."""
    pass


class ConnectionError(BaseBotError):
    """Raised when connection to IB fails."""
    pass


class MarketDataError(BaseBotError):
    """Raised when market data retrieval fails."""
    pass


class OrderExecutionError(BaseBotError):
    """Raised when order execution fails."""
    pass


class PositionError(BaseBotError):
    """Raised when there's an issue with positions."""
    pass


class MarginError(BaseBotError):
    """Raised when margin requirements are not met."""
    pass


class EmergencyError(BaseBotError):
    """Raised when emergency conditions are detected."""
    def __init__(self, message: str, current_leverage: float, threshold: float):
        super().__init__(message, {
            "current_leverage": current_leverage,
            "threshold": threshold
        })
        self.current_leverage = current_leverage
        self.threshold = threshold


class DataIntegrityError(BaseBotError):
    """Raised when data integrity issues are detected."""
    pass


class RetryableError(BaseBotError):
    """Base class for errors that can be retried."""
    def __init__(self, message: str, retry_count: int = 0, max_retries: int = 3):
        super().__init__(message, {
            "retry_count": retry_count,
            "max_retries": max_retries
        })
        self.retry_count = retry_count
        self.max_retries = max_retries
    
    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries


class TemporaryError(RetryableError):
    """Raised for temporary errors that should be retried."""
    pass


class FatalError(BaseBotError):
    """Raised for fatal errors that require immediate shutdown."""
    pass 
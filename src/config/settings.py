"""
Configuration settings for the Portfolio Rebalancing Tool.
All sensitive information should be loaded from environment variables or the OS keyring.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import keyring
except ImportError:  # pragma: no cover - keyring optional
    keyring = None

KEYRING_SERVICE = "ib-portfolio-rebalancer"


def getenv(name: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve a configuration value from environment or keyring."""
    value = os.getenv(name)
    if value:
        return value
    if keyring:
        try:
            secret = keyring.get_password(KEYRING_SERVICE, name)
            if secret:
                return secret
        except Exception:
            pass
    return default


@dataclass
class IBConfig:
    """Interactive Brokers connection configuration."""


    host: str = field(default_factory=lambda: getenv("IB_GATEWAY_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(getenv("IB_GATEWAY_PORT", "4002")))
    client_id: int = field(default_factory=lambda: int(getenv("IB_CLIENT_ID", "1")))
    account_id: str = field(default_factory=lambda: getenv("IB_ACCOUNT_ID", ""))


    def __post_init__(self):
        if not self.account_id:
            raise ValueError("IB_ACCOUNT_ID environment variable is required")


@dataclass
class TelegramConfig:
    """Telegram notification configuration."""

    bot_token: Optional[str] = field(default_factory=lambda: getenv("TELEGRAM_BOT_TOKEN"))
    chat_id: Optional[str] = field(default_factory=lambda: getenv("TELEGRAM_CHAT_ID"))

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)


@dataclass
class StrategyConfig:
    """Strategy parameters configuration."""

    # Fixed leverage settings
    default_leverage: float = field(
        default_factory=lambda: float(getenv("DEFAULT_LEVERAGE", "1.4"))
    )
    leverage_buffer: float = field(default_factory=lambda: float(getenv("LEVERAGE_BUFFER", "0.1")))
    emergency_leverage_threshold: float = field(
        default_factory=lambda: float(getenv("EMERGENCY_LEVERAGE_THRESHOLD", "3.0"))
    )

    # Rebalancing parameters
    rebalance_tolerance: float = field(
        default_factory=lambda: float(getenv("REBALANCE_TOLERANCE", "0.05"))
    )
    safety_threshold: float = field(
        default_factory=lambda: float(getenv("SAFETY_THRESHOLD", "0.15"))
    )  # 15% safety buffer


@dataclass
class LoggingConfig:
    """Logging configuration."""

    log_level: str = field(default_factory=lambda: getenv("LOG_LEVEL", "INFO"))
    log_dir: Path = field(default_factory=lambda: Path(getenv("LOG_DIR", "logs")))
    max_log_size_mb: int = field(
        default_factory=lambda: int(getenv("LOG_MAX_BYTES", "10485760")) // 1048576
    )
    log_retention_count: int = field(default_factory=lambda: int(getenv("LOG_BACKUP_COUNT", "5")))

    def __post_init__(self):
        self.log_dir.mkdir(exist_ok=True)


@dataclass
class Config:
    """Main configuration container."""

    ib: IBConfig = field(default_factory=IBConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Runtime configuration
    dry_run: bool = field(default_factory=lambda: getenv("DRY_RUN", "false").lower() == "true")
    debug: bool = field(default_factory=lambda: getenv("DEBUG", "false").lower() == "true")

    # Market data settings
    primary_exchange: str = field(default_factory=lambda: getenv("PRIMARY_EXCHANGE", "SMART"))


def load_config() -> Config:
    """Load configuration from environment variables."""
    return Config()


# Example environment template
ENV_TEMPLATE = """# Interactive Brokers Configuration
IB_GATEWAY_HOST=127.0.0.1
IB_GATEWAY_PORT=7497  # Paper: 7497, Live: 7496, Gateway: 4002/4001
IB_CLIENT_ID=1
IB_ACCOUNT_ID=YOUR_ACCOUNT_ID

# Strategy Settings
DEFAULT_LEVERAGE=1.4              # Target leverage for portfolio
EMERGENCY_LEVERAGE_THRESHOLD=3.0  # Emergency liquidation threshold
LEVERAGE_BUFFER=0.1               # Rebalance when leverage deviates by this amount
REBALANCE_TOLERANCE=0.05          # Position weight tolerance (5%)
DRY_RUN=false                     # Set to true for testing without placing orders

# Market Data
PRIMARY_EXCHANGE=SMART

# Logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
LOG_DIR=logs
LOG_MAX_BYTES=10485760  # 10MB
LOG_BACKUP_COUNT=5

# Telegram Notifications (optional)
# TELEGRAM_BOT_TOKEN=your_bot_token_here
# TELEGRAM_CHAT_ID=your_chat_id_here
""".strip()


if __name__ == "__main__":
    # Create example .env file
    env_example_path = Path(".env.example")
    if not env_example_path.exists():
        with open(env_example_path, "w") as f:
            f.write(ENV_TEMPLATE)

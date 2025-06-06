"""
Configuration settings for the Portfolio Rebalancing Tool.
All sensitive information should be loaded from environment variables.
"""
import os
from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path


@dataclass
class IBConfig:
    """Interactive Brokers connection configuration."""
    host: str = field(default_factory=lambda: os.getenv("IB_GATEWAY_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("IB_GATEWAY_PORT", "4002")))
    client_id: int = field(default_factory=lambda: int(os.getenv("IB_CLIENT_ID", "1")))
    account_id: Optional[str] = field(default_factory=lambda: os.getenv("IB_ACCOUNT_ID"))

    def __post_init__(self):
        # account_id may be None when using multi-account mode
        pass


@dataclass
class TelegramConfig:
    """Telegram notification configuration."""
    bot_token: Optional[str] = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN"))
    chat_id: Optional[str] = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID"))
    
    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)


@dataclass
class StrategyConfig:
    """Strategy parameters configuration."""
    # Fixed leverage settings
    default_leverage: float = field(default_factory=lambda: float(os.getenv("DEFAULT_LEVERAGE", "1.4")))
    leverage_buffer: float = field(default_factory=lambda: float(os.getenv("LEVERAGE_BUFFER", "0.1")))
    emergency_leverage_threshold: float = field(default_factory=lambda: float(os.getenv("EMERGENCY_LEVERAGE_THRESHOLD", "3.0")))
    
    # Rebalancing parameters
    rebalance_tolerance: float = field(default_factory=lambda: float(os.getenv("REBALANCE_TOLERANCE", "0.05")))
    safety_threshold: float = field(default_factory=lambda: float(os.getenv("SAFETY_THRESHOLD", "0.15")))  # 15% safety buffer
    


@dataclass
class LoggingConfig:
    """Logging configuration."""
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_dir: Path = field(default_factory=lambda: Path(os.getenv("LOG_DIR", "logs")))
    max_log_size_mb: int = field(default_factory=lambda: int(os.getenv("LOG_MAX_BYTES", "10485760")) // 1048576)
    log_retention_count: int = field(default_factory=lambda: int(os.getenv("LOG_BACKUP_COUNT", "5")))
    
    def __post_init__(self):
        self.log_dir.mkdir(exist_ok=True)


@dataclass
class AccountConfig:
    """Individual account configuration."""
    account_id: str
    base_currency: str = "USD"


@dataclass
class Config:
    """Main configuration container."""
    ib: IBConfig = field(default_factory=IBConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    accounts: List[AccountConfig] = field(default_factory=list)
    
    # Runtime configuration
    dry_run: bool = field(default_factory=lambda: os.getenv("DRY_RUN", "false").lower() == "true")
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    
    # Market data settings
    primary_exchange: str = field(default_factory=lambda: os.getenv("PRIMARY_EXCHANGE", "SMART"))


def load_config() -> Config:
    """Load configuration from environment variables."""
    config = Config()
    accounts_env = os.getenv("IB_ACCOUNTS")
    accounts: List[AccountConfig] = []

    if accounts_env:
        parts = [p.strip() for p in accounts_env.split(',') if p.strip()]
        for part in parts:
            if ':' in part:
                acc_id, curr = part.split(':', 1)
                accounts.append(AccountConfig(acc_id.strip(), curr.strip().upper()))
            else:
                accounts.append(AccountConfig(part.strip(), os.getenv("IB_BASE_CURRENCY", "USD").upper()))
    else:
        account_id = os.getenv("IB_ACCOUNT_ID")
        if account_id:
            base = os.getenv("IB_BASE_CURRENCY", "USD").upper()
            accounts.append(AccountConfig(account_id, base))

    if not accounts:
        raise ValueError("No IB account configured. Set IB_ACCOUNT_ID or IB_ACCOUNTS")

    config.accounts = accounts
    if not config.ib.account_id:
        config.ib.account_id = accounts[0].account_id

    return config


# Example environment template
ENV_TEMPLATE = """# Interactive Brokers Configuration
IB_GATEWAY_HOST=127.0.0.1
IB_GATEWAY_PORT=4002  # Use 7497 for TWS paper, 7496 for TWS live
IB_CLIENT_ID=1
# Single account
IB_ACCOUNT_ID=YOUR_ACCOUNT_ID
# Or multiple accounts with base currencies
# IB_ACCOUNTS=DU1234567:CAD,DU7654321:USD

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

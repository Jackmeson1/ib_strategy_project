"""
Enhanced logging utilities with rotation, sanitization, and structured logging.
"""
import logging
import re
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional, Union

from src.config.settings import LoggingConfig


class SanitizingFormatter(logging.Formatter):
    """Custom formatter that sanitizes sensitive information."""
    
    # Patterns to sanitize
    SANITIZE_PATTERNS = [
        (r'(api[_-]?key|token|password|secret)["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'\1=***REDACTED***'),
        (r'(account[_-]?id)["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'\1=***ACCOUNT***'),
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***EMAIL***'),
        (r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', '***CARD***'),
    ]
    
    def format(self, record: logging.LogRecord) -> str:
        """Format and sanitize the log record."""
        msg = super().format(record)
        for pattern, replacement in self.SANITIZE_PATTERNS:
            msg = re.sub(pattern, replacement, msg, flags=re.IGNORECASE)
        return msg


class StructuredLogger:
    """Wrapper for structured logging with context."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.context: Dict[str, Any] = {}
    
    def set_context(self, **kwargs):
        """Set persistent context for all log messages."""
        self.context.update(kwargs)
    
    def clear_context(self):
        """Clear the logging context."""
        self.context.clear()
    
    def _log(self, level: int, msg: str, extra: Optional[Dict] = None, **kwargs):
        """Internal logging method with context injection."""
        log_extra = self.context.copy()
        if extra:
            log_extra.update(extra)
        log_extra.update(kwargs)
        self.logger.log(level, msg, extra={"structured": log_extra})
    
    def debug(self, msg: str, **kwargs):
        self._log(logging.DEBUG, msg, **kwargs)
    
    def info(self, msg: str, **kwargs):
        self._log(logging.INFO, msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        self._log(logging.WARNING, msg, **kwargs)
    
    def error(self, msg: str, **kwargs):
        self._log(logging.ERROR, msg, **kwargs)
    
    def critical(self, msg: str, **kwargs):
        self._log(logging.CRITICAL, msg, **kwargs)


def setup_logger(
    name: str,
    config: LoggingConfig,
    log_to_console: bool = True,
    log_to_file: bool = True
) -> StructuredLogger:
    """
    Set up a logger with rotation and sanitization.
    
    Args:
        name: Logger name
        config: Logging configuration
        log_to_console: Whether to log to console
        log_to_file: Whether to log to file
    
    Returns:
        StructuredLogger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.log_level.upper()))
    logger.handlers.clear()
    
    # Create formatters
    detailed_formatter = SanitizingFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(structured)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = SanitizingFormatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # File handlers
    if log_to_file:
        # Main log file with rotation by size
        log_file = config.log_dir / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=config.max_log_size_mb * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        logger.addHandler(file_handler)
        
        # Error log file
        error_file = config.log_dir / f"{name}_errors.log"
        error_handler = RotatingFileHandler(
            error_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        logger.addHandler(error_handler)
        
        # Daily rotation for archival
        daily_file = config.log_dir / f"{name}_daily.log"
        daily_handler = TimedRotatingFileHandler(
            daily_file,
            when='midnight',
            interval=1,
            backupCount=config.log_retention_count,
            encoding='utf-8'
        )
        daily_handler.setLevel(logging.INFO)
        daily_handler.setFormatter(detailed_formatter)
        logger.addHandler(daily_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    # Add empty structured data to avoid KeyError
    class StructuredFilter(logging.Filter):
        def filter(self, record):
            if not hasattr(record, 'structured'):
                record.structured = {}
            return True
    
    for handler in logger.handlers:
        handler.addFilter(StructuredFilter())
    
    return StructuredLogger(logger)


def get_logger(name: str) -> StructuredLogger:
    """Get an existing logger or create a new one with default config."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        from src.config.settings import load_config
        config = load_config()
        return setup_logger(name, config.logging)
    return StructuredLogger(logger) 
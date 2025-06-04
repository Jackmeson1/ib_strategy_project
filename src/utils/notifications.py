"""
Notification utilities for Telegram.
"""
import os
import tempfile
from typing import Optional, Dict, List

import requests

from src.config.settings import TelegramConfig
from src.core.types import AccountSummaryDict, Position, LeverageState
from src.utils.logger import get_logger


class TelegramNotifier:
    """Sends notifications to Telegram."""
    
    def __init__(self, config: TelegramConfig):
        self.config = config
        self.logger = get_logger(__name__)
        self.max_message_length = 4096
        
        if not self.config.is_configured:
            self.logger.warning("Telegram not configured - notifications disabled")
    
    @property
    def send_message_url(self) -> str:
        return f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
    
    @property
    def send_document_url(self) -> str:
        return f"https://api.telegram.org/bot{self.config.bot_token}/sendDocument"
    
    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Send a message to Telegram.
        
        Args:
            text: Message text
            parse_mode: Parse mode (Markdown or HTML)
            
        Returns:
            True if successful
        """
        if not self.config.is_configured:
            return False
        
        # If message is too long, send as file
        if len(text) > self.max_message_length:
            return self.send_file(text, "message.txt")
        
        payload = {
            "chat_id": self.config.chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        try:
            response = requests.post(self.send_message_url, json=payload, timeout=10)
            if response.ok:
                self.logger.debug("Telegram message sent successfully")
                return True
            else:
                self.logger.error(f"Failed to send Telegram message: {response.text}")
                return False
        except Exception as e:
            self.logger.error(f"Error sending Telegram message: {e}")
            return False
    
    def send_file(self, content: str, filename: str = "log.txt") -> bool:
        """
        Send a file to Telegram.
        
        Args:
            content: File content
            filename: Name for the file
            
        Returns:
            True if successful
        """
        if not self.config.is_configured:
            return False
        
        tmp_file_path = None
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=f"_{filename}") as tmp_file:
                tmp_file.write(content)
                tmp_file_path = tmp_file.name
            
            # Send file
            with open(tmp_file_path, 'rb') as file_obj:
                data = {"chat_id": self.config.chat_id}
                files = {"document": (filename, file_obj)}
                response = requests.post(self.send_document_url, data=data, files=files, timeout=30)
            
            if response.ok:
                self.logger.debug("Telegram file sent successfully")
                return True
            else:
                self.logger.error(f"Failed to send Telegram file: {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error sending Telegram file: {e}")
            return False
        finally:
            # Clean up temporary file
            if tmp_file_path and os.path.exists(tmp_file_path):
                os.remove(tmp_file_path)
    
    def send_portfolio_summary(
        self,
        account_summary: AccountSummaryDict,
        positions: Dict[str, Position],
        current_leverage: float,
        target_leverage: float
    ) -> bool:
        """
        Send a formatted portfolio summary.
        
        Args:
            account_summary: Account summary
            positions: Current positions
            current_leverage: Current portfolio leverage
            target_leverage: Target leverage
            
        Returns:
            True if successful
        """
        # Format account values
        nlv = account_summary.get('NetLiquidation', 0)
        available = account_summary.get('AvailableFunds', 0)
        margin_used = account_summary.get('MaintMarginReq', 0)
        
        # Build message
        lines = [
            "📊 *Portfolio Summary*",
            "",
            f"⚖️ *Leverage*",
            f"• Current: {current_leverage:.2f}x",
            f"• Target: {target_leverage:.2f}x",
            "",
            f"💰 *Account*",
            f"• Net Liquidation: ${nlv:,.0f}",
            f"• Available Funds: ${available:,.0f}",
            f"• Margin Used: ${margin_used:,.0f}",
        ]
        
        if positions:
            lines.extend([
                "",
                f"📈 *Top Positions* ({len(positions)} total)",
            ])
            # Show top 5 positions by value
            sorted_positions = sorted(
                positions.items(),
                key=lambda x: abs(x[1].market_value),
                reverse=True
            )[:5]
            
            total_value = sum(pos.market_value for pos in positions.values())
            for symbol, pos in sorted_positions:
                weight = pos.market_value / total_value if total_value > 0 else 0
                lines.append(
                    f"• {symbol}: {pos.quantity:,.0f} shares "
                    f"({weight:.1%} of portfolio)"
                )
        
        message = "\n".join(lines)
        return self.send_message(message) 
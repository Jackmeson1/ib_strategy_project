"""
IB connection management with proper resource handling and async support.
"""
import asyncio
import time
from contextlib import contextmanager, asynccontextmanager
from typing import Optional, Callable, Any

from ib_insync import IB, util
from ib_insync.contract import Contract

from src.config.settings import IBConfig
from src.core.exceptions import ConnectionError, FatalError
from src.utils.logger import get_logger


class IBConnectionManager:
    """Manages IB connection with proper resource handling."""
    
    def __init__(self, config: IBConfig):
        self.config = config
        self.logger = get_logger(__name__)
        self.ib: Optional[IB] = None
        self._is_connected = False
        self._callbacks_registered = False
    
    def connect(self, timeout: int = 30) -> IB:
        """
        Connect to IB Gateway/TWS.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            Connected IB instance
            
        Raises:
            ConnectionError: If connection fails
        """
        if self._is_connected and self.ib and self.ib.isConnected():
            return self.ib
        
        try:
            self.ib = IB()
            self.logger.info(
                "Connecting to IB",
                host=self.config.host,
                port=self.config.port,
                client_id=self.config.client_id
            )
            
            start_time = time.time()
            self.ib.connect(
                self.config.host,
                self.config.port,
                clientId=self.config.client_id,
                timeout=timeout
            )
            
            connection_time = time.time() - start_time
            self._is_connected = True
            
            self.logger.info(
                "Successfully connected to IB",
                connection_time=f"{connection_time:.2f}s",
                account_id=self.config.account_id
            )
            
            return self.ib
            
        except Exception as e:
            self.logger.error("Failed to connect to IB", error=str(e))
            self._cleanup()
            raise ConnectionError(f"Failed to connect to IB: {e}")
    
    def disconnect(self):
        """Disconnect from IB and cleanup resources."""
        if self.ib:
            try:
                if self.ib.isConnected():
                    self.logger.info("Disconnecting from IB")
                    self.ib.disconnect()
                self._is_connected = False
                self._callbacks_registered = False
            except Exception as e:
                self.logger.error("Error during disconnect", error=str(e))
            finally:
                self._cleanup()
    
    def _cleanup(self):
        """Cleanup resources."""
        self.ib = None
        self._is_connected = False
        self._callbacks_registered = False
    
    def register_callback(self, event_name: str, callback: Callable):
        """Register a callback for IB events."""
        if not self.ib:
            raise ConnectionError("Not connected to IB")
        
        event = getattr(self.ib, event_name, None)
        if event:
            event += callback
            self.logger.debug(f"Registered callback for {event_name}")
        else:
            self.logger.warning(f"Unknown event: {event_name}")
    
    def ensure_connected(self):
        """Ensure connection is active, reconnect if necessary."""
        if not self._is_connected or not self.ib or not self.ib.isConnected():
            self.logger.warning("Connection lost, attempting to reconnect")
            self.connect()
    
    @contextmanager
    def connection(self):
        """Context manager for IB connection."""
        try:
            self.connect()
            yield self.ib
        finally:
            self.disconnect()
    
    def __enter__(self):
        """Enter context manager."""
        return self.connect()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        self.disconnect()
        return False


class AsyncIBConnectionManager(IBConnectionManager):
    """Async version of IB connection manager."""
    
    def __init__(self, config: IBConfig):
        super().__init__(config)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    async def connect_async(self, timeout: int = 30) -> IB:
        """
        Async connect to IB Gateway/TWS.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            Connected IB instance
            
        Raises:
            ConnectionError: If connection fails
        """
        if self._is_connected and self.ib and self.ib.isConnected():
            return self.ib
        
        try:
            self.ib = IB()
            self.logger.info(
                "Connecting to IB (async)",
                host=self.config.host,
                port=self.config.port,
                client_id=self.config.client_id
            )
            
            await self.ib.connectAsync(
                self.config.host,
                self.config.port,
                clientId=self.config.client_id,
                timeout=timeout
            )
            
            self._is_connected = True
            self._loop = asyncio.get_event_loop()
            
            self.logger.info(
                "Successfully connected to IB (async)",
                account_id=self.config.account_id
            )
            
            return self.ib
            
        except Exception as e:
            self.logger.error("Failed to connect to IB (async)", error=str(e))
            await self._cleanup_async()
            raise ConnectionError(f"Failed to connect to IB: {e}")
    
    async def disconnect_async(self):
        """Async disconnect from IB and cleanup resources."""
        if self.ib:
            try:
                if self.ib.isConnected():
                    self.logger.info("Disconnecting from IB (async)")
                    self.ib.disconnect()
                self._is_connected = False
                self._callbacks_registered = False
            except Exception as e:
                self.logger.error("Error during async disconnect", error=str(e))
            finally:
                await self._cleanup_async()
    
    async def _cleanup_async(self):
        """Async cleanup resources."""
        self.ib = None
        self._is_connected = False
        self._callbacks_registered = False
        self._loop = None
    
    @asynccontextmanager
    async def async_connection(self):
        """Async context manager for IB connection."""
        try:
            await self.connect_async()
            yield self.ib
        finally:
            await self.disconnect_async()


def create_connection_manager(config: IBConfig, use_async: bool = False) -> IBConnectionManager:
    """
    Factory function to create appropriate connection manager.
    
    Args:
        config: IB configuration
        use_async: Whether to use async connection manager
        
    Returns:
        Connection manager instance
    """
    if use_async:
        # Ensure event loop is running for ib_insync
        util.startLoop()
        return AsyncIBConnectionManager(config)
    return IBConnectionManager(config) 
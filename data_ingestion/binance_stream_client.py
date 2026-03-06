"""
Binance WebSocket Stream Client for Live Market Data.

This module provides a WebSocket client for connecting to Binance Testnet
and streaming live trade data for specified symbols.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import List, Set, Optional, Callable
import websockets
from websockets.exceptions import ConnectionClosed

from config import get_settings
from aggregation.models import Tick
from data_ingestion.tick_store import TickStore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BinanceStreamClient:
    """
    WebSocket client for streaming live trade data from Binance Testnet.
    
    Connects to Binance Testnet WebSocket API and streams trade updates
    for specified symbols. Supports dynamic symbol subscription and
    automatic reconnection on disconnect.
    
    Attributes:
        tick_store: TickStore instance for storing latest ticks
        symbols: Set of currently subscribed symbols
        _ws: WebSocket connection instance
        _running: Flag indicating if the client is running
    """
    
    def __init__(self, tick_store: TickStore, symbols: Optional[List[str]] = None):
        """
        Initialize the Binance stream client.
        
        Args:
            tick_store: TickStore instance for storing received ticks
            symbols: Initial list of symbols to subscribe to
        """
        self.settings = get_settings()
        self.tick_store = tick_store
        self.symbols: Set[str] = set(s.lower() for s in (symbols or self.settings.symbols))
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_delay = 5  # seconds
        self._tick_callbacks: List[Callable[[Tick], None]] = []
    
    def add_tick_callback(self, callback: Callable[[Tick], None]) -> None:
        """
        Add a callback function to be called on each new tick.
        
        Args:
            callback: Function to call with each new Tick
        """
        self._tick_callbacks.append(callback)
    
    def remove_tick_callback(self, callback: Callable[[Tick], None]) -> None:
        """
        Remove a tick callback function.
        
        Args:
            callback: Function to remove from callbacks
        """
        if callback in self._tick_callbacks:
            self._tick_callbacks.remove(callback)
    
    def _build_stream_url(self) -> str:
        """
        Build the WebSocket stream URL for combined streams.
        
        Returns:
            Complete WebSocket URL with all symbol streams
        """
        # Build combined stream URL for trade streams
        # Format: wss://stream.testnet.binance.vision/stream?streams=btcusdt@trade/ethusdt@trade
        streams = "/".join(f"{symbol}@trade" for symbol in self.symbols)
        return f"{self.settings.binance_ws_url.replace('/ws', '/stream')}?streams={streams}"
    
    async def subscribe(self, symbol: str) -> None:
        """
        Subscribe to a new symbol's trade stream.
        
        Args:
            symbol: Symbol to subscribe to (e.g., 'BTCUSDT')
        """
        symbol = symbol.lower()
        if symbol not in self.symbols:
            self.symbols.add(symbol)
            logger.info(f"Added symbol {symbol.upper()} to subscription list")
            
            # If connected, need to reconnect to update streams
            if self._ws and self._running:
                logger.info("Reconnecting to update subscriptions...")
                await self._ws.close()
    
    async def unsubscribe(self, symbol: str) -> None:
        """
        Unsubscribe from a symbol's trade stream.
        
        Args:
            symbol: Symbol to unsubscribe from
        """
        symbol = symbol.lower()
        if symbol in self.symbols:
            self.symbols.discard(symbol)
            logger.info(f"Removed symbol {symbol.upper()} from subscription list")
            
            # If connected, need to reconnect to update streams
            if self._ws and self._running:
                logger.info("Reconnecting to update subscriptions...")
                await self._ws.close()
    
    def get_subscribed_symbols(self) -> List[str]:
        """
        Get list of currently subscribed symbols.
        
        Returns:
            List of subscribed symbol names (uppercase)
        """
        return [s.upper() for s in self.symbols]
    
    async def _handle_message(self, message: str) -> None:
        """
        Handle an incoming WebSocket message.
        
        Args:
            message: Raw JSON message from WebSocket
        """
        try:
            data = json.loads(message)
            
            # Combined stream format: {"stream": "btcusdt@trade", "data": {...}}
            if "stream" in data and "data" in data:
                stream_name = data["stream"]
                trade_data = data["data"]
                
                # Extract symbol from stream name (e.g., "btcusdt@trade" -> "BTCUSDT")
                symbol = stream_name.split("@")[0].upper()
                
                # Parse tick from trade data
                tick = Tick.from_binance_message(symbol, trade_data)
                
                # Store tick
                self.tick_store.update(tick)
                
                # Notify callbacks
                for callback in self._tick_callbacks:
                    try:
                        callback(tick)
                    except Exception as e:
                        logger.error(f"Error in tick callback: {e}")
                        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def _connect_and_stream(self) -> None:
        """
        Connect to WebSocket and stream messages.
        
        Handles connection, message receiving, and automatic reconnection.
        """
        while self._running:
            try:
                url = self._build_stream_url()
                logger.info(f"Connecting to Binance Testnet WebSocket...")
                logger.info(f"Subscribing to symbols: {', '.join(s.upper() for s in self.symbols)}")
                
                async with websockets.connect(url, ping_interval=20, ping_timeout=60) as ws:
                    self._ws = ws
                    logger.info("Connected to Binance Testnet WebSocket")
                    
                    async for message in ws:
                        if not self._running:
                            break
                        await self._handle_message(message)
                        
            except ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}")
                if self._running:
                    logger.info(f"Reconnecting in {self._reconnect_delay} seconds...")
                    await asyncio.sleep(self._reconnect_delay)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if self._running:
                    logger.info(f"Reconnecting in {self._reconnect_delay} seconds...")
                    await asyncio.sleep(self._reconnect_delay)
            finally:
                self._ws = None
    
    async def start(self) -> None:
        """
        Start the WebSocket streaming client.
        
        This method runs the streaming loop that connects to Binance
        and processes incoming messages.
        """
        if self._running:
            logger.warning("Stream client is already running")
            return
        
        self._running = True
        logger.info("Starting Binance stream client...")
        await self._connect_and_stream()
    
    async def stop(self) -> None:
        """
        Stop the WebSocket streaming client gracefully.
        """
        logger.info("Stopping Binance stream client...")
        self._running = False
        
        if self._ws:
            await self._ws.close()
        
        logger.info("Binance stream client stopped")
    
    @property
    def is_running(self) -> bool:
        """Check if the client is currently running."""
        return self._running
    
    @property
    def is_connected(self) -> bool:
        """Check if the client is currently connected."""
        return self._ws is not None and self._ws.open

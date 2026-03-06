"""
WebSocket Server for Real-Time Candle Broadcasting.

This module provides a WebSocket server that broadcasts candle updates
and strategy signals to connected clients. Supports both standalone
WebSocket server and FastAPI WebSocket integration.
"""

import asyncio
import json
import logging
from typing import Set, Optional, Callable, Union, Any
import websockets
from websockets.server import WebSocketServerProtocol

from aggregation.models import OHLCCandle
from strategy.base_strategy import Signal

logger = logging.getLogger(__name__)


class WebSocketServer:
    """
    WebSocket server for broadcasting real-time updates to clients.
    
    Broadcasts:
    - New closed candles
    - Strategy signals
    - Tick updates (optional)
    
    Attributes:
        host: Server host address
        port: Server port
        clients: Set of connected client WebSocket connections
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8001):
        """
        Initialize the WebSocket server.
        
        Args:
            host: Server host (default: 0.0.0.0)
            port: Server port (default: 8001)
        """
        self.host = host
        self.port = port
        # Support both websockets library and FastAPI WebSocket clients
        self.clients: Set[Any] = set()
        self._fastapi_clients: Set[Any] = set()  # FastAPI WebSocket clients
        self._server = None
        self._running = False
        
        logger.info(f"WebSocket server configured on {host}:{port}")
    
    async def _register(self, websocket: WebSocketServerProtocol) -> None:
        """
        Register a new client connection.
        
        Args:
            websocket: Client WebSocket connection
        """
        self.clients.add(websocket)
        logger.info(f"Client connected: {websocket.remote_address}. Total clients: {len(self.clients)}")
        
        # Send welcome message
        await websocket.send(json.dumps({
            "type": "connected",
            "message": "Connected to Crypto Trading WebSocket Server",
            "total_clients": len(self.clients)
        }))
    
    async def _unregister(self, websocket: WebSocketServerProtocol) -> None:
        """
        Unregister a client connection.
        
        Args:
            websocket: Client WebSocket connection
        """
        self.clients.discard(websocket)
        logger.info(f"Client disconnected. Remaining clients: {len(self.clients)}")
    
    async def _handle_client(self, websocket: WebSocketServerProtocol) -> None:
        """
        Handle a client WebSocket connection.
        
        Args:
            websocket: Client WebSocket connection
        """
        await self._register(websocket)
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    
                    # Handle client messages (e.g., subscribe to specific symbols)
                    if data.get("action") == "subscribe":
                        symbols = data.get("symbols", [])
                        await websocket.send(json.dumps({
                            "type": "subscribed",
                            "symbols": symbols
                        }))
                    
                    elif data.get("action") == "ping":
                        await websocket.send(json.dumps({
                            "type": "pong",
                            "timestamp": data.get("timestamp")
                        }))
                        
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Invalid JSON"
                    }))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self._unregister(websocket)
    
    async def broadcast(self, message: dict) -> None:
        """
        Broadcast a message to all connected clients.
        
        Args:
            message: Message dictionary to broadcast
        """
        if not self.clients:
            return
        
        message_str = json.dumps(message)
        
        # Create list to track failed clients
        failed_clients = []
        
        for client in self.clients.copy():
            try:
                await client.send(message_str)
            except websockets.exceptions.ConnectionClosed:
                failed_clients.append(client)
            except Exception as e:
                logger.error(f"Failed to send to client: {e}")
                failed_clients.append(client)
        
        # Remove failed clients
        for client in failed_clients:
            await self._unregister(client)
    
    async def broadcast_candle(self, candle: OHLCCandle) -> None:
        """
        Broadcast a closed candle to all clients.
        
        Args:
            candle: The closed OHLC candle
        """
        message = {
            "type": "candle",
            "data": candle.to_dict()
        }
        # Broadcast to standalone clients
        await self.broadcast(message)
        # Also broadcast to FastAPI clients
        await self.broadcast_to_fastapi(message)
    
    async def broadcast_signal(
        self, 
        symbol: str, 
        variant: str, 
        signal: Signal, 
        price: float
    ) -> None:
        """
        Broadcast a strategy signal to all clients.
        
        Args:
            symbol: Trading symbol
            variant: Strategy variant
            signal: Trading signal
            price: Current price
        """
        message = {
            "type": "signal",
            "data": {
                "symbol": symbol,
                "variant": variant,
                "signal": signal.value,
                "price": price
            }
        }
        # Broadcast to standalone clients
        await self.broadcast(message)
        # Also broadcast to FastAPI clients
        await self.broadcast_to_fastapi(message)
    
    def on_candle(self, candle: OHLCCandle) -> None:
        """
        Callback for candle close events.
        
        Args:
            candle: The closed candle
        """
        asyncio.create_task(self.broadcast_candle(candle))
    
    def on_signal(
        self, 
        symbol: str, 
        variant: str, 
        signal: Signal, 
        price: float
    ) -> None:
        """
        Callback for strategy signal events.
        
        Args:
            symbol: Trading symbol
            variant: Strategy variant
            signal: Trading signal
            price: Current price
        """
        asyncio.create_task(
            self.broadcast_signal(symbol, variant, signal, price)
        )
    
    async def start(self) -> None:
        """Start the WebSocket server."""
        if self._running:
            logger.warning("WebSocket server is already running")
            return
        
        self._running = True
        self._server = await websockets.serve(
            self._handle_client,
            self.host,
            self.port
        )
        
        logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")
    
    async def stop(self) -> None:
        """Stop the WebSocket server gracefully."""
        if not self._running:
            return
        
        self._running = False
        
        # Close all client connections
        for client in self.clients.copy():
            try:
                await client.close()
            except Exception:
                pass
        
        self.clients.clear()
        
        # Close server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        
        logger.info("WebSocket server stopped")
    
    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running
    
    @property
    def client_count(self) -> int:
        """Get number of connected clients (both standalone and FastAPI)."""
        return len(self.clients) + len(self._fastapi_clients)
    
    # =========================================================================
    # FastAPI WebSocket Integration
    # =========================================================================
    
    async def handle_fastapi_websocket(self, websocket) -> None:
        """
        Handle a FastAPI WebSocket connection.
        
        This method is called from the FastAPI WebSocket endpoint.
        
        Args:
            websocket: FastAPI WebSocket connection
        """
        # Accept the connection
        await websocket.accept()
        
        # Register client
        self._fastapi_clients.add(websocket)
        logger.info(f"FastAPI WebSocket client connected. Total clients: {self.client_count}")
        
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to Crypto Trading WebSocket Server",
            "total_clients": self.client_count
        })
        
        try:
            while True:
                try:
                    # Receive and handle messages
                    data = await websocket.receive_json()
                    
                    if data.get("action") == "subscribe":
                        symbols = data.get("symbols", [])
                        await websocket.send_json({
                            "type": "subscribed",
                            "symbols": symbols
                        })
                    elif data.get("action") == "ping":
                        await websocket.send_json({
                            "type": "pong",
                            "timestamp": data.get("timestamp")
                        })
                except Exception:
                    # Client likely disconnected
                    break
        finally:
            # Unregister client
            self._fastapi_clients.discard(websocket)
            logger.info(f"FastAPI WebSocket client disconnected. Remaining: {self.client_count}")
    
    async def broadcast_to_fastapi(self, message: dict) -> None:
        """
        Broadcast a message to all FastAPI WebSocket clients.
        
        Args:
            message: Message dictionary to broadcast
        """
        if not self._fastapi_clients:
            return
        
        failed_clients = []
        
        for client in self._fastapi_clients.copy():
            try:
                await client.send_json(message)
            except Exception:
                failed_clients.append(client)
        
        # Remove failed clients
        for client in failed_clients:
            self._fastapi_clients.discard(client)
    
    async def broadcast_all(self, message: dict) -> None:
        """
        Broadcast to both standalone and FastAPI clients.
        
        Args:
            message: Message dictionary to broadcast
        """
        # Broadcast to standalone clients
        await self.broadcast(message)
        # Broadcast to FastAPI clients
        await self.broadcast_to_fastapi(message)


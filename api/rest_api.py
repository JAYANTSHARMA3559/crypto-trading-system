"""
REST API for the Crypto Trading System.

This module provides FastAPI endpoints for accessing trading data,
managing symbols, and viewing system status.
"""

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
import os

from aggregation.ohlc_aggregator import OHLCAggregator
from strategy.strategy_manager import StrategyManager
from execution.trade_logger import TradeLogger
from data_ingestion.tick_store import TickStore

logger = logging.getLogger(__name__)


# Request/Response models
class SymbolRequest(BaseModel):
    """Request model for adding a symbol."""
    symbol: str


class CandleResponse(BaseModel):
    """Response model for OHLC candle data."""
    symbol: str
    open: float
    high: float
    low: float
    close: float
    timestamp: str
    volume: float
    tick_count: int
    is_closed: bool


class PositionResponse(BaseModel):
    """Response model for position data."""
    symbol: str
    side: str
    entry_price: float
    entry_time: Optional[str]
    quantity: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    stop_loss_price: float


class TradeResponse(BaseModel):
    """Response model for trade data."""
    timestamp: str
    symbol: str
    side: str
    size: float
    price: float
    variant: str
    order_id: Optional[str]
    status: str
    pnl: Optional[float]
    notes: Optional[str]


# Global references (set during app creation)
_ohlc_aggregator: Optional[OHLCAggregator] = None
_strategy_manager: Optional[StrategyManager] = None
_trade_logger: Optional[TradeLogger] = None
_tick_store: Optional[TickStore] = None
_ws_server = None  # WebSocket server for FastAPI integration
_add_symbol_callback = None
_remove_symbol_callback = None


def create_app(
    ohlc_aggregator: OHLCAggregator,
    strategy_manager: StrategyManager,
    trade_logger: TradeLogger,
    tick_store: TickStore,
    ws_server=None,
    add_symbol_callback=None,
    remove_symbol_callback=None
) -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Args:
        ohlc_aggregator: OHLC aggregator instance
        strategy_manager: Strategy manager instance
        trade_logger: Trade logger instance
        tick_store: Tick store instance
        add_symbol_callback: Callback for adding symbols
        remove_symbol_callback: Callback for removing symbols
        
    Returns:
        Configured FastAPI application
    """
    global _ohlc_aggregator, _strategy_manager, _trade_logger, _tick_store
    global _add_symbol_callback, _remove_symbol_callback, _ws_server
    
    _ohlc_aggregator = ohlc_aggregator
    _strategy_manager = strategy_manager
    _trade_logger = trade_logger
    _tick_store = tick_store
    _ws_server = ws_server
    _add_symbol_callback = add_symbol_callback
    _remove_symbol_callback = remove_symbol_callback
    
    app = FastAPI(
        title="Crypto Trading System API",
        description="API for accessing live crypto trading data and system status",
        version="1.0.0"
    )
    
    # Store references in app.state (recommended FastAPI pattern)
    app.state.trade_logger = trade_logger
    app.state.tick_store = tick_store
    app.state.strategy_manager = strategy_manager
    app.state.ohlc_aggregator = ohlc_aggregator
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Health check endpoint
    @app.get("/health", tags=["System"])
    async def health_check():
        """Check if the system is healthy."""
        return {
            "status": "healthy",
            "symbols": _strategy_manager.get_symbols() if _strategy_manager else [],
            "tick_count": len(_tick_store) if _tick_store else 0
        }
    
    # Debug endpoint
    @app.get("/debug", tags=["System"])
    async def debug_status():
        """Debug endpoint to check component availability."""
        return {
            "trade_logger": _trade_logger is not None,
            "tick_store": _tick_store is not None,
            "strategy_manager": _strategy_manager is not None,
            "ohlc_aggregator": _ohlc_aggregator is not None
        }
    
    # Symbol management endpoints
    @app.get("/symbols", tags=["Symbols"])
    async def get_symbols() -> List[str]:
        """Get list of active symbols."""
        return _strategy_manager.get_symbols() if _strategy_manager else []
    
    @app.post("/symbols/{symbol}", tags=["Symbols"])
    async def add_symbol(symbol: str) -> Dict[str, str]:
        """
        Add a new symbol to track.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
        """
        symbol = symbol.upper()
        
        if _add_symbol_callback:
            await _add_symbol_callback(symbol)
        
        if _strategy_manager:
            _strategy_manager.add_symbol(symbol)
        
        return {"message": f"Symbol {symbol} added successfully"}
    
    @app.delete("/symbols/{symbol}", tags=["Symbols"])
    async def remove_symbol(symbol: str) -> Dict[str, str]:
        """
        Remove a symbol from tracking.
        
        Args:
            symbol: Trading symbol to remove
        """
        symbol = symbol.upper()
        
        if _remove_symbol_callback:
            await _remove_symbol_callback(symbol)
        
        if _strategy_manager:
            _strategy_manager.remove_symbol(symbol)
        
        return {"message": f"Symbol {symbol} removed successfully"}
    
    # Candle data endpoints
    @app.get("/candles/{symbol}", tags=["Candles"])
    async def get_candles(
        symbol: str,
        limit: int = Query(default=50, ge=1, le=500)
    ) -> Dict[str, Any]:
        """
        Get OHLC candle history for a symbol.
        
        Args:
            symbol: Trading symbol
            limit: Number of candles to return (default: 50)
        """
        if not _ohlc_aggregator:
            raise HTTPException(status_code=500, detail="Aggregator not available")
        
        symbol = symbol.upper()
        history = _ohlc_aggregator.get_history(symbol, limit)
        current = _ohlc_aggregator.get_current_candle(symbol)
        
        return {
            "symbol": symbol,
            "history": [c.to_dict() for c in history],
            "current": current.to_dict() if current else None,
            "count": len(history)
        }
    
    @app.get("/candles", tags=["Candles"])
    async def get_all_candles(
        limit: int = Query(default=10, ge=1, le=100)
    ) -> Dict[str, Any]:
        """
        Get recent candles for all symbols.
        
        Args:
            limit: Number of candles per symbol (default: 10)
        """
        if not _ohlc_aggregator:
            raise HTTPException(status_code=500, detail="Aggregator not available")
        
        result = {}
        for symbol in _ohlc_aggregator.get_symbols():
            history = _ohlc_aggregator.get_history(symbol, limit)
            current = _ohlc_aggregator.get_current_candle(symbol)
            result[symbol] = {
                "history": [c.to_dict() for c in history],
                "current": current.to_dict() if current else None
            }
        
        return result
    
    # Position endpoints
    @app.get("/positions", tags=["Positions"])
    async def get_all_positions() -> Dict[str, Any]:
        """Get all current positions across symbols and variants."""
        if not _strategy_manager:
            raise HTTPException(status_code=500, detail="Strategy manager not available")
        
        return _strategy_manager.get_status()
    
    @app.get("/positions/{symbol}", tags=["Positions"])
    async def get_symbol_positions(symbol: str) -> Dict[str, Any]:
        """
        Get positions for a specific symbol.
        
        Args:
            symbol: Trading symbol
        """
        if not _strategy_manager:
            raise HTTPException(status_code=500, detail="Strategy manager not available")
        
        symbol = symbol.upper()
        positions = {}
        
        for variant in _strategy_manager.get_variants():
            position = _strategy_manager.get_position(symbol, variant.name)
            if position:
                strategy = _strategy_manager.get_strategy(symbol, variant.name)
                positions[variant.name] = {
                    "position": position.to_dict(),
                    "variant": variant.to_dict(),
                    "indicators": strategy.get_indicators() if strategy else None
                }
        
        return {"symbol": symbol, "positions": positions}
    
    # Trade history endpoints
    @app.get("/trades", tags=["Trades"])
    async def get_trades(
        symbol: Optional[str] = None,
        variant: Optional[str] = None,
        limit: int = Query(default=50, ge=1, le=500)
    ) -> Dict[str, Any]:
        """
        Get trade history.
        
        Args:
            symbol: Filter by symbol (optional)
            variant: Filter by variant (optional)
            limit: Maximum trades to return
        """
        if not _trade_logger:
            raise HTTPException(status_code=500, detail="Trade logger not available")
        
        trades = _trade_logger.get_trades(
            symbol=symbol.upper() if symbol else None,
            variant=variant,
            limit=limit
        )
        
        summary = _trade_logger.get_summary(
            symbol=symbol.upper() if symbol else None,
            variant=variant
        )
        
        return {
            "trades": trades,
            "summary": summary,
            "count": len(trades)
        }
    
    # Latest tick endpoints
    @app.get("/ticks", tags=["Ticks"])
    async def get_latest_ticks() -> Dict[str, Any]:
        """Get latest tick for all symbols."""
        if not _tick_store:
            raise HTTPException(status_code=500, detail="Tick store not available")
        
        ticks = _tick_store.get_all()
        return {
            symbol: tick.to_dict() for symbol, tick in ticks.items()
        }
    
    @app.get("/ticks/{symbol}", tags=["Ticks"])
    async def get_symbol_tick(symbol: str) -> Dict[str, Any]:
        """
        Get latest tick for a symbol.
        
        Args:
            symbol: Trading symbol
        """
        if not _tick_store:
            raise HTTPException(status_code=500, detail="Tick store not available")
        
        tick = _tick_store.get(symbol.upper())
        if not tick:
            raise HTTPException(status_code=404, detail=f"No tick data for {symbol}")
        
        return tick.to_dict()
    
    # Strategy info endpoint
    @app.get("/strategy", tags=["Strategy"])
    async def get_strategy_info() -> Dict[str, Any]:
        """Get strategy configuration and variant information."""
        if not _strategy_manager:
            raise HTTPException(status_code=500, detail="Strategy manager not available")
        
        return {
            "type": "SMA/EMA Crossover",
            "parameters": {
                "sma_period": _strategy_manager.sma_period,
                "ema_period": _strategy_manager.ema_period
            },
            "variants": [v.to_dict() for v in _strategy_manager.get_variants()],
            "signals": {
                "BUY": "EMA crosses above SMA (bullish crossover)",
                "SELL": "EMA crosses below SMA (bearish crossover) OR Stop Loss triggered"
            }
        }
    
    # Manual trading endpoint - using app.state for reliable access
    logger.info(f"Trade endpoint setup: trade_logger={app.state.trade_logger}")
    
    @app.post("/trade", tags=["Trading"])
    async def place_manual_trade(
        request: Request,
        symbol: str,
        side: str,
        variant: str,
        quantity: float = 0.001
    ) -> Dict[str, Any]:
        """
        Place a manual trade for testing/demonstration.
        
        Args:
            symbol: Trading symbol (BTCUSDT, ETHUSDT)
            side: BUY or SELL
            variant: Strategy variant (A or B)
            quantity: Trade quantity
        """
        from datetime import datetime
        import random
        
        # Get references from app.state
        tl = request.app.state.trade_logger
        ts = request.app.state.tick_store
        sm = request.app.state.strategy_manager
        
        # Check for None explicitly (TradeLogger has __len__ which makes 'not tl' fail when empty)
        if tl is None:
            raise HTTPException(status_code=500, detail="Trade logger not available")
        
        if ts is None:
            raise HTTPException(status_code=500, detail="Tick store not available")
        
        symbol = symbol.upper()
        side = side.upper()
        variant = variant.upper()
        
        if side not in ["BUY", "SELL"]:
            raise HTTPException(status_code=400, detail="Side must be BUY or SELL")
        
        if variant not in ["A", "B"]:
            raise HTTPException(status_code=400, detail="Variant must be A or B")
        
        # Get current price from tick store
        tick = ts.get(symbol)
        if not tick:
            raise HTTPException(status_code=404, detail=f"No price data for {symbol}")
        
        price = tick.price
        
        # Calculate P&L for SELL orders (simulated)
        pnl = None
        if side == "SELL":
            # Simulate a small profit/loss for demo
            pnl = random.uniform(-0.05, 0.15) * price * quantity
        
        # Log the trade
        trade = tl.log_trade(
            symbol=symbol,
            side=side,
            size=quantity,
            price=price,
            variant=variant,
            order_id=f"MANUAL-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            status="FILLED",
            pnl=pnl,
            notes=f"Manual {side} order via dashboard"
        )
        
        # Update position state if strategy manager available
        if sm:
            if side == "BUY":
                sm.enter_position(
                    symbol=symbol,
                    variant_name=variant,
                    price=price,
                    quantity=quantity,
                    timestamp=datetime.utcnow()
                )
            else:
                sm.exit_position(
                    symbol=symbol,
                    variant_name=variant,
                    price=price
                )
        
        logger.info(f"Manual trade executed: {side} {quantity} {symbol} @ {price:.2f} (Variant {variant})")
        
        return {
            "success": True,
            "trade": trade,
            "message": f"Manual {side} order executed successfully"
        }
    
    logger.info("REST API created and configured")
    
    # Determine frontend directory path
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
    
    # =========================================================================
    # WebSocket endpoint for real-time updates (integrated with FastAPI)
    # =========================================================================
    
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """
        WebSocket endpoint for real-time candle and signal updates.
        
        This endpoint integrates with the WebSocketServer for broadcasting.
        """
        if _ws_server:
            await _ws_server.handle_fastapi_websocket(websocket)
        else:
            # Fallback: simple echo/disconnect if no ws_server
            await websocket.accept()
            await websocket.send_json({
                "type": "error",
                "message": "WebSocket server not configured"
            })
            await websocket.close()
    
    # =========================================================================
    # Frontend static file serving
    # =========================================================================
    
    @app.get("/", response_class=FileResponse, include_in_schema=False)
    async def serve_index():
        """Serve the main dashboard page."""
        index_path = os.path.join(frontend_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path, media_type="text/html")
        return {"error": "index.html not found"}
    
    @app.get("/analytics.html", response_class=FileResponse, include_in_schema=False)
    async def serve_analytics():
        """Serve the analytics page."""
        analytics_path = os.path.join(frontend_dir, "analytics.html")
        if os.path.exists(analytics_path):
            return FileResponse(analytics_path, media_type="text/html")
        return {"error": "analytics.html not found"}
    
    # Mount static files (CSS, JS) - must be after explicit routes
    if os.path.exists(frontend_dir):
        app.mount("/", StaticFiles(directory=frontend_dir, html=False), name="static")
        logger.info(f"Frontend static files mounted from {frontend_dir}")
    
    return app


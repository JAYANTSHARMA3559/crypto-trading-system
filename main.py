"""
Live Crypto Trading System - Main Application.

This is the main entry point for the crypto trading system. It initializes
all components and starts the data streaming, strategy execution, and API servers.

Components:
- BinanceStreamClient: WebSocket connection to Binance Testnet
- TickStore: In-memory storage for latest ticks
- OHLCAggregator: Builds 1-minute OHLC candles from ticks
- StrategyManager: Runs SMA/EMA strategies with two variants (A/B)
- OrderExecutor: Executes trades on Binance Testnet
- REST API: FastAPI server for data access
- WebSocket Server: Real-time candle/signal broadcasting
"""

import asyncio
import signal
import sys
import logging
from typing import Optional

import uvicorn
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from config import get_settings
from data_ingestion.binance_stream_client import BinanceStreamClient
from data_ingestion.tick_store import TickStore
from aggregation.ohlc_aggregator import OHLCAggregator
from strategy.strategy_manager import StrategyManager
from execution.order_executor import OrderExecutor
from execution.binance_order_client import BinanceOrderClient
from execution.trade_logger import TradeLogger
from api.rest_api import create_app
from api.websocket_server import WebSocketServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class CryptoTradingSystem:
    """
    Main application class for the Crypto Trading System.
    
    Coordinates all components and manages the application lifecycle.
    """
    
    def __init__(self):
        """Initialize the trading system components."""
        self.settings = get_settings()
        
        # Core components
        self.tick_store = TickStore()
        self.ohlc_aggregator = OHLCAggregator()
        self.strategy_manager = StrategyManager()
        self.trade_logger = TradeLogger()
        self.order_client = BinanceOrderClient()
        self.order_executor = OrderExecutor(
            strategy_manager=self.strategy_manager,
            order_client=self.order_client,
            trade_logger=self.trade_logger
        )
        
        # Data streaming
        self.stream_client = BinanceStreamClient(
            tick_store=self.tick_store,
            symbols=self.settings.symbols
        )
        
        # API servers
        self.ws_server = WebSocketServer(
            host=self.settings.api_host,
            port=self.settings.api_port + 1  # WebSocket on port+1
        )
        
        # Create FastAPI app
        self.app = create_app(
            ohlc_aggregator=self.ohlc_aggregator,
            strategy_manager=self.strategy_manager,
            trade_logger=self.trade_logger,
            tick_store=self.tick_store,
            ws_server=self.ws_server,
            add_symbol_callback=self._add_symbol,
            remove_symbol_callback=self._remove_symbol
        )
        
        # Wire up callbacks
        self._setup_callbacks()
        
        # Shutdown flag
        self._shutdown = False
        
        logger.info("Crypto Trading System initialized")
    
    def _setup_callbacks(self):
        """Set up callbacks between components."""
        # Tick -> OHLC Aggregator
        self.stream_client.add_tick_callback(self.ohlc_aggregator.process_tick)
        
        # Candle -> Strategy Manager
        self.ohlc_aggregator.add_candle_callback(self._on_candle)
        
        # Candle -> WebSocket broadcast
        self.ohlc_aggregator.add_candle_callback(self.ws_server.on_candle)
        
        # Signal -> Order Executor
        self.strategy_manager.add_signal_callback(self.order_executor.on_signal)
        
        # Signal -> WebSocket broadcast
        self.strategy_manager.add_signal_callback(self.ws_server.on_signal)
    
    def _on_candle(self, candle):
        """Handle new closed candle."""
        # Forward to strategy manager
        signals = self.strategy_manager.on_candle(candle)
        
        for symbol, variant, sig in signals:
            logger.info(f"Signal generated: {symbol} {variant} -> {sig.value}")
    
    async def _add_symbol(self, symbol: str):
        """Add a new symbol to track."""
        await self.stream_client.subscribe(symbol)
    
    async def _remove_symbol(self, symbol: str):
        """Remove a symbol from tracking."""
        await self.stream_client.unsubscribe(symbol)
    
    async def start(self):
        """Start all system components."""
        logger.info("=" * 60)
        logger.info("Starting Live Crypto Trading System")
        logger.info("=" * 60)
        
        # Log configuration
        logger.info(f"Symbols: {', '.join(self.settings.symbols)}")
        logger.info(f"Strategy: SMA({self.settings.sma_period})/EMA({self.settings.ema_period}) Crossover")
        logger.info(f"Variant A SL: {self.settings.variant_a_sl*100:.0f}%")
        logger.info(f"Variant B SL: {self.settings.variant_b_sl*100:.0f}%")
        logger.info(f"REST API: http://{self.settings.api_host}:{self.settings.api_port}")
        logger.info(f"WebSocket: ws://{self.settings.api_host}:{self.settings.api_port + 1}")
        logger.info("=" * 60)
        
        # Check API credentials
        if not self.settings.binance_api_key or not self.settings.binance_api_secret:
            logger.warning(
                "Binance API credentials not configured! "
                "Orders will NOT be executed. "
                "Set BINANCE_API_KEY and BINANCE_API_SECRET in .env file."
            )
        else:
            # Test connectivity
            connected = await self.order_client.test_connectivity()
            if connected:
                logger.info("Binance Testnet REST API: Connected")
            else:
                logger.warning("Binance Testnet REST API: Connection failed")
        
        # Start components
        await self.ohlc_aggregator.start()
        await self.ws_server.start()
        
        # Start Binance stream in background task
        stream_task = asyncio.create_task(self.stream_client.start())
        
        # Start REST API server
        config = uvicorn.Config(
            app=self.app,
            host=self.settings.api_host,
            port=self.settings.api_port,
            log_level="info",
            access_log=False
        )
        server = uvicorn.Server(config)
        api_task = asyncio.create_task(server.serve())
        
        logger.info("System started successfully!")
        logger.info("Press Ctrl+C to stop")
        
        # Wait for shutdown
        try:
            while not self._shutdown:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        
        # Cleanup
        await self.stop()
        
        # Cancel tasks
        stream_task.cancel()
        api_task.cancel()
        
        try:
            await stream_task
        except asyncio.CancelledError:
            pass
        
        try:
            await api_task
        except asyncio.CancelledError:
            pass
    
    async def stop(self):
        """Stop all system components."""
        logger.info("Shutting down...")
        
        await self.stream_client.stop()
        await self.ohlc_aggregator.stop()
        await self.ws_server.stop()
        await self.order_executor.close()
        
        logger.info("Shutdown complete")
    
    def shutdown(self):
        """Signal shutdown."""
        self._shutdown = True


def main():
    """Main entry point."""
    system = CryptoTradingSystem()
    
    # Handle signals
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}")
        system.shutdown()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the system
    try:
        asyncio.run(system.start())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

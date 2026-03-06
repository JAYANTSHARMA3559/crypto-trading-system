"""
Order Executor for Strategy Signal Execution.

This module coordinates order execution based on strategy signals,
managing position entry/exit and trade logging.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from strategy.base_strategy import Signal
from strategy.strategy_manager import StrategyManager
from execution.binance_order_client import BinanceOrderClient
from execution.trade_logger import TradeLogger
from config import get_settings

logger = logging.getLogger(__name__)


class OrderExecutor:
    """
    Executes orders based on strategy signals.
    
    Receives signals from the strategy manager, places orders via
    the Binance client, and logs all trades.
    
    Attributes:
        strategy_manager: Strategy manager instance
        order_client: Binance order client
        trade_logger: Trade logger for persistence
    """
    
    def __init__(
        self,
        strategy_manager: StrategyManager,
        order_client: Optional[BinanceOrderClient] = None,
        trade_logger: Optional[TradeLogger] = None
    ):
        """
        Initialize the order executor.
        
        Args:
            strategy_manager: Strategy manager for position tracking
            order_client: Binance order client (creates new if not provided)
            trade_logger: Trade logger (creates new if not provided)
        """
        self.settings = get_settings()
        self.strategy_manager = strategy_manager
        self.order_client = order_client or BinanceOrderClient()
        self.trade_logger = trade_logger or TradeLogger()
        
        # Order sizes for different base currencies
        self._order_sizes: Dict[str, float] = {
            "BTC": self.settings.order_size_btc,
            "ETH": self.settings.order_size_eth
        }
        
        # Track pending orders to avoid duplicate execution
        self._pending_orders: Dict[str, bool] = {}
        
        logger.info("Order executor initialized")
    
    def _get_order_size(self, symbol: str) -> float:
        """
        Get the order size for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Order size based on base currency
        """
        symbol = symbol.upper()
        
        # Determine base currency from symbol
        if symbol.startswith("BTC"):
            return self._order_sizes.get("BTC", 0.001)
        elif symbol.startswith("ETH"):
            return self._order_sizes.get("ETH", 0.01)
        else:
            # Default to small quantity for unknown pairs
            return 0.001
    
    async def execute_signal(
        self,
        symbol: str,
        variant: str,
        signal: Signal,
        price: float
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a trading signal.
        
        Args:
            symbol: Trading symbol
            variant: Strategy variant name
            signal: Trading signal (BUY/SELL)
            price: Current market price
            
        Returns:
            Order response if order was placed, None otherwise
        """
        symbol = symbol.upper()
        key = f"{symbol}_{variant}"
        
        # Prevent duplicate execution
        if self._pending_orders.get(key):
            logger.warning(f"Order already pending for {key}")
            return None
        
        try:
            self._pending_orders[key] = True
            
            position = self.strategy_manager.get_position(symbol, variant)
            
            if signal == Signal.BUY:
                return await self._execute_buy(symbol, variant, price, position)
            
            elif signal == Signal.SELL:
                return await self._execute_sell(symbol, variant, price, position)
            
            return None
            
        finally:
            self._pending_orders[key] = False
    
    async def _execute_buy(
        self,
        symbol: str,
        variant: str,
        price: float,
        position
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a BUY signal.
        
        Args:
            symbol: Trading symbol
            variant: Strategy variant
            price: Current price
            position: Current position state
            
        Returns:
            Order response if successful
        """
        # Don't buy if already in position
        if position and position.side == "LONG":
            logger.info(f"Already in LONG position for {symbol} variant {variant}")
            return None
        
        quantity = self._get_order_size(symbol)
        
        logger.info(
            f"Executing BUY for {symbol} variant {variant}: "
            f"qty={quantity}, price={price:.2f}"
        )
        
        # Place market order
        response = await self.order_client.place_market_order(
            symbol=symbol,
            side="BUY",
            quantity=quantity
        )
        
        if "orderId" in response:
            # Get fill price (use average if available, otherwise use input price)
            fill_price = float(response.get("fills", [{}])[0].get("price", price)) if response.get("fills") else price
            
            # Update strategy position
            self.strategy_manager.enter_position(
                symbol=symbol,
                variant_name=variant,
                price=fill_price,
                quantity=quantity,
                timestamp=datetime.utcnow()
            )
            
            # Log trade
            self.trade_logger.log_trade(
                symbol=symbol,
                side="BUY",
                size=quantity,
                price=fill_price,
                variant=variant,
                order_id=str(response["orderId"]),
                status=response.get("status", "FILLED"),
                notes=f"SMA/EMA crossover entry"
            )
            
            logger.info(
                f"BUY executed for {symbol} variant {variant}: "
                f"OrderID={response['orderId']}, Price={fill_price:.2f}"
            )
        else:
            logger.error(f"BUY order failed: {response}")
        
        return response
    
    async def _execute_sell(
        self,
        symbol: str,
        variant: str,
        price: float,
        position
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a SELL signal.
        
        Args:
            symbol: Trading symbol
            variant: Strategy variant
            price: Current price
            position: Current position state
            
        Returns:
            Order response if successful
        """
        # Don't sell if not in position
        if not position or position.side != "LONG":
            logger.info(f"No LONG position to close for {symbol} variant {variant}")
            return None
        
        quantity = position.quantity
        
        logger.info(
            f"Executing SELL for {symbol} variant {variant}: "
            f"qty={quantity}, price={price:.2f}"
        )
        
        # Place market order
        response = await self.order_client.place_market_order(
            symbol=symbol,
            side="SELL",
            quantity=quantity
        )
        
        if "orderId" in response:
            # Get fill price
            fill_price = float(response.get("fills", [{}])[0].get("price", price)) if response.get("fills") else price
            
            # Exit position and get P&L
            pnl = self.strategy_manager.exit_position(
                symbol=symbol,
                variant_name=variant,
                price=fill_price
            )
            
            # Determine exit reason
            exit_reason = "SMA/EMA crossover exit"
            if position.is_stop_loss_triggered():
                exit_reason = "Stop Loss triggered"
            
            # Log trade
            self.trade_logger.log_trade(
                symbol=symbol,
                side="SELL",
                size=quantity,
                price=fill_price,
                variant=variant,
                order_id=str(response["orderId"]),
                status=response.get("status", "FILLED"),
                pnl=pnl,
                notes=exit_reason
            )
            
            logger.info(
                f"SELL executed for {symbol} variant {variant}: "
                f"OrderID={response['orderId']}, Price={fill_price:.2f}, P&L={pnl:.4f}"
            )
        else:
            logger.error(f"SELL order failed: {response}")
        
        return response
    
    def on_signal(
        self,
        symbol: str,
        variant: str,
        signal: Signal,
        price: float
    ) -> None:
        """
        Callback for strategy signals (creates async task).
        
        Args:
            symbol: Trading symbol
            variant: Strategy variant
            signal: Trading signal
            price: Current price
        """
        if signal != Signal.HOLD:
            asyncio.create_task(
                self.execute_signal(symbol, variant, signal, price)
            )
    
    async def close(self) -> None:
        """Close the order executor and its clients."""
        await self.order_client.close()
        logger.info("Order executor closed")
    
    def get_trade_history(
        self,
        symbol: Optional[str] = None,
        variant: Optional[str] = None,
        limit: Optional[int] = None
    ) -> list:
        """
        Get trade history.
        
        Args:
            symbol: Filter by symbol
            variant: Filter by variant
            limit: Maximum trades to return
            
        Returns:
            List of trade records
        """
        return self.trade_logger.get_trades(
            symbol=symbol,
            variant=variant,
            limit=limit
        )
    
    def get_trade_summary(
        self,
        symbol: Optional[str] = None,
        variant: Optional[str] = None
    ) -> dict:
        """
        Get trade summary statistics.
        
        Args:
            symbol: Filter by symbol
            variant: Filter by variant
            
        Returns:
            Summary statistics
        """
        return self.trade_logger.get_summary(
            symbol=symbol,
            variant=variant
        )

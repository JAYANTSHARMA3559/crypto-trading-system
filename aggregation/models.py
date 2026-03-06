"""
Data Models for OHLC Aggregation.

This module defines the core data structures used throughout the trading system
for representing market data ticks and OHLC candles.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import json


@dataclass
class Tick:
    """
    Represents a single trade/tick from the market.
    
    Attributes:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        price: Trade price
        quantity: Trade quantity
        timestamp: UTC timestamp of the trade
        trade_id: Unique trade identifier from exchange
    """
    symbol: str
    price: float
    quantity: float
    timestamp: datetime
    trade_id: Optional[int] = None
    
    def to_dict(self) -> dict:
        """Convert tick to dictionary for JSON serialization."""
        return {
            "symbol": self.symbol,
            "price": self.price,
            "quantity": self.quantity,
            "timestamp": self.timestamp.isoformat(),
            "trade_id": self.trade_id
        }
    
    @classmethod
    def from_binance_message(cls, symbol: str, data: dict) -> "Tick":
        """
        Create a Tick from a Binance WebSocket trade message.
        
        Args:
            symbol: The trading symbol
            data: Raw message data from Binance WebSocket
            
        Returns:
            Tick instance
        """
        # Binance trade message format:
        # {
        #   "e": "trade",
        #   "E": 123456789,  # Event time
        #   "s": "BTCUSDT",  # Symbol
        #   "t": 12345,      # Trade ID
        #   "p": "0.001",    # Price
        #   "q": "100",      # Quantity
        #   "T": 123456785,  # Trade time
        #   ...
        # }
        return cls(
            symbol=symbol.upper(),
            price=float(data.get("p", 0)),
            quantity=float(data.get("q", 0)),
            timestamp=datetime.utcfromtimestamp(data.get("T", 0) / 1000),
            trade_id=data.get("t")
        )


@dataclass
class OHLCCandle:
    """
    Represents a 1-minute OHLC (Open, High, Low, Close) candle.
    
    Attributes:
        symbol: Trading pair symbol
        open: Opening price of the candle
        high: Highest price during the candle period
        low: Lowest price during the candle period
        close: Closing price of the candle
        timestamp: UTC timestamp of candle start (minute boundary)
        volume: Total traded volume (optional)
        tick_count: Number of ticks in this candle (optional)
        is_closed: Whether the candle is finalized
    """
    symbol: str
    open: float
    high: float
    low: float
    close: float
    timestamp: datetime
    volume: float = 0.0
    tick_count: int = 0
    is_closed: bool = False
    
    def to_dict(self) -> dict:
        """Convert candle to dictionary for JSON serialization."""
        return {
            "symbol": self.symbol,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "timestamp": self.timestamp.isoformat(),
            "volume": self.volume,
            "tick_count": self.tick_count,
            "is_closed": self.is_closed
        }
    
    def to_json(self) -> str:
        """Convert candle to JSON string."""
        return json.dumps(self.to_dict())
    
    def update(self, tick: Tick) -> None:
        """
        Update the candle with a new tick.
        
        Args:
            tick: New tick to incorporate into the candle
        """
        if not self.is_closed:
            self.high = max(self.high, tick.price)
            self.low = min(self.low, tick.price)
            self.close = tick.price
            self.volume += tick.quantity
            self.tick_count += 1
    
    @classmethod
    def from_tick(cls, tick: Tick, candle_timestamp: datetime) -> "OHLCCandle":
        """
        Create a new candle from the first tick.
        
        Args:
            tick: The first tick of the candle
            candle_timestamp: The minute-boundary timestamp for this candle
            
        Returns:
            New OHLCCandle instance
        """
        return cls(
            symbol=tick.symbol,
            open=tick.price,
            high=tick.price,
            low=tick.price,
            close=tick.price,
            timestamp=candle_timestamp,
            volume=tick.quantity,
            tick_count=1,
            is_closed=False
        )

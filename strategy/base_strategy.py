"""
Base Strategy Interface for Trading Strategies.

This module defines the abstract base class and common types
for implementing trading strategies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, List

from aggregation.models import OHLCCandle


class Signal(Enum):
    """Trading signal types."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Position:
    """
    Represents a trading position.
    
    Attributes:
        symbol: Trading symbol
        side: Position side ('LONG' or 'FLAT')
        entry_price: Price at which position was entered
        entry_time: Timestamp of position entry
        quantity: Position size
        current_price: Current market price
        unrealized_pnl: Unrealized profit/loss
        stop_loss_price: Stop loss trigger price
    """
    symbol: str
    side: str  # 'LONG' or 'FLAT'
    entry_price: float = 0.0
    entry_time: Optional[datetime] = None
    quantity: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    stop_loss_price: float = 0.0
    realized_pnl: float = 0.0
    
    def update_price(self, price: float) -> None:
        """
        Update position with current market price.
        
        Args:
            price: Current market price
        """
        self.current_price = price
        if self.side == "LONG" and self.entry_price > 0:
            self.unrealized_pnl = (price - self.entry_price) * self.quantity
    
    def is_stop_loss_triggered(self) -> bool:
        """
        Check if stop loss has been triggered.
        
        Returns:
            True if stop loss is triggered
        """
        if self.side == "LONG" and self.current_price > 0 and self.stop_loss_price > 0:
            return self.current_price <= self.stop_loss_price
        return False
    
    def to_dict(self) -> dict:
        """Convert position to dictionary."""
        return {
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "quantity": self.quantity,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "stop_loss_price": self.stop_loss_price
        }


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.
    
    All trading strategies must inherit from this class and implement
    the required methods.
    """
    
    def __init__(self, symbol: str, stop_loss_pct: float = 0.10):
        """
        Initialize the strategy.
        
        Args:
            symbol: Trading symbol for this strategy
            stop_loss_pct: Stop loss percentage (e.g., 0.10 for 10%)
        """
        self.symbol = symbol.upper()
        self.stop_loss_pct = stop_loss_pct
        self.position = Position(symbol=self.symbol, side="FLAT")
        self.candle_history: List[OHLCCandle] = []
    
    @abstractmethod
    def calculate_signal(self, candles: List[OHLCCandle]) -> Signal:
        """
        Calculate trading signal based on candle data.
        
        Args:
            candles: List of OHLC candles (oldest to newest)
            
        Returns:
            Trading signal (BUY, SELL, or HOLD)
        """
        pass
    
    @abstractmethod
    def get_required_candles(self) -> int:
        """
        Get the minimum number of candles required to calculate signals.
        
        Returns:
            Number of candles needed
        """
        pass
    
    def on_candle(self, candle: OHLCCandle) -> Optional[Signal]:
        """
        Process a new closed candle.
        
        Args:
            candle: The new closed candle
            
        Returns:
            Signal if action should be taken, None otherwise
        """
        if candle.symbol.upper() != self.symbol:
            return None
        
        # Add candle to history
        self.candle_history.append(candle)
        
        # Trim history to required size + buffer
        max_history = self.get_required_candles() * 2
        if len(self.candle_history) > max_history:
            self.candle_history = self.candle_history[-max_history:]
        
        # Update position with current price
        self.position.update_price(candle.close)
        
        # Check for stop loss
        if self.position.is_stop_loss_triggered():
            return Signal.SELL
        
        # Calculate signal if we have enough candles
        if len(self.candle_history) >= self.get_required_candles():
            return self.calculate_signal(self.candle_history)
        
        return Signal.HOLD
    
    def enter_position(self, price: float, quantity: float, timestamp: datetime) -> None:
        """
        Enter a long position.
        
        Args:
            price: Entry price
            quantity: Position size
            timestamp: Entry timestamp
        """
        self.position.side = "LONG"
        self.position.entry_price = price
        self.position.entry_time = timestamp
        self.position.quantity = quantity
        self.position.current_price = price
        self.position.unrealized_pnl = 0.0
        self.position.stop_loss_price = price * (1 - self.stop_loss_pct)
    
    def exit_position(self, price: float) -> float:
        """
        Exit the current position.
        
        Args:
            price: Exit price
            
        Returns:
            Realized P&L from the trade
        """
        if self.position.side == "LONG":
            pnl = (price - self.position.entry_price) * self.position.quantity
            self.position.realized_pnl += pnl
        else:
            pnl = 0.0
        
        self.position.side = "FLAT"
        self.position.entry_price = 0.0
        self.position.entry_time = None
        self.position.quantity = 0.0
        self.position.unrealized_pnl = 0.0
        self.position.stop_loss_price = 0.0
        
        return pnl
    
    def get_position(self) -> Position:
        """Get the current position state."""
        return self.position
    
    def is_in_position(self) -> bool:
        """Check if currently in a position."""
        return self.position.side == "LONG"

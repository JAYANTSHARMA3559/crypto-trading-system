"""
Strategy Manager for Multiple Strategy Variants.

This module manages multiple strategy variants (e.g., different stop-loss levels)
and coordinates their execution across symbols.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Callable, Tuple
import logging

from aggregation.models import OHLCCandle
from strategy.base_strategy import BaseStrategy, Signal, Position
from strategy.sma_ema_strategy import SMAEMAStrategy
from config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class StrategyVariant:
    """
    Represents a strategy variant with specific parameters.
    
    Attributes:
        name: Variant name (e.g., 'A', 'B')
        stop_loss_pct: Stop loss percentage for this variant
        description: Human-readable description
    """
    name: str
    stop_loss_pct: float
    description: str
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "stop_loss_pct": self.stop_loss_pct,
            "description": self.description
        }


class StrategyManager:
    """
    Manages multiple strategy variants across multiple symbols.
    
    Creates and coordinates strategy instances for each symbol-variant combination,
    processes candles, and emits signals for order execution.
    
    Attributes:
        variants: List of strategy variants
        strategies: Dict mapping (symbol, variant_name) to strategy instance
        _signal_callbacks: Callbacks to notify on signal generation
    """
    
    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        sma_period: Optional[int] = None,
        ema_period: Optional[int] = None
    ):
        """
        Initialize the strategy manager.
        
        Creates two variants:
        - Variant A: Tighter stop loss (15%)
        - Variant B: Looser stop loss (10%)
        
        Args:
            symbols: List of symbols to create strategies for
            sma_period: SMA period (uses config default if not specified)
            ema_period: EMA period (uses config default if not specified)
        """
        self.settings = get_settings()
        
        self.sma_period = sma_period or self.settings.sma_period
        self.ema_period = ema_period or self.settings.ema_period
        
        # Define strategy variants
        self.variants: List[StrategyVariant] = [
            StrategyVariant(
                name="A",
                stop_loss_pct=self.settings.variant_a_sl,
                description=f"Tighter SL ({self.settings.variant_a_sl*100:.0f}%) - Exits faster on loss"
            ),
            StrategyVariant(
                name="B",
                stop_loss_pct=self.settings.variant_b_sl,
                description=f"Looser SL ({self.settings.variant_b_sl*100:.0f}%) - Allows more drawdown"
            )
        ]
        
        # Create strategies for each symbol-variant combination
        # Key: (symbol, variant_name) -> Strategy
        self.strategies: Dict[Tuple[str, str], SMAEMAStrategy] = {}
        
        symbols = symbols or self.settings.symbols
        for symbol in symbols:
            self._create_strategies_for_symbol(symbol)
        
        # Signal callbacks
        self._signal_callbacks: List[Callable[[str, str, Signal, float], None]] = []
        
        logger.info(
            f"Strategy Manager initialized with {len(symbols)} symbols "
            f"and {len(self.variants)} variants"
        )
    
    def _create_strategies_for_symbol(self, symbol: str) -> None:
        """
        Create strategy instances for all variants for a symbol.
        
        Args:
            symbol: Trading symbol
        """
        symbol = symbol.upper()
        for variant in self.variants:
            key = (symbol, variant.name)
            self.strategies[key] = SMAEMAStrategy(
                symbol=symbol,
                sma_period=self.sma_period,
                ema_period=self.ema_period,
                stop_loss_pct=variant.stop_loss_pct
            )
            logger.info(f"Created strategy for {symbol} variant {variant.name}")
    
    def add_symbol(self, symbol: str) -> None:
        """
        Add a new symbol to track.
        
        Args:
            symbol: Trading symbol to add
        """
        symbol = symbol.upper()
        if any(s == symbol for s, _ in self.strategies.keys()):
            logger.warning(f"Symbol {symbol} already exists")
            return
        
        self._create_strategies_for_symbol(symbol)
        logger.info(f"Added symbol {symbol}")
    
    def remove_symbol(self, symbol: str) -> None:
        """
        Remove a symbol from tracking.
        
        Args:
            symbol: Trading symbol to remove
        """
        symbol = symbol.upper()
        keys_to_remove = [k for k in self.strategies.keys() if k[0] == symbol]
        
        for key in keys_to_remove:
            del self.strategies[key]
        
        logger.info(f"Removed symbol {symbol}")
    
    def add_signal_callback(
        self, 
        callback: Callable[[str, str, Signal, float], None]
    ) -> None:
        """
        Add a callback for signal notifications.
        
        Args:
            callback: Function(symbol, variant_name, signal, price) to call on signal
        """
        self._signal_callbacks.append(callback)
    
    def remove_signal_callback(
        self, 
        callback: Callable[[str, str, Signal, float], None]
    ) -> None:
        """
        Remove a signal callback.
        
        Args:
            callback: Function to remove
        """
        if callback in self._signal_callbacks:
            self._signal_callbacks.remove(callback)
    
    def on_candle(self, candle: OHLCCandle) -> List[Tuple[str, str, Signal]]:
        """
        Process a new candle across all strategy variants.
        
        Args:
            candle: New closed OHLC candle
            
        Returns:
            List of (symbol, variant_name, signal) tuples for actionable signals
        """
        signals = []
        symbol = candle.symbol.upper()
        
        for variant in self.variants:
            key = (symbol, variant.name)
            strategy = self.strategies.get(key)
            
            if strategy:
                signal = strategy.on_candle(candle)
                
                if signal and signal != Signal.HOLD:
                    signals.append((symbol, variant.name, signal))
                    
                    # Notify callbacks
                    for callback in self._signal_callbacks:
                        try:
                            callback(symbol, variant.name, signal, candle.close)
                        except Exception as e:
                            logger.error(f"Error in signal callback: {e}")
        
        return signals
    
    def enter_position(
        self, 
        symbol: str, 
        variant_name: str, 
        price: float, 
        quantity: float,
        timestamp: Optional[datetime] = None
    ) -> None:
        """
        Enter a position for a specific symbol-variant.
        
        Args:
            symbol: Trading symbol
            variant_name: Strategy variant name
            price: Entry price
            quantity: Position size
            timestamp: Entry timestamp (defaults to now)
        """
        key = (symbol.upper(), variant_name)
        strategy = self.strategies.get(key)
        
        if strategy:
            strategy.enter_position(
                price=price,
                quantity=quantity,
                timestamp=timestamp or datetime.utcnow()
            )
            logger.info(
                f"Entered position for {symbol} variant {variant_name}: "
                f"price={price:.2f}, qty={quantity}"
            )
    
    def exit_position(self, symbol: str, variant_name: str, price: float) -> float:
        """
        Exit a position for a specific symbol-variant.
        
        Args:
            symbol: Trading symbol
            variant_name: Strategy variant name
            price: Exit price
            
        Returns:
            Realized P&L from the trade
        """
        key = (symbol.upper(), variant_name)
        strategy = self.strategies.get(key)
        
        if strategy:
            pnl = strategy.exit_position(price)
            logger.info(
                f"Exited position for {symbol} variant {variant_name}: "
                f"price={price:.2f}, P&L={pnl:.4f}"
            )
            return pnl
        
        return 0.0
    
    def get_position(self, symbol: str, variant_name: str) -> Optional[Position]:
        """
        Get position state for a specific symbol-variant.
        
        Args:
            symbol: Trading symbol
            variant_name: Strategy variant name
            
        Returns:
            Position object or None
        """
        key = (symbol.upper(), variant_name)
        strategy = self.strategies.get(key)
        return strategy.get_position() if strategy else None
    
    def get_all_positions(self) -> Dict[str, Dict[str, Position]]:
        """
        Get all position states.
        
        Returns:
            Nested dict: {symbol: {variant_name: Position}}
        """
        positions: Dict[str, Dict[str, Position]] = {}
        
        for (symbol, variant_name), strategy in self.strategies.items():
            if symbol not in positions:
                positions[symbol] = {}
            positions[symbol][variant_name] = strategy.get_position()
        
        return positions
    
    def get_strategy(self, symbol: str, variant_name: str) -> Optional[SMAEMAStrategy]:
        """
        Get a specific strategy instance.
        
        Args:
            symbol: Trading symbol
            variant_name: Strategy variant name
            
        Returns:
            Strategy instance or None
        """
        return self.strategies.get((symbol.upper(), variant_name))
    
    def get_symbols(self) -> List[str]:
        """
        Get list of tracked symbols.
        
        Returns:
            List of symbol names
        """
        return list(set(s for s, _ in self.strategies.keys()))
    
    def get_variants(self) -> List[StrategyVariant]:
        """
        Get list of strategy variants.
        
        Returns:
            List of StrategyVariant objects
        """
        return self.variants
    
    def get_status(self) -> dict:
        """
        Get comprehensive status of all strategies.
        
        Returns:
            Status dictionary with all positions and indicators
        """
        status = {
            "symbols": self.get_symbols(),
            "variants": [v.to_dict() for v in self.variants],
            "positions": {},
            "parameters": {
                "sma_period": self.sma_period,
                "ema_period": self.ema_period
            }
        }
        
        for (symbol, variant_name), strategy in self.strategies.items():
            if symbol not in status["positions"]:
                status["positions"][symbol] = {}
            
            status["positions"][symbol][variant_name] = {
                "position": strategy.get_position().to_dict(),
                "indicators": strategy.get_indicators()
            }
        
        return status

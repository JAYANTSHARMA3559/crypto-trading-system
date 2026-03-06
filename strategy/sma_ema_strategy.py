"""
SMA/EMA Crossover Trading Strategy.

This module implements a Simple Moving Average / Exponential Moving Average
crossover strategy for generating trading signals.

Strategy Logic:
- Calculate SMA (Simple Moving Average) over N periods
- Calculate EMA (Exponential Moving Average) over M periods  
- BUY signal when EMA crosses above SMA (bullish crossover)
- SELL signal when EMA crosses below SMA (bearish crossover)
"""

from typing import List, Optional
import logging

from aggregation.models import OHLCCandle
from strategy.base_strategy import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class SMAEMAStrategy(BaseStrategy):
    """
    SMA/EMA Crossover Trading Strategy.
    
    Generates trading signals based on the crossover of Exponential Moving Average
    and Simple Moving Average. A bullish signal is generated when EMA crosses above
    SMA, and a bearish signal when EMA crosses below SMA.
    
    Attributes:
        sma_period: Period for Simple Moving Average calculation
        ema_period: Period for Exponential Moving Average calculation
        _prev_ema: Previous EMA value for crossover detection
        _prev_sma: Previous SMA value for crossover detection
    """
    
    def __init__(
        self, 
        symbol: str, 
        sma_period: int = 10, 
        ema_period: int = 5,
        stop_loss_pct: float = 0.10
    ):
        """
        Initialize the SMA/EMA crossover strategy.
        
        Args:
            symbol: Trading symbol
            sma_period: Period for SMA calculation (default: 10)
            ema_period: Period for EMA calculation (default: 5)
            stop_loss_pct: Stop loss percentage (default: 0.10 = 10%)
        """
        super().__init__(symbol, stop_loss_pct)
        
        if sma_period <= 0 or ema_period <= 0:
            raise ValueError("SMA and EMA periods must be positive integers")
        
        self.sma_period = sma_period
        self.ema_period = ema_period
        self._prev_ema: Optional[float] = None
        self._prev_sma: Optional[float] = None
        self._current_ema: Optional[float] = None
        self._current_sma: Optional[float] = None
        
        # EMA multiplier: 2 / (period + 1)
        self._ema_multiplier = 2 / (ema_period + 1)
        
        logger.info(
            f"Initialized SMA/EMA strategy for {symbol}: "
            f"SMA={sma_period}, EMA={ema_period}, SL={stop_loss_pct*100:.1f}%"
        )
    
    def get_required_candles(self) -> int:
        """
        Get minimum candles needed for strategy calculation.
        
        Returns:
            Maximum of SMA and EMA periods + 1 for crossover detection
        """
        return max(self.sma_period, self.ema_period) + 1
    
    def _calculate_sma(self, prices: List[float], period: int) -> float:
        """
        Calculate Simple Moving Average.
        
        SMA = Sum of last N prices / N
        
        Args:
            prices: List of prices
            period: Number of periods
            
        Returns:
            SMA value
        """
        if len(prices) < period:
            return 0.0
        return sum(prices[-period:]) / period
    
    def _calculate_ema(self, current_price: float, previous_ema: Optional[float] = None) -> float:
        """
        Calculate Exponential Moving Average.
        
        EMA = (Current Price × Multiplier) + (Previous EMA × (1 - Multiplier))
        where Multiplier = 2 / (Period + 1)
        
        For the first EMA, use SMA as the starting point.
        
        Args:
            current_price: Current closing price
            previous_ema: Previous EMA value (or None for first calculation)
            
        Returns:
            EMA value
        """
        if previous_ema is None:
            # Use current price as starting EMA
            return current_price
        
        return (current_price * self._ema_multiplier) + (previous_ema * (1 - self._ema_multiplier))
    
    def calculate_signal(self, candles: List[OHLCCandle]) -> Signal:
        """
        Calculate trading signal based on SMA/EMA crossover.
        
        Strategy Rules:
        - BUY: When EMA crosses above SMA (bullish crossover)
        - SELL: When EMA crosses below SMA (bearish crossover)
        - HOLD: No crossover detected
        
        Args:
            candles: List of OHLC candles (oldest to newest)
            
        Returns:
            Trading signal (BUY, SELL, or HOLD)
        """
        if len(candles) < self.get_required_candles():
            return Signal.HOLD
        
        # Extract closing prices
        closes = [c.close for c in candles]
        
        # Store previous values for crossover detection
        self._prev_ema = self._current_ema
        self._prev_sma = self._current_sma
        
        # Calculate current SMA
        self._current_sma = self._calculate_sma(closes, self.sma_period)
        
        # Calculate current EMA
        self._current_ema = self._calculate_ema(closes[-1], self._prev_ema)
        
        # Need previous values to detect crossover
        if self._prev_ema is None or self._prev_sma is None:
            return Signal.HOLD
        
        # Detect crossover
        # Bullish: EMA was below SMA, now EMA is above SMA
        bullish_crossover = (
            self._prev_ema <= self._prev_sma and 
            self._current_ema > self._current_sma
        )
        
        # Bearish: EMA was above SMA, now EMA is below SMA
        bearish_crossover = (
            self._prev_ema >= self._prev_sma and 
            self._current_ema < self._current_sma
        )
        
        if bullish_crossover:
            logger.info(
                f"{self.symbol} BULLISH CROSSOVER: "
                f"EMA({self.ema_period})={self._current_ema:.2f} > "
                f"SMA({self.sma_period})={self._current_sma:.2f}"
            )
            return Signal.BUY
        
        if bearish_crossover:
            logger.info(
                f"{self.symbol} BEARISH CROSSOVER: "
                f"EMA({self.ema_period})={self._current_ema:.2f} < "
                f"SMA({self.sma_period})={self._current_sma:.2f}"
            )
            return Signal.SELL
        
        return Signal.HOLD
    
    def get_indicators(self) -> dict:
        """
        Get current indicator values.
        
        Returns:
            Dictionary with SMA and EMA values
        """
        return {
            "sma": self._current_sma,
            "ema": self._current_ema,
            "sma_period": self.sma_period,
            "ema_period": self.ema_period
        }
    
    def reset(self) -> None:
        """Reset the strategy state."""
        self._prev_ema = None
        self._prev_sma = None
        self._current_ema = None
        self._current_sma = None
        self.candle_history.clear()
        self.position.side = "FLAT"
        self.position.entry_price = 0.0
        self.position.quantity = 0.0

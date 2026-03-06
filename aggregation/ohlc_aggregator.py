"""
OHLC Candle Aggregator for Real-Time Candle Building.

This module aggregates incoming ticks into 1-minute OHLC candles,
ensuring proper minute-boundary closing and maintaining rolling history.
"""

import asyncio
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
import logging

from aggregation.models import Tick, OHLCCandle
from config import get_settings

logger = logging.getLogger(__name__)


class OHLCAggregator:
    """
    Real-time aggregator for building 1-minute OHLC candles from ticks.
    
    Aggregates incoming ticks into candles, closes candles at minute
    boundaries, and maintains a rolling history of finalized candles.
    
    Attributes:
        _current_candles: Dict mapping symbols to their current (building) candle
        _history: Dict mapping symbols to their list of finalized candles
        _lock: Threading lock for thread-safe access
        _candle_callbacks: List of callbacks to notify on candle close
    """
    
    def __init__(self, history_size: Optional[int] = None):
        """
        Initialize the OHLC aggregator.
        
        Args:
            history_size: Maximum number of candles to retain per symbol
        """
        self.settings = get_settings()
        self._history_size = history_size or self.settings.candle_history_size
        
        self._current_candles: Dict[str, OHLCCandle] = {}
        self._history: Dict[str, List[OHLCCandle]] = defaultdict(list)
        self._lock = threading.RLock()
        self._candle_callbacks: List[Callable[[OHLCCandle], None]] = []
        self._running = False
        self._boundary_task: Optional[asyncio.Task] = None
    
    def add_candle_callback(self, callback: Callable[[OHLCCandle], None]) -> None:
        """
        Add a callback to be called when a candle closes.
        
        Args:
            callback: Function to call with each closed candle
        """
        self._candle_callbacks.append(callback)
    
    def remove_candle_callback(self, callback: Callable[[OHLCCandle], None]) -> None:
        """
        Remove a candle callback.
        
        Args:
            callback: Function to remove from callbacks
        """
        if callback in self._candle_callbacks:
            self._candle_callbacks.remove(callback)
    
    def _get_candle_timestamp(self, tick_time: datetime) -> datetime:
        """
        Get the minute-boundary timestamp for a tick.
        
        Args:
            tick_time: The tick's timestamp
            
        Returns:
            Datetime floored to the minute
        """
        return tick_time.replace(second=0, microsecond=0)
    
    def process_tick(self, tick: Tick) -> Optional[OHLCCandle]:
        """
        Process an incoming tick and update/create candles.
        
        Args:
            tick: The incoming tick to process
            
        Returns:
            Closed candle if a candle was finalized, None otherwise
        """
        with self._lock:
            symbol = tick.symbol.upper()
            candle_timestamp = self._get_candle_timestamp(tick.timestamp)
            
            current_candle = self._current_candles.get(symbol)
            closed_candle = None
            
            if current_candle is None:
                # No current candle, create a new one
                self._current_candles[symbol] = OHLCCandle.from_tick(tick, candle_timestamp)
                logger.debug(f"Started new candle for {symbol} at {candle_timestamp}")
                
            elif current_candle.timestamp < candle_timestamp:
                # Current candle is from a previous minute, close it
                closed_candle = self._close_candle(symbol)
                
                # Start a new candle
                self._current_candles[symbol] = OHLCCandle.from_tick(tick, candle_timestamp)
                logger.debug(f"Started new candle for {symbol} at {candle_timestamp}")
                
            else:
                # Update current candle
                current_candle.update(tick)
            
            return closed_candle
    
    def _close_candle(self, symbol: str) -> Optional[OHLCCandle]:
        """
        Close the current candle for a symbol.
        
        Args:
            symbol: The symbol to close the candle for
            
        Returns:
            The closed candle, or None if no candle exists
        """
        candle = self._current_candles.get(symbol)
        if candle:
            candle.is_closed = True
            
            # Add to history
            self._history[symbol].append(candle)
            
            # Trim history if needed
            if len(self._history[symbol]) > self._history_size:
                self._history[symbol] = self._history[symbol][-self._history_size:]
            
            logger.info(
                f"Closed candle for {symbol}: "
                f"O={candle.open:.2f} H={candle.high:.2f} "
                f"L={candle.low:.2f} C={candle.close:.2f} "
                f"V={candle.volume:.4f} Ticks={candle.tick_count}"
            )
            
            # Notify callbacks
            for callback in self._candle_callbacks:
                try:
                    callback(candle)
                except Exception as e:
                    logger.error(f"Error in candle callback: {e}")
            
            return candle
        return None
    
    def close_all_candles(self) -> List[OHLCCandle]:
        """
        Force close all current candles.
        
        Returns:
            List of closed candles
        """
        closed = []
        with self._lock:
            for symbol in list(self._current_candles.keys()):
                candle = self._close_candle(symbol)
                if candle:
                    closed.append(candle)
            self._current_candles.clear()
        return closed
    
    async def _minute_boundary_checker(self) -> None:
        """
        Background task to ensure candles close at minute boundaries.
        
        This ensures candles are closed even if no new ticks arrive.
        """
        while self._running:
            try:
                # Calculate time until next minute
                now = datetime.utcnow()
                next_minute = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
                sleep_time = (next_minute - now).total_seconds() + 0.1  # Add small buffer
                
                await asyncio.sleep(sleep_time)
                
                if not self._running:
                    break
                
                # Check and close any candles from previous minutes
                current_timestamp = self._get_candle_timestamp(datetime.utcnow())
                
                with self._lock:
                    for symbol in list(self._current_candles.keys()):
                        candle = self._current_candles.get(symbol)
                        if candle and candle.timestamp < current_timestamp:
                            self._close_candle(symbol)
                            del self._current_candles[symbol]
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in minute boundary checker: {e}")
                await asyncio.sleep(1)
    
    async def start(self) -> None:
        """Start the aggregator's background tasks."""
        if self._running:
            return
        
        self._running = True
        self._boundary_task = asyncio.create_task(self._minute_boundary_checker())
        logger.info("OHLC Aggregator started")
    
    async def stop(self) -> None:
        """Stop the aggregator and close all candles."""
        self._running = False
        
        if self._boundary_task:
            self._boundary_task.cancel()
            try:
                await self._boundary_task
            except asyncio.CancelledError:
                pass
        
        # Close any remaining candles
        self.close_all_candles()
        logger.info("OHLC Aggregator stopped")
    
    def get_current_candle(self, symbol: str) -> Optional[OHLCCandle]:
        """
        Get the current (building) candle for a symbol.
        
        Args:
            symbol: The trading symbol
            
        Returns:
            Current candle or None if not building
        """
        with self._lock:
            return self._current_candles.get(symbol.upper())
    
    def get_history(self, symbol: str, limit: Optional[int] = None) -> List[OHLCCandle]:
        """
        Get the candle history for a symbol.
        
        Args:
            symbol: The trading symbol
            limit: Maximum number of candles to return (most recent)
            
        Returns:
            List of finalized candles (oldest to newest)
        """
        with self._lock:
            history = self._history.get(symbol.upper(), [])
            if limit:
                return history[-limit:]
            return list(history)
    
    def get_all_current_candles(self) -> Dict[str, OHLCCandle]:
        """
        Get all current (building) candles.
        
        Returns:
            Dict mapping symbols to their current candles
        """
        with self._lock:
            return dict(self._current_candles)
    
    def get_symbols(self) -> List[str]:
        """
        Get all symbols with candle data.
        
        Returns:
            List of symbol names
        """
        with self._lock:
            symbols = set(self._current_candles.keys())
            symbols.update(self._history.keys())
            return list(symbols)

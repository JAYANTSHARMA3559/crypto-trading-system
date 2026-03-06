"""
In-Memory Tick Store for Latest Market Data.

This module provides thread-safe storage for the latest ticks per symbol,
with UTC timestamp normalization.
"""

import threading
from datetime import datetime
from typing import Dict, Optional, List
from aggregation.models import Tick


class TickStore:
    """
    Thread-safe in-memory store for the latest tick per symbol.
    
    Maintains the most recent tick for each tracked symbol with
    proper timestamp normalization to UTC.
    
    Attributes:
        _ticks: Dictionary mapping symbols to their latest tick
        _lock: Threading lock for thread-safe access
    """
    
    def __init__(self):
        """Initialize an empty tick store."""
        self._ticks: Dict[str, Tick] = {}
        self._lock = threading.RLock()
        self._subscribers: List[callable] = []
    
    def update(self, tick: Tick) -> None:
        """
        Update the store with a new tick for a symbol.
        
        Args:
            tick: The new tick to store
        """
        with self._lock:
            self._ticks[tick.symbol.upper()] = tick
        
        # Notify subscribers
        for callback in self._subscribers:
            try:
                callback(tick)
            except Exception as e:
                print(f"Error in tick subscriber: {e}")
    
    def get(self, symbol: str) -> Optional[Tick]:
        """
        Get the latest tick for a symbol.
        
        Args:
            symbol: The trading symbol to look up
            
        Returns:
            The latest Tick for the symbol, or None if not found
        """
        with self._lock:
            return self._ticks.get(symbol.upper())
    
    def get_all(self) -> Dict[str, Tick]:
        """
        Get all latest ticks.
        
        Returns:
            Dictionary of all symbols to their latest ticks
        """
        with self._lock:
            return dict(self._ticks)
    
    def get_symbols(self) -> List[str]:
        """
        Get list of all symbols with stored ticks.
        
        Returns:
            List of symbol names
        """
        with self._lock:
            return list(self._ticks.keys())
    
    def subscribe(self, callback: callable) -> None:
        """
        Subscribe to tick updates.
        
        Args:
            callback: Function to call with each new tick
        """
        self._subscribers.append(callback)
    
    def unsubscribe(self, callback: callable) -> None:
        """
        Unsubscribe from tick updates.
        
        Args:
            callback: Function to remove from subscribers
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)
    
    def clear(self, symbol: Optional[str] = None) -> None:
        """
        Clear stored ticks.
        
        Args:
            symbol: If provided, only clear this symbol. Otherwise clear all.
        """
        with self._lock:
            if symbol:
                self._ticks.pop(symbol.upper(), None)
            else:
                self._ticks.clear()
    
    def __len__(self) -> int:
        """Return the number of symbols with stored ticks."""
        with self._lock:
            return len(self._ticks)
    
    def __contains__(self, symbol: str) -> bool:
        """Check if a symbol has a stored tick."""
        with self._lock:
            return symbol.upper() in self._ticks

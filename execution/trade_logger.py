"""
Trade Logger for Persisting Trade History.

This module provides functionality to log and persist trade information
to a JSON file for later analysis.
"""

import json
import os
import threading
from datetime import datetime
from typing import List, Optional, Dict, Any
import logging

from config import get_settings

logger = logging.getLogger(__name__)


class TradeLogger:
    """
    Logger for persisting trade information to JSON file.
    
    Each trade record includes timestamp, symbol, side, size, price,
    and strategy variant information.
    
    Attributes:
        log_file: Path to the JSON log file
        _trades: In-memory list of trades
        _lock: Threading lock for thread-safe access
    """
    
    def __init__(self, log_file: Optional[str] = None):
        """
        Initialize the trade logger.
        
        Args:
            log_file: Path to log file (uses config default if not specified)
        """
        self.settings = get_settings()
        self.log_file = log_file or self.settings.trade_log_file
        self._trades: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        
        # Load existing trades if file exists
        self._load_trades()
        
        logger.info(f"Trade logger initialized with file: {self.log_file}")
    
    def _load_trades(self) -> None:
        """Load existing trades from the log file."""
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r') as f:
                    self._trades = json.load(f)
                logger.info(f"Loaded {len(self._trades)} existing trades from log")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Could not load existing trades: {e}")
                self._trades = []
    
    def _save_trades(self) -> None:
        """Save all trades to the log file."""
        try:
            with open(self.log_file, 'w') as f:
                json.dump(self._trades, f, indent=2, default=str)
        except IOError as e:
            logger.error(f"Failed to save trades: {e}")
    
    def log_trade(
        self,
        symbol: str,
        side: str,
        size: float,
        price: float,
        variant: str,
        order_id: Optional[str] = None,
        status: str = "FILLED",
        pnl: Optional[float] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Log a new trade.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            side: Trade side ('BUY' or 'SELL')
            size: Trade size/quantity
            price: Execution price
            variant: Strategy variant ('A' or 'B')
            order_id: Exchange order ID (if available)
            status: Order status (default: 'FILLED')
            pnl: Realized P&L (for exit trades)
            notes: Additional notes
            
        Returns:
            The logged trade record
        """
        trade = {
            "timestamp": datetime.utcnow().isoformat(),
            "symbol": symbol.upper(),
            "side": side.upper(),
            "size": size,
            "price": price,
            "variant": variant,
            "order_id": order_id,
            "status": status,
            "pnl": pnl,
            "notes": notes
        }
        
        with self._lock:
            self._trades.append(trade)
            self._save_trades()
        
        logger.info(
            f"Logged trade: {side} {size} {symbol} @ {price:.2f} "
            f"(Variant {variant})"
        )
        
        return trade
    
    def get_trades(
        self,
        symbol: Optional[str] = None,
        variant: Optional[str] = None,
        side: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get trade history with optional filtering.
        
        Args:
            symbol: Filter by symbol
            variant: Filter by strategy variant
            side: Filter by trade side
            limit: Maximum number of trades to return (most recent)
            
        Returns:
            List of trade records
        """
        with self._lock:
            trades = self._trades.copy()
        
        # Apply filters
        if symbol:
            trades = [t for t in trades if t["symbol"] == symbol.upper()]
        
        if variant:
            trades = [t for t in trades if t["variant"] == variant]
        
        if side:
            trades = [t for t in trades if t["side"] == side.upper()]
        
        # Apply limit
        if limit:
            trades = trades[-limit:]
        
        return trades
    
    def get_summary(self, symbol: Optional[str] = None, variant: Optional[str] = None) -> Dict[str, Any]:
        """
        Get trade summary statistics.
        
        Args:
            symbol: Filter by symbol
            variant: Filter by strategy variant
            
        Returns:
            Summary statistics including total trades, P&L, etc.
        """
        trades = self.get_trades(symbol=symbol, variant=variant)
        
        if not trades:
            return {
                "total_trades": 0,
                "buy_trades": 0,
                "sell_trades": 0,
                "total_pnl": 0.0,
                "winning_trades": 0,
                "losing_trades": 0
            }
        
        buy_trades = [t for t in trades if t["side"] == "BUY"]
        sell_trades = [t for t in trades if t["side"] == "SELL"]
        
        pnl_trades = [t for t in trades if t.get("pnl") is not None]
        total_pnl = sum(t["pnl"] for t in pnl_trades)
        winning = len([t for t in pnl_trades if t["pnl"] > 0])
        losing = len([t for t in pnl_trades if t["pnl"] < 0])
        
        return {
            "total_trades": len(trades),
            "buy_trades": len(buy_trades),
            "sell_trades": len(sell_trades),
            "total_pnl": total_pnl,
            "winning_trades": winning,
            "losing_trades": losing,
            "win_rate": winning / len(pnl_trades) if pnl_trades else 0.0
        }
    
    def clear(self) -> None:
        """Clear all trade history."""
        with self._lock:
            self._trades = []
            self._save_trades()
        logger.info("Trade history cleared")
    
    def __len__(self) -> int:
        """Return total number of logged trades."""
        with self._lock:
            return len(self._trades)

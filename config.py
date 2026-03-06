"""
Configuration Management for Live Crypto Trading System.

This module provides centralized configuration using Pydantic Settings,
loading values from environment variables and .env files.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List
import os


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Attributes:
        binance_api_key: Binance Testnet API key
        binance_api_secret: Binance Testnet API secret
        symbols: List of trading symbols to track
        sma_period: Period for Simple Moving Average calculation
        ema_period: Period for Exponential Moving Average calculation
        variant_a_sl: Stop Loss percentage for Variant A (tighter)
        variant_b_sl: Stop Loss percentage for Variant B (looser)
        candle_history_size: Number of historical candles to retain per symbol
        api_host: Host for REST API server
        api_port: Port for REST API server
    """
    
    # Binance Testnet Configuration
    binance_api_key: str = Field(default="", description="Binance Testnet API Key")
    binance_api_secret: str = Field(default="", description="Binance Testnet API Secret")
    
    # Binance Testnet Endpoints
    binance_ws_url: str = Field(
        default="wss://stream.testnet.binance.vision/ws",
        description="Binance Testnet WebSocket URL"
    )
    binance_rest_url: str = Field(
        default="https://testnet.binance.vision/api",
        description="Binance Testnet REST API URL"
    )
    
    # Symbol Configuration
    symbols: List[str] = Field(
        default=["BTCUSDT", "ETHUSDT"],
        description="List of symbols to track"
    )
    
    # Strategy Parameters
    sma_period: int = Field(default=10, description="SMA lookback period")
    ema_period: int = Field(default=5, description="EMA lookback period")
    
    # Stop Loss Configuration
    variant_a_sl: float = Field(default=0.15, description="Variant A Stop Loss (15%)")
    variant_b_sl: float = Field(default=0.10, description="Variant B Stop Loss (10%)")
    
    # Order Configuration
    order_size_btc: float = Field(default=0.001, description="Order size for BTC pairs")
    order_size_eth: float = Field(default=0.01, description="Order size for ETH pairs")
    
    # Candle Configuration
    candle_history_size: int = Field(
        default=100,
        description="Number of historical candles to retain per symbol"
    )
    
    # API Server Configuration
    api_host: str = Field(default="0.0.0.0", description="REST API host")
    # Use PORT env var (set by Render/Railway) or default to 8000
    api_port: int = Field(
        default_factory=lambda: int(os.environ.get("PORT", 8000)),
        description="REST API port"
    )
    
    # Trade Log Configuration
    trade_log_file: str = Field(default="trades.json", description="Trade log file path")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
        @classmethod
        def parse_env_var(cls, field_name: str, raw_val: str):
            """Parse comma-separated symbols list from environment."""
            if field_name == "symbols":
                return [s.strip().upper() for s in raw_val.split(",")]
            return raw_val


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings

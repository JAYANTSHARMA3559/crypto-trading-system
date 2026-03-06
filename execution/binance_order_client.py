"""
Binance Order Client for REST API Operations.

This module provides a client for interacting with the Binance Testnet REST API
to place and manage orders.
"""

import hashlib
import hmac
import time
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlencode
import aiohttp

from config import get_settings

logger = logging.getLogger(__name__)


class BinanceOrderClient:
    """
    REST API client for placing orders on Binance Testnet.
    
    Handles authentication, request signing, and order placement
    using the Binance Testnet REST API.
    
    Attributes:
        api_key: Binance API key
        api_secret: Binance API secret
        base_url: Binance REST API base URL
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None
    ):
        """
        Initialize the Binance order client.
        
        Args:
            api_key: Binance API key (uses config/env if not specified)
            api_secret: Binance API secret (uses config/env if not specified)
        """
        self.settings = get_settings()
        
        self.api_key = api_key or self.settings.binance_api_key
        self.api_secret = api_secret or self.settings.binance_api_secret
        self.base_url = self.settings.binance_rest_url
        
        self._session: Optional[aiohttp.ClientSession] = None
        
        if not self.api_key or not self.api_secret:
            logger.warning(
                "Binance API credentials not configured. "
                "Order placement will fail."
            )
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _sign_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sign a request with HMAC-SHA256.
        
        Args:
            params: Request parameters
            
        Returns:
            Parameters with signature added
        """
        # Add timestamp
        params["timestamp"] = int(time.time() * 1000)
        
        # Create query string and sign it
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        params["signature"] = signature
        return params
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with API key."""
        return {
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded"
        }
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False
    ) -> Dict[str, Any]:
        """
        Make an API request.
        
        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint path
            params: Request parameters
            signed: Whether the request needs to be signed
            
        Returns:
            Response JSON data
        """
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        params = params or {}
        
        if signed:
            params = self._sign_request(params)
        
        try:
            if method == "GET":
                async with session.get(
                    url, 
                    params=params, 
                    headers=self._get_headers()
                ) as response:
                    data = await response.json()
                    if response.status != 200:
                        logger.error(f"API error: {data}")
                    return data
            
            elif method == "POST":
                async with session.post(
                    url,
                    data=params,
                    headers=self._get_headers()
                ) as response:
                    data = await response.json()
                    if response.status != 200:
                        logger.error(f"API error: {data}")
                    return data
            
            elif method == "DELETE":
                async with session.delete(
                    url,
                    params=params,
                    headers=self._get_headers()
                ) as response:
                    data = await response.json()
                    if response.status != 200:
                        logger.error(f"API error: {data}")
                    return data
                    
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return {"error": str(e)}
    
    async def get_account_info(self) -> Dict[str, Any]:
        """
        Get account information.
        
        Returns:
            Account information including balances
        """
        return await self._request("GET", "/v3/account", signed=True)
    
    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get trading rules for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Symbol trading rules or None
        """
        data = await self._request("GET", "/v3/exchangeInfo", {"symbol": symbol})
        
        if "symbols" in data and data["symbols"]:
            return data["symbols"][0]
        return None
    
    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float
    ) -> Dict[str, Any]:
        """
        Place a market order.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            side: Order side ('BUY' or 'SELL')
            quantity: Order quantity
            
        Returns:
            Order response from Binance
        """
        if not self.api_key or not self.api_secret:
            logger.error("Cannot place order: API credentials not configured")
            return {"error": "API credentials not configured"}
        
        params = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": "MARKET",
            "quantity": quantity
        }
        
        logger.info(f"Placing MARKET {side} order: {quantity} {symbol}")
        
        response = await self._request("POST", "/v3/order", params, signed=True)
        
        if "orderId" in response:
            logger.info(
                f"Order placed successfully: ID={response['orderId']}, "
                f"Status={response.get('status')}"
            )
        else:
            logger.error(f"Order failed: {response}")
        
        return response
    
    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        time_in_force: str = "GTC"
    ) -> Dict[str, Any]:
        """
        Place a limit order.
        
        Args:
            symbol: Trading symbol
            side: Order side ('BUY' or 'SELL')
            quantity: Order quantity
            price: Limit price
            time_in_force: Time in force (GTC, IOC, FOK)
            
        Returns:
            Order response from Binance
        """
        if not self.api_key or not self.api_secret:
            logger.error("Cannot place order: API credentials not configured")
            return {"error": "API credentials not configured"}
        
        params = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": "LIMIT",
            "quantity": quantity,
            "price": price,
            "timeInForce": time_in_force
        }
        
        logger.info(f"Placing LIMIT {side} order: {quantity} {symbol} @ {price}")
        
        response = await self._request("POST", "/v3/order", params, signed=True)
        
        if "orderId" in response:
            logger.info(
                f"Order placed successfully: ID={response['orderId']}, "
                f"Status={response.get('status')}"
            )
        else:
            logger.error(f"Order failed: {response}")
        
        return response
    
    async def get_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """
        Get order status.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID
            
        Returns:
            Order information
        """
        params = {
            "symbol": symbol.upper(),
            "orderId": order_id
        }
        return await self._request("GET", "/v3/order", params, signed=True)
    
    async def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """
        Cancel an order.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID
            
        Returns:
            Cancellation response
        """
        params = {
            "symbol": symbol.upper(),
            "orderId": order_id
        }
        return await self._request("DELETE", "/v3/order", params, signed=True)
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get all open orders.
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of open orders
        """
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return await self._request("GET", "/v3/openOrders", params, signed=True)
    
    async def test_connectivity(self) -> bool:
        """
        Test API connectivity.
        
        Returns:
            True if API is reachable
        """
        try:
            response = await self._request("GET", "/v3/ping")
            return response == {}
        except Exception:
            return False

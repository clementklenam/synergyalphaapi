import asyncio
import logging
from typing import Dict, Set, List, Optional, Any
from datetime import datetime
from collections import defaultdict
import yfinance as yf
from fastapi import WebSocket, WebSocketDisconnect
from yfinance.exceptions import YFRateLimitError
import random

logger = logging.getLogger(__name__)


class PriceCache:
    """In-memory cache for storing latest stock prices"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def update(self, ticker: str, price_data: Dict[str, Any]):
        """Update price data for a ticker"""
        async with self._lock:
            self._cache[ticker.upper()] = {
                **price_data,
                "last_updated": datetime.utcnow()
            }
    
    async def get(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get cached price data for a ticker"""
        async with self._lock:
            return self._cache.get(ticker.upper())
    
    async def get_all(self) -> Dict[str, Dict[str, Any]]:
        """Get all cached prices"""
        async with self._lock:
            return self._cache.copy()


class SubscriptionManager:
    """Manages WebSocket subscriptions for stock price updates"""
    
    def __init__(self):
        # Map of ticker -> set of WebSocket connections
        self._subscriptions: Dict[str, Set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
    
    async def subscribe(self, ticker: str, websocket: WebSocket):
        """Add a WebSocket subscription for a ticker"""
        async with self._lock:
            self._subscriptions[ticker.upper()].add(websocket)
            logger.info(f"Subscribed {ticker.upper()}: {len(self._subscriptions[ticker.upper()])} active connections")
    
    async def unsubscribe(self, ticker: str, websocket: WebSocket):
        """Remove a WebSocket subscription for a ticker"""
        async with self._lock:
            ticker = ticker.upper()
            if ticker in self._subscriptions:
                self._subscriptions[ticker].discard(websocket)
                if not self._subscriptions[ticker]:
                    del self._subscriptions[ticker]
                logger.info(f"Unsubscribed {ticker}: {len(self._subscriptions.get(ticker, set()))} remaining")
    
    async def get_active_tickers(self) -> Set[str]:
        """Get set of tickers that have active subscriptions"""
        async with self._lock:
            return set(self._subscriptions.keys())
    
    async def broadcast(self, ticker: str, data: Dict[str, Any]):
        """Broadcast price update to all subscribers of a ticker"""
        async with self._lock:
            ticker = ticker.upper()
            connections = self._subscriptions.get(ticker, set()).copy()
        
        if not connections:
            return
        
        # Send update to all connected clients
        disconnected = set()
        for websocket in connections:
            try:
                await websocket.send_json({
                    "ticker": ticker,
                    "data": data,
                    "timestamp": datetime.utcnow().isoformat()
                })
            except Exception as e:
                logger.warning(f"Error sending to websocket: {e}")
                disconnected.add(websocket)
        
        # Clean up disconnected websockets
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    self._subscriptions[ticker].discard(ws)


class RealtimePriceManager:
    """Manages real-time stock price streaming using Yahoo Finance"""
    
    def __init__(self):
        self.cache = PriceCache()
        self.subscriptions = SubscriptionManager()
        self._polling_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._poll_interval = 2.0  # Poll every 2 seconds
        self._semaphore = asyncio.Semaphore(5)  # Limit concurrent requests
    
    async def start(self):
        """Start the polling task"""
        if self._is_running:
            logger.warning("RealtimePriceManager is already running")
            return
        
        self._is_running = True
        self._polling_task = asyncio.create_task(self._polling_loop())
        logger.info("RealtimePriceManager started")
    
    async def stop(self):
        """Stop the polling task"""
        self._is_running = False
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        logger.info("RealtimePriceManager stopped")
    
    async def _polling_loop(self):
        """Main polling loop that fetches prices for active subscriptions"""
        logger.info("Price polling loop started")
        
        while self._is_running:
            try:
                active_tickers = await self.subscriptions.get_active_tickers()
                
                if not active_tickers:
                    # No active subscriptions, wait a bit
                    await asyncio.sleep(1)
                    continue
                
                logger.debug(f"Polling {len(active_tickers)} active tickers")
                
                # Fetch prices for all active tickers
                tasks = []
                for ticker in active_tickers:
                    task = self._fetch_price(ticker)
                    tasks.append(task)
                
                # Execute all fetches concurrently (with semaphore limit)
                await asyncio.gather(*tasks, return_exceptions=True)
                
                # Wait before next poll
                await asyncio.sleep(self._poll_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying
    
    async def _fetch_price(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fetch price for a single ticker"""
        async with self._semaphore:
            try:
                # Add small random delay to avoid hitting rate limits
                await asyncio.sleep(random.uniform(0.1, 0.5))
                
                stock = yf.Ticker(ticker)
                
                # Get current price info
                info = stock.info
                
                # Get latest quote data
                quote_data = {
                    "price": info.get('currentPrice') or info.get('regularMarketPrice'),
                    "previous_close": info.get('previousClose'),
                    "open": info.get('open'),
                    "day_high": info.get('dayHigh') or info.get('regularMarketDayHigh'),
                    "day_low": info.get('dayLow') or info.get('regularMarketDayLow'),
                    "volume": info.get('volume') or info.get('regularMarketVolume'),
                    "change": info.get('regularMarketChange'),
                    "change_percent": info.get('regularMarketChangePercent'),
                    "market_cap": info.get('marketCap'),
                    "currency": info.get('currency'),
                }
                
                # Calculate change if not available
                if quote_data["price"] and quote_data["previous_close"]:
                    if not quote_data.get("change"):
                        quote_data["change"] = quote_data["price"] - quote_data["previous_close"]
                    if not quote_data.get("change_percent") and quote_data["previous_close"]:
                        quote_data["change_percent"] = (
                            (quote_data["change"] / quote_data["previous_close"]) * 100
                        )
                
                # Update cache
                await self.cache.update(ticker, quote_data)
                
                # Broadcast to subscribers
                await self.subscriptions.broadcast(ticker, quote_data)
                
                return quote_data
                
            except YFRateLimitError:
                logger.warning(f"Rate limit hit for {ticker}, backing off")
                await asyncio.sleep(5)
                return None
            except Exception as e:
                logger.error(f"Error fetching price for {ticker}: {e}")
                return None
    
    async def get_price(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get cached price for a ticker, fetch if not cached or stale"""
        ticker = ticker.upper()
        
        # Check cache first
        cached = await self.cache.get(ticker)
        if cached:
            # If cache is fresh (less than 5 seconds old), return it
            age = (datetime.utcnow() - cached.get("last_updated", datetime.utcnow())).total_seconds()
            if age < 5:
                return cached
        
        # Cache miss or stale, fetch new price
        return await self._fetch_price(ticker)


# Global instance
_realtime_manager: Optional[RealtimePriceManager] = None


def get_realtime_manager() -> RealtimePriceManager:
    """Get the global RealtimePriceManager instance"""
    global _realtime_manager
    if _realtime_manager is None:
        _realtime_manager = RealtimePriceManager()
    return _realtime_manager


# Real-Time Stock Price Data - Brainstorming Document

## Current Architecture
- **Backend**: FastAPI (supports WebSockets natively)
- **Database**: MongoDB (stores historical/snapshot data)
- **Data Sources**: 
  - Yahoo Finance (yfinance) - Delayed/free data
  - Finnhub API - Already have API key configured
- **Current Quote Endpoint**: `/companies/{ticker}/quote` - Returns stored data from MongoDB

---

## Option 1: WebSocket Streaming (Recommended for True Real-Time) ⭐

### Architecture:
```
Client <--WebSocket--> FastAPI Server <--WebSocket--> Data Provider
                      |
                      v
                   Redis/Cache (optional)
```

### Implementation Approach:
1. **FastAPI WebSocket endpoint** for clients to subscribe to price updates
2. **Connect to data provider WebSocket** (Finnhub, Polygon, etc.)
3. **Stream updates** to subscribed clients in real-time

### Data Provider Options:

#### A. Finnhub WebSocket (You already have API key!)
- ✅ Free tier: 60 calls/minute
- ✅ WebSocket support for real-time quotes
- ✅ Easy integration
- ❌ Limited free tier
- **Implementation**: `ws://ws.finnhub.io?token=YOUR_TOKEN`

#### B. Polygon.io
- ✅ Real-time WebSocket API
- ✅ Good free tier
- ✅ Reliable
- ❌ Requires API key setup
- **Cost**: Free tier available, paid plans for higher limits

#### C. Alpha Vantage
- ✅ WebSocket API available
- ✅ Good documentation
- ❌ Rate limits on free tier
- **Cost**: Free tier limited

#### D. Yahoo Finance (WebSocket alternative)
- ✅ Free
- ❌ No official WebSocket API
- ❌ Requires scraping (not recommended)

### Pros:
- ✅ True real-time updates (milliseconds latency)
- ✅ Efficient (only sends updates when prices change)
- ✅ Low server load (push-based, not polling)
- ✅ Scalable (multiple clients can subscribe)

### Cons:
- ❌ More complex to implement
- ❌ Requires WebSocket connection management
- ❌ Data provider costs (though some free tiers available)

### Code Structure:
```python
# WebSocket endpoint
@app.websocket("/ws/quote/{ticker}")
async def websocket_quote(websocket: WebSocket, ticker: str):
    await websocket.accept()
    # Subscribe to ticker updates
    # Stream updates to client
```

---

## Option 2: Server-Sent Events (SSE) - Simpler Alternative

### Architecture:
```
Client <--SSE Stream--> FastAPI Server <--Polling/WebSocket--> Data Provider
```

### Implementation:
1. **FastAPI SSE endpoint** - One-way streaming to clients
2. **Background task** polls data provider every few seconds
3. **Stream updates** to connected clients

### Pros:
- ✅ Simpler than WebSockets (HTTP-based)
- ✅ Automatic reconnection handling
- ✅ Works through proxies/firewalls better
- ✅ Easier to implement

### Cons:
- ❌ One-way only (server → client)
- ❌ Still requires polling on backend (unless using provider WebSocket)
- ❌ Slightly higher latency than WebSockets

### Code Structure:
```python
from sse_starlette.sse import EventSourceResponse

@app.get("/stream/quote/{ticker}")
async def stream_quote(ticker: str):
    async def event_generator():
        while True:
            # Fetch latest price
            # yield price update
            await asyncio.sleep(1)  # Update every second
    return EventSourceResponse(event_generator())
```

---

## Option 3: Fast Polling with Caching (Pseudo Real-Time)

### Architecture:
```
Client <--REST Polling--> FastAPI Server <--Frequent Polling--> Data Provider
                         |
                         v
                      Redis/Cache
```

### Implementation:
1. **Background task** polls data provider every 1-5 seconds
2. **Store latest prices in Redis** (or in-memory cache)
3. **REST endpoint** returns cached prices instantly
4. **Clients poll** the endpoint frequently (every 1-5 seconds)

### Pros:
- ✅ Simple to implement (uses existing REST endpoints)
- ✅ No WebSocket complexity
- ✅ Works with any HTTP client
- ✅ Can use Redis for fast access

### Cons:
- ❌ Higher latency (polling interval)
- ❌ More API calls (higher costs)
- ❌ More server load
- ❌ Not truly "real-time"

### Code Structure:
```python
# Background task
async def update_prices_continuously():
    while True:
        # Poll data provider
        # Update Redis/cache
        await asyncio.sleep(1)  # Poll every second

# REST endpoint
@app.get("/quote/realtime/{ticker}")
async def get_realtime_quote(ticker: str):
    # Return from Redis cache
    return cached_price
```

---

## Option 4: Hybrid Approach (Best of Both Worlds) 🌟

### Architecture:
- **WebSocket/SSE for active clients** (real-time streaming)
- **Fast REST endpoint with caching** (for occasional checks)
- **Background WebSocket connection** to data provider
- **Redis cache** for latest prices

### Implementation:
1. Connect to data provider WebSocket in background
2. Store latest prices in Redis
3. Offer both:
   - WebSocket endpoint for real-time streaming
   - REST endpoint for quick lookups (reads from Redis)

### Pros:
- ✅ True real-time for subscribed clients
- ✅ Fast REST endpoint for quick checks
- ✅ Efficient (single provider connection)
- ✅ Flexible (clients choose their approach)

### Cons:
- ❌ Most complex to implement
- ❌ Requires Redis setup

---

## Recommendation: Start with Option 1 (Finnhub WebSocket) + Option 3 (Caching)

### Why?
1. **You already have Finnhub API key** - Easy to start
2. **FastAPI has native WebSocket support** - No extra dependencies
3. **Add Redis caching** for fast REST access
4. **Scalable** - Can add more providers later

### Implementation Plan:

#### Phase 1: Basic WebSocket Streaming
1. Create WebSocket endpoint for price streaming
2. Connect to Finnhub WebSocket API
3. Stream updates to connected clients
4. Store latest prices in MongoDB/Redis

#### Phase 2: Multi-Ticker Support
1. Allow clients to subscribe to multiple tickers
2. Manage subscriptions efficiently
3. Batch updates

#### Phase 3: Caching Layer
1. Add Redis for fast price lookups
2. Update REST endpoint to use cache
3. Fallback to database if cache miss

#### Phase 4: Advanced Features
1. Price change notifications
2. Historical price tracking in real-time
3. Aggregated feeds (e.g., "top gainers stream")

---

## Technical Considerations

### 1. Connection Management
- Handle client disconnections gracefully
- Reconnect to data provider if connection drops
- Manage multiple client subscriptions

### 2. Rate Limiting
- Respect data provider rate limits
- Implement backpressure handling
- Queue updates if needed

### 3. Error Handling
- Handle provider API errors
- Fallback to cached data
- Notify clients of connection issues

### 4. Scalability
- Use Redis for distributed caching
- Consider message queue (Redis Pub/Sub) for multiple servers
- Load balancing considerations

### 5. Data Storage
- Store latest prices in Redis (fast access)
- Store price history in MongoDB (analytics)
- Consider time-series database (InfluxDB) for high-frequency data

---

## Dependencies to Add

```txt
# For WebSocket support (FastAPI has built-in, but might need):
websockets  # For connecting to provider WebSocket
sse-starlette  # If using SSE instead
redis  # For caching
hiredis  # Faster Redis client (optional)
```

---

## Cost Comparison

| Provider | Free Tier | Paid Tier | Real-Time? |
|----------|-----------|-----------|------------|
| Finnhub | 60 calls/min | $9-99/month | ✅ Yes |
| Polygon.io | Limited | $29+/month | ✅ Yes |
| Alpha Vantage | 5 calls/min | $49.99/month | ✅ Yes |
| Yahoo Finance | Unlimited | Free | ❌ No (delayed) |

---

## Next Steps

1. **Choose approach** (Recommend: Finnhub WebSocket)
2. **Set up Redis** (optional but recommended)
3. **Implement WebSocket endpoint**
4. **Test with single ticker**
5. **Scale to multiple tickers**
6. **Add caching layer**

Would you like me to start implementing one of these approaches?


# API Performance Optimization Plan

## Current Performance Bottlenecks

### 1. ⚠️ **yfinance Blocking Calls** (HIGH PRIORITY)
- **Issue**: `yfinance` is synchronous and blocks the async event loop
- **Impact**: Each yfinance call blocks other requests
- **Location**: `main.py` comprehensive endpoint, dividend endpoint
- **Solution**: Run yfinance calls in thread pool executor

### 2. ⚠️ **No Response Caching** (HIGH PRIORITY)
- **Issue**: Expensive operations (yfinance calls, news scraping) are repeated for every request
- **Impact**: Slow response times, unnecessary API calls
- **Solution**: Implement Redis or in-memory caching with TTL

### 3. ⚠️ **Multiple Sequential yfinance Calls** (MEDIUM PRIORITY)
- **Issue**: Comprehensive endpoint makes 3+ separate yfinance calls sequentially
- **Impact**: Cumulative blocking time
- **Solution**: Batch calls or reuse stock object

### 4. ⚠️ **News Content Scraping** (MEDIUM PRIORITY)
- **Issue**: Full article content scraping is slow (2-5 seconds per article)
- **Impact**: Comprehensive endpoint can take 10+ seconds
- **Solution**: Cache scraped content, make it optional, or async scrape

### 5. ⚠️ **Database Query Optimization** (MEDIUM PRIORITY)
- **Issue**: No indexes on frequently queried fields (ticker, sector, industry)
- **Impact**: Slower database queries
- **Solution**: Add MongoDB indexes

### 6. ⚠️ **Large Response Payloads** (LOW PRIORITY)
- **Issue**: Comprehensive endpoint returns large JSON responses
- **Impact**: Serialization and network transfer time
- **Solution**: Response compression, field selection

---

## Optimization Solutions (Prioritized)

### 🔥 **Priority 1: Make yfinance Calls Async** (BIGGEST IMPACT)

**Problem**: yfinance blocks the event loop
**Solution**: Use `asyncio.to_thread()` or `run_in_executor()`

**Implementation**:
```python
from concurrent.futures import ThreadPoolExecutor
import asyncio

# Create executor for yfinance calls
_yfinance_executor = ThreadPoolExecutor(max_workers=5)

async def get_yfinance_info_async(ticker: str):
    """Fetch yfinance info in thread pool"""
    loop = asyncio.get_event_loop()
    def _fetch():
        stock = yf.Ticker(ticker)
        return stock.info
    return await loop.run_in_executor(_yfinance_executor, _fetch)

async def get_yfinance_history_async(ticker: str, period: str = "1y"):
    """Fetch yfinance history in thread pool"""
    loop = asyncio.get_event_loop()
    def _fetch():
        stock = yf.Ticker(ticker)
        return stock.history(period=period)
    return await loop.run_in_executor(_yfinance_executor, _fetch)
```

**Expected Improvement**: 3-5x faster for endpoints using yfinance

---

### 🔥 **Priority 2: Add Response Caching** (BIG IMPACT)

**Problem**: Expensive operations repeated on every request
**Solution**: Implement Redis or in-memory cache

**Option A: Redis (Recommended for Production)**
```python
import redis.asyncio as redis
from functools import wraps

redis_client = None

async def init_redis():
    global redis_client
    redis_client = await redis.from_url("redis://localhost:6379")

@lru_cache decorator won't work for async, so create custom cache:

def cache_response(ttl: int = 300):
    """Cache endpoint responses"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Create cache key from function name and args
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Try to get from cache
            cached = await redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Store in cache
            await redis_client.setex(cache_key, ttl, json.dumps(result))
            return result
        return wrapper
    return decorator
```

**Option B: In-Memory Cache (Simpler, Good for Development)**
```python
from functools import lru_cache
from datetime import datetime, timedelta
from typing import Dict, Any

class TTLCache:
    def __init__(self, ttl: int = 300):
        self._cache: Dict[str, tuple] = {}
        self.ttl = ttl
    
    async def get(self, key: str) -> Any:
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl):
                return value
            del self._cache[key]
        return None
    
    async def set(self, key: str, value: Any):
        self._cache[key] = (value, datetime.now())

# Global cache instance
_response_cache = TTLCache(ttl=300)  # 5 minutes
```

**Expected Improvement**: 10-100x faster for cached responses

---

### 🔥 **Priority 3: Optimize Comprehensive Endpoint** (MEDIUM-HIGH IMPACT)

**Problem**: Multiple sequential yfinance calls
**Solution**: Batch calls and reuse stock object

**Current Flow**:
1. Fetch stock.info (blocking)
2. Fetch stock.history (blocking)
3. Fetch earnings data (blocking)
4. Each call blocks separately

**Optimized Flow**:
1. Fetch all data in parallel using thread pool
2. Reuse stock object when possible
3. Cache results

**Implementation**:
```python
async def get_comprehensive_data_optimized(ticker: str):
    # Fetch all yfinance data in parallel
    loop = asyncio.get_event_loop()
    
    async def fetch_all():
        def _fetch():
            stock = yf.Ticker(ticker)
            return {
                'info': stock.info,
                'history': stock.history(period="1y"),
                'earnings': stock.earnings if hasattr(stock, 'earnings') else None,
                'calendar': stock.calendar if hasattr(stock, 'calendar') else None
            }
        return await loop.run_in_executor(_yfinance_executor, _fetch)
    
    # Execute all in parallel with database query
    yf_data_task = fetch_all()
    db_task = db.companies.find_one({"ticker": ticker})
    
    yf_data, company = await asyncio.gather(yf_data_task, db_task)
```

**Expected Improvement**: 2-3x faster for comprehensive endpoint

---

### ⚡ **Priority 4: Add Database Indexes** (MEDIUM IMPACT)

**Problem**: Database queries are slow without indexes
**Solution**: Add indexes on frequently queried fields

**Implementation**:
```python
# In database.py or startup script
async def create_indexes():
    db = await MongoManager.get_database()
    
    # Create indexes
    await db.companies.create_index("ticker", unique=True)
    await db.companies.create_index("sector")
    await db.companies.create_index("industry")
    await db.companies.create_index("market_cap")
    await db.companies.create_index([("ticker", "text"), ("companyName", "text")])
    
    logger.info("Database indexes created")
```

**Expected Improvement**: 2-5x faster database queries

---

### ⚡ **Priority 5: Optimize News Scraping** (MEDIUM IMPACT)

**Problem**: Article content scraping is slow (2-5 seconds per article)
**Solution**: 
1. Cache scraped content
2. Make scraping async with timeout
3. Use connection pooling for HTTP requests

**Implementation**:
```python
# In news_service.py
async def _fetch_article_content_async(self, url: str, timeout: int = 5):
    """Fetch article content with timeout"""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    html = await response.text()
                    # Parse content
                    return self._extract_content(html)
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching content from {url}")
        return None
```

**Expected Improvement**: 2-3x faster news content fetching

---

### 📊 **Priority 6: Response Compression** (LOW-MEDIUM IMPACT)

**Problem**: Large JSON responses
**Solution**: Enable gzip compression in FastAPI

**Implementation**:
```python
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)
```

**Expected Improvement**: 50-80% reduction in response size

---

### 📊 **Priority 7: Field Selection** (LOW IMPACT)

**Problem**: Comprehensive endpoint returns everything
**Solution**: Add query parameters to select specific fields

**Implementation**:
```python
@app.get("/companies/{ticker}/comprehensive")
async def get_comprehensive_data(
    ticker: str,
    fields: Optional[str] = Query(None, description="Comma-separated fields to include"),
    # ... other params
):
    # Parse fields parameter and only include requested fields
    if fields:
        requested_fields = set(fields.split(','))
        # Filter response based on requested_fields
```

---

## Implementation Order (Recommended)

1. ✅ **Add Database Indexes** (Quick win, 5 minutes)
2. ✅ **Make yfinance Calls Async** (High impact, 30 minutes)
3. ✅ **Add Response Caching** (High impact, 1-2 hours)
4. ✅ **Optimize Comprehensive Endpoint** (Medium impact, 1 hour)
5. ✅ **Optimize News Scraping** (Medium impact, 30 minutes)
6. ✅ **Add Response Compression** (Quick win, 5 minutes)
7. ✅ **Field Selection** (Low priority, optional)

---

## Expected Overall Improvement

| Optimization | Expected Speedup | Implementation Time |
|-------------|------------------|---------------------|
| Database Indexes | 2-5x (DB queries) | 5 min |
| Async yfinance | 3-5x (yfinance endpoints) | 30 min |
| Response Caching | 10-100x (cached requests) | 1-2 hours |
| Comprehensive Optimize | 2-3x (comprehensive endpoint) | 1 hour |
| News Scraping | 2-3x (news endpoints) | 30 min |
| Response Compression | 1.5-2x (network transfer) | 5 min |

**Combined Expected Improvement**: 
- **Cached requests**: 50-200x faster
- **Uncached requests**: 5-10x faster
- **Database queries**: 2-5x faster

---

## Quick Wins (Do First!)

1. **Add Database Indexes** - 5 minutes, immediate improvement
2. **Enable GZip Compression** - 5 minutes, reduces bandwidth
3. **Make yfinance Async** - 30 minutes, high impact

---

## Monitoring & Metrics

After implementing optimizations, monitor:
- Response times (p50, p95, p99)
- Cache hit rates
- Database query times
- API call counts to yfinance
- Error rates

Consider adding:
```python
import time
from fastapi import Request

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response
```


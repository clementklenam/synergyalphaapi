# Stock News Feature Implementation

## Overview
Added stock news functionality using Yahoo Finance (yfinance) - completely free, no API keys required!

## Implementation

### Created Files
1. **`news_service.py`** - News fetching service
   - `NewsService` class for fetching and formatting news
   - Uses yfinance `.news` attribute
   - Concurrent fetching with rate limiting
   - Formats articles for consistent API responses

### API Endpoints

#### 1. Get News for Single Ticker
```
GET /companies/{ticker}/news?limit=10
```

**Parameters:**
- `ticker` (path): Stock ticker symbol (e.g., AAPL)
- `limit` (query, optional): Maximum articles to return (1-50, default: 10)

**Example:**
```bash
curl http://localhost:8000/companies/AAPL/news?limit=5
```

**Response:**
```json
{
  "ticker": "AAPL",
  "count": 5,
  "articles": [
    {
      "id": "article-id",
      "ticker": "AAPL",
      "title": "Article Title",
      "summary": "Article summary",
      "description": "Article description",
      "publish_date": "2026-01-03T12:00:00Z",
      "display_time": "2026-01-03T14:00:00Z",
      "url": "https://finance.yahoo.com/news/...",
      "thumbnail_url": "https://s.yimg.com/...",
      "provider": "Yahoo Finance",
      "provider_url": "http://finance.yahoo.com/",
      "is_editor_pick": false,
      "content_type": "STORY"
    }
  ]
}
```

#### 2. Get News for Multiple Tickers
```
GET /news/batch?tickers=AAPL&tickers=MSFT&tickers=GOOGL&limit=10
```

**Parameters:**
- `tickers` (query, required): List of ticker symbols (max 20)
- `limit` (query, optional): Maximum articles per ticker (1-50, default: 10)

**Example:**
```bash
curl "http://localhost:8000/news/batch?tickers=AAPL&tickers=MSFT&limit=5"
```

**Response:**
```json
{
  "count": 2,
  "tickers": ["AAPL", "MSFT"],
  "news": {
    "AAPL": {
      "count": 5,
      "articles": [...]
    },
    "MSFT": {
      "count": 5,
      "articles": [...]
    }
  }
}
```

## Features

✅ **Free** - Uses Yahoo Finance (yfinance), no API keys
✅ **Fast** - Concurrent fetching for multiple tickers
✅ **Rate Limited** - Built-in protection against API throttling
✅ **Formatted** - Clean, consistent response format
✅ **Error Handling** - Graceful error handling with fallbacks

## Data Source

- **Yahoo Finance** via `yfinance` library
- No additional dependencies required
- News articles include:
  - Title, summary, description
  - Publish date and display time
  - Thumbnail images
  - Article URLs
  - Provider information
  - Editor picks flag

## Usage Examples

### Python
```python
import requests

# Single ticker
response = requests.get('http://localhost:8000/companies/AAPL/news?limit=5')
data = response.json()
for article in data['articles']:
    print(f"{article['title']} - {article['url']}")

# Multiple tickers
response = requests.get(
    'http://localhost:8000/news/batch',
    params={'tickers': ['AAPL', 'MSFT', 'GOOGL'], 'limit': 5}
)
news_data = response.json()
for ticker, ticker_news in news_data['news'].items():
    print(f"\n{ticker}: {ticker_news['count']} articles")
    for article in ticker_news['articles']:
        print(f"  - {article['title']}")
```

### JavaScript/TypeScript
```javascript
// Single ticker
fetch('http://localhost:8000/companies/AAPL/news?limit=5')
  .then(res => res.json())
  .then(data => {
    console.log(`Found ${data.count} articles for ${data.ticker}`);
    data.articles.forEach(article => {
      console.log(`${article.title} - ${article.url}`);
    });
  });

// Multiple tickers
const tickers = ['AAPL', 'MSFT', 'GOOGL'];
const params = new URLSearchParams();
tickers.forEach(t => params.append('tickers', t));
params.append('limit', '5');

fetch(`http://localhost:8000/news/batch?${params}`)
  .then(res => res.json())
  .then(data => {
    Object.entries(data.news).forEach(([ticker, news]) => {
      console.log(`${ticker}: ${news.count} articles`);
    });
  });
```

## Testing

After restarting the server, test with:

```bash
# Single ticker
curl http://localhost:8000/companies/AAPL/news?limit=3

# Multiple tickers
curl "http://localhost:8000/news/batch?tickers=AAPL&tickers=MSFT&limit=3"
```

## Notes

- News is fetched on-demand (not cached)
- Yahoo Finance typically returns up to 10 articles per ticker
- Articles are sorted by relevance/date (Yahoo Finance ordering)
- Rate limiting is built-in to avoid API throttling
- All tickers are validated against the database first

## Future Enhancements

Possible improvements:
- [ ] Cache news articles with TTL
- [ ] Store news in database for historical tracking
- [ ] Add filtering by date range
- [ ] Add sentiment analysis (if using paid APIs)
- [ ] Add news search/filtering
- [ ] WebSocket streaming for new articles


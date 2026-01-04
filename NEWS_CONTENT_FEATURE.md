# News Content Extraction Feature

## Overview
Added full article content extraction capability to the news endpoints. Now you can optionally fetch the complete article text along with metadata.

## New Feature

### Query Parameter: `include_content`

Both news endpoints now support an optional `include_content` query parameter:

- **Default**: `false` (only metadata)
- **When `true`**: Fetches and extracts full article text from the article URL

## Updated Endpoints

### 1. Single Ticker News (Updated)
```
GET /companies/{ticker}/news?limit=10&include_content=true
```

**New Parameter:**
- `include_content` (query, optional): `true` to fetch full article content (default: `false`)

**Example:**
```bash
# Without content (fast)
curl "http://localhost:8000/companies/AAPL/news?limit=3"

# With content (slower but complete)
curl "http://localhost:8000/companies/AAPL/news?limit=3&include_content=true"
```

**Response (with content):**
```json
{
  "ticker": "AAPL",
  "count": 3,
  "include_content": true,
  "articles": [
    {
      "id": "article-id",
      "ticker": "AAPL",
      "title": "Article Title",
      "summary": "Article summary",
      "url": "https://finance.yahoo.com/news/...",
      "content": "Full article text here...\n\nMultiple paragraphs...",
      ...
    }
  ]
}
```

### 2. Batch News (Updated)
```
GET /news/batch?tickers=AAPL&tickers=MSFT&limit=10&include_content=true
```

**New Parameter:**
- `include_content` (query, optional): `true` to fetch full article content (default: `false`)

## Implementation Details

### How It Works

1. **Metadata Fetching** (always done):
   - Uses yfinance to get article metadata (title, summary, URL, etc.)

2. **Content Extraction** (when `include_content=true`):
   - Fetches the article HTML from the URL
   - Uses BeautifulSoup to parse HTML
   - Extracts main article content using common selectors
   - Cleans and formats the text
   - Returns the full article text

### Content Extraction Strategy

The system tries multiple strategies to extract article content:

1. **Primary selectors** (tries in order):
   - `<article>` tag
   - `[role="article"]` attribute
   - `.article-body`, `.article-content`, `.post-content`
   - `.caas-body` (Yahoo Finance specific)
   - `#article-body`

2. **Fallback**:
   - If primary selectors fail, extracts all `<p>` tags
   - Only returns content if substantial text is found (>100 characters)

3. **Cleaning**:
   - Removes scripts, styles, nav, header, footer
   - Removes excessive whitespace
   - Formats with proper line breaks

## Performance Considerations

- **Without content**: Fast (~0.5-1 second)
- **With content**: Slower (~2-5 seconds per article)
  - Fetches HTML from URL
  - Parses and extracts content
  - Multiple HTTP requests required

### Rate Limiting

- Content fetching is rate-limited (2 concurrent requests)
- 10-second timeout per article
- Graceful error handling if extraction fails

## Usage Examples

### Python
```python
import requests

# Fast: Metadata only
response = requests.get('http://localhost:8000/companies/AAPL/news?limit=3')
data = response.json()
for article in data['articles']:
    print(f"{article['title']} - {article['url']}")

# Complete: With full content
response = requests.get(
    'http://localhost:8000/companies/AAPL/news',
    params={'limit': 3, 'include_content': True}
)
data = response.json()
for article in data['articles']:
    print(f"\n{article['title']}")
    if article.get('content'):
        print(f"Content: {article['content'][:200]}...")
    else:
        print("Content not available")
```

### JavaScript
```javascript
// Metadata only (fast)
fetch('http://localhost:8000/companies/AAPL/news?limit=3')
  .then(res => res.json())
  .then(data => {
    data.articles.forEach(article => {
      console.log(`${article.title} - ${article.url}`);
    });
  });

// With content (slower)
fetch('http://localhost:8000/companies/AAPL/news?limit=3&include_content=true')
  .then(res => res.json())
  .then(data => {
    data.articles.forEach(article => {
      console.log(`\n${article.title}`);
      if (article.content) {
        console.log(`Content: ${article.content.substring(0, 200)}...`);
      }
    });
  });
```

## Limitations

1. **Extraction Success Rate**:
   - Works best with standard article formats
   - May fail on custom HTML structures
   - Yahoo Finance articles work well

2. **Performance**:
   - Significantly slower when `include_content=true`
   - Multiple HTTP requests required
   - Consider caching for production

3. **Legal/ToS**:
   - Respects robots.txt and site terms
   - User-Agent header included
   - Intended for personal/non-commercial use

4. **Reliability**:
   - Depends on article site availability
   - Some sites may block automated requests
   - Timeout handling included

## Future Enhancements

Possible improvements:
- [ ] Cache extracted content with TTL
- [ ] Store content in database
- [ ] Add content preview/summary generation
- [ ] Support more article formats
- [ ] Add content length limits
- [ ] Better error reporting for failed extractions

## Testing

After server restart, test with:

```bash
# Without content (fast)
curl "http://localhost:8000/companies/AAPL/news?limit=2"

# With content (slower)
curl "http://localhost:8000/companies/AAPL/news?limit=2&include_content=true"
```

## Notes

- Content extraction is optional - defaults to `false` for performance
- Extraction failures are handled gracefully (returns metadata only)
- Content is returned as plain text (no HTML formatting)
- Works best with Yahoo Finance articles and standard news sites


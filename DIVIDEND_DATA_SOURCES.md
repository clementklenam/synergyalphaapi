# Dividend Data Sources - Where to Get Missing Data

## Currently Missing Data Fields

1. **growth_streak** - Years of consecutive dividend growth
2. **sector_median** - Sector median dividend metrics
3. **recordDate** - Record date for dividends
4. **declareDate** - Declaration date for dividends
5. **payoutType** - Cash/Stock dividend type
6. **Multi-stock comparison data**

---

## Option 1: Financial Modeling Prep (FMP) ⭐ **YOU ALREADY HAVE THIS!**

**API Key**: Already configured in settings (`FMP_API_KEY`)

### Available Dividend Data:
- ✅ **Dividend history with dates** - `/v3/historical-price-full/stock_dividend/{symbol}`
- ✅ **Record dates** - Available in dividend data
- ✅ **Declaration dates** - Available in dividend data
- ✅ **Payment dates** - Available in dividend data
- ✅ **Dividend type** - Cash/Stock distinction
- ⚠️ **Growth streak** - Can calculate from historical data
- ⚠️ **Sector median** - Would need to fetch all sector stocks and calculate

### Free Tier:
- 250 API calls/day
- Good for moderate usage

### API Endpoints:
```python
# Dividend history
GET https://financialmodelingprep.com/api/v3/historical-price-full/stock_dividend/{symbol}?apikey={key}

# Example response includes:
{
  "date": "2024-11-07",
  "label": "November 07, 24",
  "adjDividend": 0.25,
  "recordDate": "2024-11-12",  # ✅ Available!
  "paymentDate": "2024-11-14",
  "declarationDate": "2024-10-31"  # ✅ Available!
}
```

### Implementation:
```python
async def get_fmp_dividend_data(ticker: str, api_key: str):
    url = f"https://financialmodelingprep.com/api/v3/historical-price-full/stock_dividend/{ticker}?apikey={api_key}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            return data
```

---

## Option 2: Finnhub API ⭐ **YOU ALREADY HAVE THIS!**

**API Key**: Already configured (`FINNHUB_API_KEY`)

### Available Dividend Data:
- ✅ **Dividend history** - `/stock/dividend?symbol={symbol}`
- ⚠️ **Record dates** - May be available
- ❌ **Declaration dates** - Not available
- ✅ **Payment dates** - Available
- ❌ **Dividend type** - Not explicitly available
- ❌ **Growth streak** - Would need calculation
- ❌ **Sector median** - Not available

### Free Tier:
- 60 API calls/minute
- Good rate limits

### API Endpoints:
```python
# Dividend history
GET https://finnhub.io/api/v1/stock/dividend?symbol={symbol}&token={token}

# Example response:
{
  "symbol": "AAPL",
  "data": [
    {
      "date": "2024-11-07",
      "amount": 0.25
    }
  ]
}
```

---

## Option 3: Alpha Vantage (Free Tier)

### Available Dividend Data:
- ✅ **Dividend history** - TIME_SERIES_MONTHLY_ADJUSTED
- ⚠️ **Some dates** - Limited
- ❌ **Record/Declaration dates** - Not available
- ❌ **Dividend type** - Not available

### Free Tier:
- 5 API calls/minute
- 500 calls/day
- Very limited for production

---

## Option 4: Polygon.io (Paid, but good free tier)

### Available Dividend Data:
- ✅ **Comprehensive dividend data** - `/v2/reference/dividends`
- ✅ **Record dates** - Available
- ✅ **Declaration dates** - Available
- ✅ **Payment dates** - Available
- ✅ **Dividend type** - Available
- ✅ **Sector data** - Available with paid plans

### Free Tier:
- Limited historical data
- Good for testing

### Paid Plans:
- $29/month+ for production use
- Comprehensive data

---

## Option 5: SEC EDGAR (Free, but complex)

### Available Dividend Data:
- ✅ **All dividend filings** - 10-K, 10-Q, 8-K
- ✅ **Declaration dates** - In filings
- ✅ **Record dates** - In filings
- ✅ **Payment dates** - In filings
- ❌ **Easy API** - Requires parsing HTML/XML

### Complexity:
- High - Need to parse SEC filings
- Requires significant development
- Free but time-consuming

---

## Recommended Approach

### For Your Use Case:

**Primary: Financial Modeling Prep (FMP)** ⭐
- You already have the API key
- Provides recordDate, declareDate, paymentDate
- Provides dividend type information
- Good free tier (250 calls/day)
- Can calculate growth_streak from historical data

**Supplement with:**
- **yfinance** - For basic dividend data (already using)
- **Calculate growth_streak** - From FMP historical data
- **Calculate sector_median** - Fetch sector stocks from FMP and calculate (uses more API calls)

### Implementation Priority:

1. **High Priority (Easy wins with FMP):**
   - ✅ recordDate
   - ✅ declareDate
   - ✅ payoutType

2. **Medium Priority (Calculatable):**
   - ⚠️ growth_streak - Calculate from FMP historical data

3. **Low Priority (Complex/Expensive):**
   - ❌ sector_median - Would require fetching many stocks
   - ❌ Multi-stock comparison - Not essential for single-stock endpoint

---

## Code Example: Adding FMP Dividend Data

```python
from settings import Settings
import aiohttp

async def get_fmp_dividend_details(ticker: str):
    """Get detailed dividend data from FMP"""
    api_key = Settings.FMP_API_KEY
    url = f"https://financialmodelingprep.com/api/v3/historical-price-full/stock_dividend/{ticker}?apikey={api_key}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                return data
    return None

# Use in dividend endpoint:
fmp_data = await get_fmp_dividend_details(ticker)
# Merge with yfinance data
```

---

## Summary Table

| Data Field | yfinance | FMP (You have!) | Finnhub (You have!) | Polygon | SEC EDGAR |
|------------|----------|-----------------|---------------------|---------|-----------|
| dividendYield | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| dividendRate | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| payoutRatio | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| recordDate | ❌ | ✅ | ⚠️ | ✅ | ✅ |
| declareDate | ❌ | ✅ | ❌ | ✅ | ✅ |
| payoutType | ❌ | ✅ | ❌ | ✅ | ✅ |
| growth_streak | ❌ | ⚠️ (calc) | ⚠️ (calc) | ⚠️ (calc) | ⚠️ (calc) |
| sector_median | ❌ | ⚠️ (many calls) | ❌ | ✅ (paid) | ❌ |

**Legend:**
- ✅ Available
- ⚠️ Available with calculation/multiple calls
- ❌ Not available

**Recommendation: Use FMP API (you already have the key!)**

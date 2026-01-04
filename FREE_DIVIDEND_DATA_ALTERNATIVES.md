# Free Dividend Data Sources (Apart from FMP)

## Missing Data Fields:
1. **recordDate** - Record date for dividends
2. **declareDate** - Declaration date for dividends  
3. **payoutType** - Cash/Stock dividend type
4. **growth_streak** - Years of consecutive dividend growth (calculatable)
5. **sector_median** - Sector median dividend metrics (calculatable)

---

## Option 1: SEC EDGAR (100% Free, No API Key) ⭐

### What It Provides:
- ✅ **Declaration dates** - In 8-K, 10-K, 10-Q filings
- ✅ **Record dates** - In dividend announcements
- ✅ **Payment dates** - In filings
- ✅ **Dividend type** - Cash/Stock specified in filings
- ✅ **Historical data** - All historical filings
- ✅ **Completely free** - No API key, no limits

### Limitations:
- ❌ **Complex parsing** - Requires HTML/XML parsing
- ❌ **No structured API** - Need to parse filings
- ❌ **Time-consuming** - More development effort

### How to Access:
```python
# SEC EDGAR Company Filings API (Free)
# Base URL: https://data.sec.gov/submissions/

# Example:
# 1. Get company CIK (Central Index Key)
GET https://data.sec.gov/submissions/CIK0000320193.json  # AAPL's CIK

# 2. Get recent filings
GET https://data.sec.gov/submissions/CIK0000320193.json
# Look for 8-K filings (dividend declarations)

# 3. Get specific filing
GET https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm
# Parse HTML for dividend information
```

### Implementation Complexity:
- **High** - Requires web scraping/parsing
- Need to identify dividend-related filings
- Parse HTML/XML for dates and amounts

---

## Option 2: Yahoo Finance Web Scraping (Free, No API Key)

### What It Provides:
- ⚠️ **Some dates** - May be in HTML but not in yfinance API
- ⚠️ **Dividend type** - Sometimes in page HTML
- ✅ **Free** - No API key needed
- ✅ **Real-time** - Current data

### Limitations:
- ❌ **Unreliable** - HTML structure can change
- ❌ **Against Terms of Service** - Scraping may violate ToS
- ❌ **Rate limiting** - Can get blocked
- ❌ **Fragile** - Breaks when HTML changes

### Not Recommended:
- Violates terms of service
- Unreliable for production

---

## Option 3: Nasdaq Dividend Calendar (Free, Limited)

### What It Provides:
- ✅ **Record dates** - Available on website
- ✅ **Ex-dividend dates** - Available
- ✅ **Payment dates** - Available
- ⚠️ **Declaration dates** - Sometimes available
- ✅ **Free access** - Public website

### Limitations:
- ❌ **No official API** - Requires web scraping
- ❌ **Limited historical data** - Mainly current/upcoming
- ❌ **Scraping required** - HTML parsing needed

### URL Format:
```
https://www.nasdaq.com/market-activity/dividends
https://www.nasdaq.com/market-activity/stocks/{ticker}/dividend-history
```

### Implementation:
- Would require BeautifulSoup/requests
- Parse HTML tables
- Fragile to website changes

---

## Option 4: IEX Cloud Free Tier (Free, but Limited)

### What It Provides:
- ✅ **Dividend data** - `/stock/{symbol}/dividends`
- ⚠️ **Some dates** - Limited detail
- ✅ **Free tier** - 50,000 messages/month
- ✅ **Official API** - Structured data

### Free Tier Limits:
- 50,000 messages/month
- Good for development/testing
- May need paid plan for production

### API Endpoint:
```
GET https://cloud.iexapis.com/stable/stock/{symbol}/dividends?token={token}
```

### What's Available:
- Dividend amounts
- Payment dates
- Ex-dividend dates
- ❌ Record dates - Not clearly available
- ❌ Declaration dates - Not available
- ❌ Dividend type - Not explicitly available

### Requires:
- Free account registration
- API key (free)

---

## Option 5: Alpha Vantage Free Tier (Very Limited)

### What It Provides:
- ✅ **Dividend history** - TIME_SERIES_MONTHLY_ADJUSTED
- ❌ **Record dates** - Not available
- ❌ **Declaration dates** - Not available
- ❌ **Dividend type** - Not available

### Free Tier Limits:
- 5 API calls/minute
- 500 calls/day
- Too limited for production

### Verdict:
- ❌ Doesn't provide missing fields anyway
- Not useful for this use case

---

## Option 6: EOD Historical Data Free Tier

### What It Provides:
- ✅ **Dividend history** - `/eod/{symbol}?api_token={token}`
- ⚠️ **Some dates** - Limited
- ✅ **Free tier** - 20 API calls/day

### Free Tier Limits:
- 20 API calls/day (very limited)
- Requires registration

### What's Available:
- Dividend amounts
- Payment dates
- ❌ Record dates - Not clearly available
- ❌ Declaration dates - Not available
- ❌ Dividend type - Not available

---

## Option 7: Polygon.io Free Tier (Limited)

### What It Provides:
- ✅ **Dividend data** - `/v2/reference/dividends`
- ✅ **Record dates** - Available (paid plans)
- ✅ **Declaration dates** - Available (paid plans)
- ✅ **Dividend type** - Available (paid plans)

### Free Tier Limitations:
- ❌ **Very limited** - Mostly paid features
- Basic data only
- Missing fields require paid plans ($29+/month)

---

## Option 8: Calculate from Available Data (Free Strategy)

### growth_streak (Calculatable from yfinance):
```python
# Use yfinance dividend history
# Calculate consecutive years of dividend increases
# Completely free - just calculation

def calculate_growth_streak(dividends_dict):
    # Group by year
    # Compare year-over-year
    # Count consecutive increases
    pass
```

### sector_median (Calculatable but expensive):
```python
# Fetch all stocks in sector from database
# Calculate dividend metrics for each
# Calculate median
# Free but uses many API calls
```

---

## Comparison Table (Free Options)

| Data Field | SEC EDGAR | Nasdaq | IEX Cloud Free | EOD Free | Polygon Free | Calculate |
|------------|-----------|--------|----------------|----------|--------------|-----------|
| recordDate | ✅ (parse) | ✅ (scrape) | ⚠️ | ❌ | ❌ (paid) | ❌ |
| declareDate | ✅ (parse) | ⚠️ (scrape) | ❌ | ❌ | ❌ (paid) | ❌ |
| payoutType | ✅ (parse) | ⚠️ (scrape) | ❌ | ❌ | ❌ (paid) | ❌ |
| growth_streak | ⚠️ (calc) | ⚠️ (calc) | ⚠️ (calc) | ⚠️ (calc) | ⚠️ (calc) | ✅ (free) |
| sector_median | ⚠️ (many) | ⚠️ (many) | ⚠️ (many) | ⚠️ (many) | ⚠️ (many) | ⚠️ (many) |
| Cost | Free | Free | Free (limited) | Free (very limited) | Free (very limited) | Free |
| Complexity | High | Medium | Low | Low | Low | Medium |
| Reliability | High | Low | High | Medium | High | High |

---

## Recommendations (Free Options)

### Best Free Option (No API Key): SEC EDGAR ⭐
- **Pros:**
  - 100% free, no API key
  - Official SEC data (most reliable)
  - All data available
  - No rate limits
  
- **Cons:**
  - High complexity (parsing HTML/XML)
  - Requires development effort
  - Slower to implement

### Easiest Free Option (API Key Required): IEX Cloud Free Tier
- **Pros:**
  - Easy to use API
  - Structured data
  - 50,000 calls/month
  
- **Cons:**
  - Doesn't provide recordDate/declareDate
  - Still missing key fields
  - Requires registration

### For Growth Streak: Calculate from yfinance (Free)
- ✅ Use existing yfinance dividend data
- ✅ No additional API needed
- ✅ Just calculation logic

### For Sector Median: Calculate from Database (Free but Many Calls)
- ✅ Use your existing database
- ⚠️ Would need to fetch many stocks
- ⚠️ Uses many API calls

---

## Final Recommendation for Free Options:

1. **For recordDate/declareDate/payoutType:**
   - **Option A**: Use FMP (you already have it) - Easiest ✅
   - **Option B**: SEC EDGAR parsing - Free but complex
   - **Option C**: Nasdaq scraping - Free but unreliable

2. **For growth_streak:**
   - Calculate from yfinance data (free, just coding) ✅

3. **For sector_median:**
   - Calculate from your database (free but many API calls)
   - Or skip (not essential for single-stock endpoint)

**Bottom Line: FMP is still your best option even among free alternatives, but SEC EDGAR is the only truly free (no API key) option that provides the missing fields.**

---

## Additional Free Options (From Research)

## Option 9: DataJockey (Free, Requires Registration)

### What It Provides:
- ✅ **Financial data from SEC filings** - Clean, structured data
- ✅ **Free API key** - No credit card required
- ⚠️ **Dividend data** - May include dividend information
- ✅ **From SEC filings** - Official source

### Free Tier:
- Free API key available
- Unknown limits (check website)

### Website: https://datajockey.io

### Status:
- ✅ Free tier available
- ⚠️ Need to verify dividend data availability

---

## Option 10: Finnworlds Historical Dividends API (Free Tier?)

### What It Provides:
- ✅ **Historical dividend data** - Detailed accounts
- ✅ **JSON format** - Structured data
- ✅ **Updated regularly** - With new distributions
- ⚠️ **Free tier availability** - Need to verify

### Website: https://finnworlds.com/historical-dividends-api/

### Status:
- ⚠️ Need to check if free tier exists
- May require registration

---

## Option 11: HeyDividend API (Free Tier)

### What It Provides:
- ✅ **Dividend data API** - Comprehensive
- ✅ **Real-time updates** - Current data
- ✅ **Historical data** - Past dividends
- ✅ **Free tier available** - Limited access

### Website: https://api.heydividend.com/

### Free Tier:
- Free tier with limitations
- Suitable for basic needs

### Status:
- ✅ Free tier available
- ⚠️ Need to verify what data is included

---

## Option 12: DivScout (Free/Open Source)

### What It Provides:
- ✅ **SEC EDGAR XBRL parsing** - Automated
- ✅ **Confidence-scored data** - Validated
- ✅ **GitHub repository** - Open source tools
- ✅ **Live dashboard** - Free access

### Website: https://divscout.com/

### Status:
- ✅ Free/open source tools available
- ✅ GitHub repository for parsing SEC data
- May help with SEC EDGAR parsing

---

## Option 13: Tradefeeds Historical Dividends API (Free Tier?)

### What It Provides:
- ✅ **Historical dividends** - Comprehensive database
- ✅ **Dividend calendar** - Upcoming dates
- ✅ **Global coverage** - Worldwide stocks
- ⚠️ **Free tier availability** - Need to verify

### Website: https://tradefeeds.com/historical-dividends-api/

### Status:
- ⚠️ Need to check if free tier exists
- May require registration

---

## Updated Comparison Table

| Source | recordDate | declareDate | payoutType | Cost | Complexity | Reliability |
|--------|-----------|-------------|------------|------|------------|-------------|
| **SEC EDGAR** | ✅ (parse) | ✅ (parse) | ✅ (parse) | Free | High | High |
| **FMP** (you have!) | ✅ | ✅ | ✅ | Free (250/day) | Low | High |
| **Nasdaq** | ✅ (scrape) | ⚠️ (scrape) | ⚠️ (scrape) | Free | Medium | Low |
| **IEX Cloud Free** | ❌ | ❌ | ❌ | Free | Low | High |
| **EOD Free** | ❌ | ❌ | ❌ | Free (20/day) | Low | Medium |
| **DataJockey** | ⚠️ (verify) | ⚠️ (verify) | ⚠️ (verify) | Free | Low | Medium |
| **HeyDividend** | ⚠️ (verify) | ⚠️ (verify) | ⚠️ (verify) | Free (limited) | Low | Medium |
| **DivScout Tools** | ✅ (via SEC) | ✅ (via SEC) | ✅ (via SEC) | Free | Medium | High |
| **Calculate from yfinance** | ❌ | ❌ | ❌ | Free | Medium | High |

---

## Final Recommendations (Free Options):

### Best Overall: FMP (You Already Have It!) ⭐
- ✅ Easiest to implement
- ✅ Provides all missing fields
- ✅ You already have the API key
- ✅ 250 calls/day free tier

### Best If No API Key: SEC EDGAR
- ✅ 100% free, no registration
- ✅ Official SEC data
- ✅ All fields available
- ❌ Complex parsing required

### Best for Growth Streak: Calculate from yfinance
- ✅ Completely free
- ✅ No additional API needed
- ✅ Just calculation logic

### Worth Investigating:
1. **DataJockey** - Free API, SEC-sourced, worth checking
2. **HeyDividend** - Free tier, worth verifying data
3. **DivScout GitHub** - Free tools for SEC parsing

**Bottom Line: FMP is still your easiest option, but SEC EDGAR is the only 100% free (no API key) option that definitely provides all the missing fields.**

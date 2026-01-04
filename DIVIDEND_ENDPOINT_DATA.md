# Dividend Endpoint - Available Data

## Endpoint: `/companies/{ticker}/dividends`

### Data Source
**yfinance** - All dividend data comes from Yahoo Finance API (free, no API key required)

---

## Response Structure

### 1. Dividend Metrics
Contains dividend-related metrics from yfinance. Only non-null values are included.

**Available Fields:**
- `dividend_yield` - Current dividend yield percentage
- `annual_payout` - Annual dividend amount (from dividendRate or calculated from recent dividends)
- `payout_ratio` - Payout ratio percentage
- `growth_streak` - Years of consecutive dividend growth (calculated from historical data)
- `payout_frequency` - Dividend payment frequency (if available)
- `eps` - Earnings per share (trailing EPS)
- `five_year_avg_yield` - Five-year average dividend yield
- `last_dividend_value` - Last dividend payment amount
- `trailing_annual_dividend_rate` - Trailing annual dividend rate
- `trailing_annual_dividend_yield` - Trailing annual dividend yield

**Note:** Only fields with actual values are returned (null fields are excluded)

---

### 2. Upcoming Payouts
Contains information about upcoming dividend payments. Only non-null values are included.

**Available Fields:**
- `exDividendDate` - Ex-dividend date (YYYY-MM-DD format)
- `exDividendAmount` - Estimated dividend amount per share
- `paymentDate` - Dividend payment date (YYYY-MM-DD format)
- `daysUntilExDividend` - Number of days until ex-dividend date
- `daysUntilPayment` - Number of days until payment date

**Note:** Only fields with actual values are returned (null fields are excluded)

---

### 3. Dividend History
Historical dividend payments from yfinance.

**Available Fields (per entry):**
- `exDivDate` - Ex-dividend date (YYYY-MM-DD format)
- `amount` - Dividend amount per share
- `fiscalYear` - Fiscal year of the dividend
- `fiscalQuarter` - Fiscal quarter (1-4) of the dividend

**Note:** Only yfinance data is included. Fields like `declareDate`, `recordDate`, `payDate`, and `payoutType` are not available from yfinance and are excluded.

---

### 4. Dividend Yield Chart Data
Historical dividend yield data points for charting.

**Available Fields (per entry):**
- `date` - Date of the dividend (YYYY-MM-DD format)
- `yield` - Dividend yield percentage at that date
- `amount` - Dividend amount per share

---

### 5. Payout History Chart Data
Yearly dividend payout totals with growth calculations.

**Available Fields (per entry):**
- `year` - Year of the payout
- `payout` - Total annual payout amount per share
- `growth` - Year-over-year growth percentage (if applicable)
- `cagr` - Compound Annual Growth Rate (calculated for the first entry if enough data available)

---

### 6. Quick Stats
Summary statistics about dividends.

**Available Fields:**
- `frequency` - Dividend payment frequency (if available from yfinance)
- `lastPaymentDate` - Date of the most recent dividend payment
- `nextPaymentDate` - Date of the next scheduled dividend payment
- `currentPayout` - Current annual payout amount
- `yoyGrowth` - Year-over-year growth percentage
- `cagr` - Compound Annual Growth Rate (if available)

**Note:** Only fields with actual values are returned (null fields are excluded)

---

## Data Limitations

### Not Available from yfinance:
- **recordDate** - Record date for dividends
- **declareDate** - Declaration date for dividends
- **payoutType** - Cash vs Stock dividend type
- **sector_median** - Sector median dividend metrics

These fields are excluded from the response as they are not provided by yfinance.

---

## Example Response

```json
{
  "ticker": "AAPL",
  "dividendMetrics": {
    "dividend_yield": 0.005,
    "annual_payout": 0.96,
    "payout_ratio": 0.15,
    "growth_streak": 12,
    "eps": 6.11,
    "five_year_avg_yield": 0.0045
  },
  "upcomingPayouts": {
    "exDividendDate": "2026-01-12",
    "exDividendAmount": 2.76,
    "paymentDate": "2026-02-02",
    "daysUntilExDividend": 7,
    "daysUntilPayment": 28
  },
  "dividendHistory": [
    {
      "exDivDate": "2025-11-07",
      "amount": 0.24,
      "fiscalYear": 2025,
      "fiscalQuarter": 4
    }
  ],
  "yieldChartData": [
    {
      "date": "2025-11-07",
      "yield": 0.5,
      "amount": 0.24
    }
  ],
  "payoutChartData": [
    {
      "year": 2025,
      "payout": 0.96,
      "growth": 4.3,
      "cagr": 5.2
    }
  ],
  "quickStats": {
    "frequency": "Quarterly",
    "lastPaymentDate": "2025-11-07",
    "nextPaymentDate": "2026-02-02",
    "currentPayout": 0.96,
    "yoyGrowth": 4.3
  }
}
```

---

## Notes

- All data comes exclusively from **yfinance** (Yahoo Finance)
- Null/None values are excluded from the response
- Historical data is calculated from yfinance dividend history
- Growth streak is calculated from historical dividend data
- Only fields with actual values are included in each section


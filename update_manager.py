import asyncio
import logging
from typing import Optional  # Add this import
import yfinance as yf
import pandas as pd
import aiohttp
from datetime import datetime
from config import Settings
from database import MongoManager
from utils import clean_mongo_data

logger = logging.getLogger(__name__)


class UpdateManager:
    _update_task: Optional[asyncio.Task] = None
    _last_update: Optional[datetime] = None
    _is_updating: bool = False
    logger = logging.getLogger(__name__)

    @classmethod
    async def start_updates(cls):
        """Start the automatic update process"""
        if cls._update_task is None:
            cls._update_task = asyncio.create_task(cls._update_loop())
            cls.logger.info("Automated updates started")

    @classmethod
    async def stop_updates(cls):
        """Stop the automatic update process"""
        if cls._update_task:
            cls._update_task.cancel()
            try:
                await cls._update_task
            except asyncio.CancelledError:
                pass
            cls._update_task = None
            cls.logger.info("Automated updates stopped")

    @classmethod
    async def _update_loop(cls):
        """Main update loop that runs continuously"""
        while True:
            try:
                await cls.update_stock_data()
                await asyncio.sleep(Settings.UPDATE_INTERVAL)
            except Exception as e:
                cls.logger.error(f"Error in update loop: {str(e)}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying

    @classmethod
    async def _get_sp500_symbols(cls):
        """Fetch S&P 500 symbols asynchronously"""
        try:
            df = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')[0]
            return df['Symbol'].tolist()
        except Exception as e:
            cls.logger.error(f"Error fetching S&P 500 symbols: {str(e)}")
            return []

    @classmethod
    async def update_stock_data(cls):
        """Update stock data for all S&P 500 companies"""
        if cls._is_updating:
            return

        cls._is_updating = True
        try:
            # Get S&P 500 symbols
            symbols = await cls._get_sp500_symbols()
            cls.logger.info(f"Starting update for {len(symbols)} companies")

            # Get database connection
            db = await MongoManager.get_database()

            # Update each company
            async with aiohttp.ClientSession() as session:
                for symbol in symbols:
                    try:
                        data = await cls._fetch_stock_data(symbol, session)
                        if data:
                            await db.companies.update_one(
                                {"ticker": data["ticker"]},
                                {"$set": data},
                                upsert=True
                            )
                            cls.logger.info(f"Updated {symbol}")
                        await asyncio.sleep(1)  # Rate limiting
                    except Exception as e:
                        cls.logger.error(f"Error updating {symbol}: {str(e)}")

            cls._last_update = datetime.now()
            cls.logger.info("Stock data update completed")

        except Exception as e:
            cls.logger.error(f"Error in update process: {str(e)}")
        finally:
            cls._is_updating = False

    @classmethod
    async def _fetch_stock_data(cls, ticker: str, session: aiohttp.ClientSession):
        """Fetch stock data for a single company"""
        try:
            # Use yfinance for basic data
            stock = yf.Ticker(ticker)
            info = stock.info

            # Fetch additional data from Financial Modeling Prep
            fmp_url = f"https://financialmodelingprep.com/api/v3/quote/{ticker}?apikey={Settings.FMP_API_KEY}"
            async with session.get(fmp_url) as response:
                fmp_data = (await response.json())[0] if response.status == 200 else {}

            # Combine data from both sources
            data = {
                "ticker": ticker,
                "name": info.get('longName', ''),
                "sector": info.get('sector', ''),
                "industry": info.get('industry', ''),
                "market_cap": info.get('marketCap', 0),
                "exchange": info.get('exchange', ''),
                "country": info.get('country', ''),
                "currency": info.get('currency', 'USD'),
                
                # Quote data
                "quote": {
                    "price": fmp_data.get('price', info.get('currentPrice', 0)),
                    "change": fmp_data.get('change', 0),
                    "changesPercentage": fmp_data.get('changesPercentage', 0),
                    "volume": fmp_data.get('volume', info.get('volume', 0)),
                    "avgVolume": info.get('averageVolume', 0),
                    "previousClose": fmp_data.get('previousClose', info.get('previousClose', 0)),
                    "dayLow": fmp_data.get('dayLow', info.get('dayLow', 0)),
                    "dayHigh": fmp_data.get('dayHigh', info.get('dayHigh', 0)),
                    "yearLow": info.get('fiftyTwoWeekLow', 0),
                    "yearHigh": info.get('fiftyTwoWeekHigh', 0),
                    "marketCap": info.get('marketCap', 0),
                    "timestamp": datetime.now().isoformat()
                },

                # Key metrics
                "key_metrics": {
                    "pe_ratio": info.get('trailingPE', 0),
                    "forward_pe": info.get('forwardPE', 0),
                    "peg_ratio": info.get('pegRatio', 0),
                    "price_to_book": info.get('priceToBook', 0),
                    "price_to_sales": info.get('priceToSalesTrailing12Months', 0),
                    "beta": info.get('beta', 0),
                    "dividend_rate": info.get('dividendRate', 0),
                    "dividend_yield": info.get('dividendYield', 0) if info.get('dividendYield') else 0,
                },

                # Financial ratios (TTM)
                "ttm_ratios": {
                    "profit_margin": info.get('profitMargins', 0),
                    "operating_margin": info.get('operatingMargins', 0),
                    "roa": info.get('returnOnAssets', 0),
                    "roe": info.get('returnOnEquity', 0),
                    "revenue_growth": info.get('revenueGrowth', 0),
                    "earnings_growth": info.get('earningsGrowth', 0),
                },

                # Update timestamp
                "last_updated": datetime.now().isoformat()
            }

            # Clean any NaN or infinite values
            return clean_mongo_data(data)

        except Exception as e:
            cls.logger.error(f"Error fetching data for {ticker}: {str(e)}")
            return None
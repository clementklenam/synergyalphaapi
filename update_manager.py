import asyncio
import logging
from typing import Optional, Dict, Any
import yfinance as yf
import pandas as pd
import aiohttp
from datetime import datetime
from config import Settings
from database import MongoManager
from utils import clean_mongo_data
import base64 

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
            cls.logger.info("Automated updates started - running every %d seconds", Settings.UPDATE_INTERVAL)

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
                if not cls._is_updating:
                    cls.logger.info("Starting scheduled update")
                    await cls.update_stock_data()
                else:
                    cls.logger.info("Update already in progress, skipping this cycle")
                
                # Log when the next update will happen
                next_update = datetime.now().timestamp() + Settings.UPDATE_INTERVAL
                cls.logger.info(f"Next update scheduled at: {datetime.fromtimestamp(next_update).strftime('%Y-%m-%d %H:%M:%S')}")
                
                await asyncio.sleep(Settings.UPDATE_INTERVAL)
            except Exception as e:
                cls.logger.error(f"Error in update loop: {str(e)}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying if there's an error


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
    async def get_stock_logo(cls, symbol: str, session: aiohttp.ClientSession) -> Optional[str]:
        """Fetches the stock logo using logo.dev API"""
        try:
            url = f"https://img.logo.dev/ticker/{symbol.lower()}?token={Settings.LOGO_API_TOKEN}"
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    content = await response.read()
                    return base64.b64encode(content).decode('utf-8')
                logger.warning(f"Failed to fetch logo for {symbol} - Status code: {response.status}")
                return None
        except Exception as e:
            logger.error(f"Error fetching logo for {symbol}: {str(e)}")
            return None
    
    @classmethod
    async def _get_yf_data(cls, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch all other data from Yahoo Finance"""
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            
            # Extract and store officers data
            officers_data = []
            if 'officers' in info:
                for officer in info['officers']:
                    officer_info = {
                        'name': officer.get('name'),
                        'title': officer.get('title'),
                        'yearBorn': officer.get('yearBorn'),
                        'totalPay': officer.get('totalPay')
                    }
                    officers_data.append(officer_info)
                    
                    if officer.get('title', '').lower().replace(' ', '') in [
                        'chiefexecutiveofficer',
                        'ceo',
                        'chiefexecutiveofficer(ceo)',
                        'presidentandceo',
                        'ceoanddirector',
                        'chiefexecutive'
                    ]:
                        info['ceo'] = officer.get('name')
            
            return {
                "ticker": symbol,
                "price": info.get('currentPrice'),
                "beta": info.get('beta'),
                "volAvg": info.get('averageVolume'),
                "mktCap": info.get('marketCap'),
                "lastDiv": info.get('lastDividendValue'),
                "range": f"{info.get('fiftyTwoWeekLow', '')}-{info.get('fiftyTwoWeekHigh', '')}",
                "changes": info.get('regularMarketChangePercent'),
                "companyName": info.get('longName'),
                "currency": info.get('currency'),
                "cusip": info.get('cusip'),
                "exchange": info.get('exchange'),
                "industry": info.get('industry'),
                "website": info.get('website'),
                "description": info.get('longBusinessSummary'),
                "sector": info.get('sector'),
                "country": info.get('country'),
                "fullTimeEmployees": info.get('fullTimeEmployees'),
                "phone": info.get('phone'),
                "address": info.get('address1'),
                "city": info.get('city'),
                "state": info.get('state'),
                "zip": info.get('zip'),
                "ceo": info.get('ceo'),
                "officers": officers_data,
                "quote": {
                    "price": info.get('currentPrice'),
                    "change": info.get('regularMarketChange'),
                    "changesPercentage": info.get('regularMarketChangePercent'),
                    "volume": info.get('volume'),
                    "avgVolume": info.get('averageVolume'),
                    "previousClose": info.get('previousClose'),
                    "dayLow": info.get('dayLow'),
                    "dayHigh": info.get('dayHigh'),
                    "yearLow": info.get('fiftyTwoWeekLow'),
                    "yearHigh": info.get('fiftyTwoWeekHigh'),
                    "marketCap": info.get('marketCap'),
                    "timestamp": datetime.now().isoformat()
                },
                "key_metrics": {
                    "pe_ratio": info.get('trailingPE'),
                    "forward_pe": info.get('forwardPE'),
                    "peg_ratio": info.get('pegRatio'),
                    "price_to_book": info.get('priceToBook'),
                    "price_to_sales": info.get('priceToSalesTrailing12Months'),
                    "beta": info.get('beta'),
                    "dividend_rate": info.get('dividendRate'),
                    "dividend_yield": info.get('dividendYield'),
                },
                "ttm_ratios": {
                    "profit_margin": info.get('profitMargins'),
                    "operating_margin": info.get('operatingMargins'),
                    "roa": info.get('returnOnAssets'),
                    "roe": info.get('returnOnEquity'),
                    "revenue_growth": info.get('revenueGrowth'),
                    "earnings_growth": info.get('earningsGrowth'),
                }
            }
        except Exception as e:
            logger.error(f"Error getting Yahoo Finance data for {symbol}: {str(e)}")
            return None
        
    @classmethod
    async def get_finnhub_data(cls, symbol: str, session: aiohttp.ClientSession) -> Optional[Dict[str, Any]]:
        """Fetches data from Finnhub API"""
        try:
            # Company Profile
            profile_url = f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}&token={Settings.FINNHUB_API_KEY}"
            quote_url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={Settings.FINNHUB_API_KEY}"
            metrics_url = f"https://finnhub.io/api/v1/stock/metric?symbol={symbol}&metric=all&token={Settings.FINNHUB_API_KEY}"
            
            # Fetch data concurrently
            async with session.get(profile_url) as profile_response, \
                      session.get(quote_url) as quote_response, \
                      session.get(metrics_url) as metrics_response:
                
                if all(resp.status == 200 for resp in [profile_response, quote_response, metrics_response]):
                    profile_data = await profile_response.json()
                    quote_data = await quote_response.json()
                    metrics_data = await metrics_response.json()
                    
                    if profile_data and quote_data and metrics_data.get('metric'):
                        metrics = metrics_data['metric']
                        
                        return {
                            "price": quote_data.get('c'),  # Current price
                            "beta": metrics.get('beta'),
                            "volAvg": metrics.get('vol10DayAvg'),
                            "mktCap": profile_data.get('marketCapitalization'),
                            "lastDiv": metrics.get('lastDividendValue'),
                            "changes": quote_data.get('dp'),  # Daily percentage change
                            "companyName": profile_data.get('name'),
                            "currency": profile_data.get('currency'),
                            "cusip": profile_data.get('cusip'),
                            "exchange": profile_data.get('exchange'),
                            "industry": profile_data.get('finnhubIndustry'),
                            "website": profile_data.get('weburl'),
                            "description": profile_data.get('description'),
                            "sector": metrics.get('sector'),
                            "country": profile_data.get('country'),
                            "phone": profile_data.get('phone'),
                            "address": profile_data.get('address'),
                            "city": profile_data.get('city'),
                            "state": profile_data.get('state'),
                            "zip": profile_data.get('zip')
                        }
            logger.warning(f"Failed to fetch complete Finnhub data for {symbol}")
            return None
        except Exception as e:
            logger.error(f"Error fetching Finnhub data for {symbol}: {str(e)}")
            return None

    @classmethod
    async def process_single_stock(cls, symbol: str, session: aiohttp.ClientSession) -> Optional[Dict[str, Any]]:
        """Process a single stock symbol using Yahoo Finance and Finnhub data"""
        try:
            # Fetch data from sources concurrently
            yf_task = asyncio.create_task(cls._get_yf_data(symbol))
            finnhub_task = asyncio.create_task(cls.get_finnhub_data(symbol, session))
            logo_task = asyncio.create_task(cls.get_stock_logo(symbol, session))
            
            # Await all tasks
            yf_info = await yf_task
            finnhub_info = await finnhub_task
            logo = await logo_task
            
            if not yf_info:
                yf_info = {}
            if not finnhub_info:
                finnhub_info = {}
            
            # Helper function to get first non-None value
            def get_first_value(*args):
                for arg in args:
                    if arg is not None:
                        return arg
                return None
            
            # Combine data from all sources
            combined_data = {
                "ticker": symbol,
                "price": get_first_value(yf_info.get('price'), finnhub_info.get('price')),
                "beta": get_first_value(yf_info.get('beta'), finnhub_info.get('beta')),
                "volAvg": get_first_value(yf_info.get('volAvg'), finnhub_info.get('volAvg')),
                "mktCap": get_first_value(yf_info.get('mktCap'), finnhub_info.get('mktCap')),
                "lastDiv": get_first_value(yf_info.get('lastDiv'), finnhub_info.get('lastDiv')),
                "range": yf_info.get('range'),
                "changes": get_first_value(yf_info.get('changes'), finnhub_info.get('changes')),
                "companyName": get_first_value(yf_info.get('companyName'), finnhub_info.get('companyName')),
                "currency": get_first_value(yf_info.get('currency'), finnhub_info.get('currency'), 'USD'),
                "cusip": get_first_value(yf_info.get('cusip'), finnhub_info.get('cusip')),
                "exchange": get_first_value(yf_info.get('exchange'), finnhub_info.get('exchange')),
                "industry": get_first_value(yf_info.get('industry'), finnhub_info.get('industry')),
                "website": get_first_value(yf_info.get('website'), finnhub_info.get('website')),
                "description": get_first_value(yf_info.get('description'), finnhub_info.get('description')),
                "sector": get_first_value(yf_info.get('sector'), finnhub_info.get('sector')),
                "country": get_first_value(yf_info.get('country'), finnhub_info.get('country')),
                "fullTimeEmployees": yf_info.get('fullTimeEmployees'),
                "ceo": yf_info.get('ceo'),
                "officers": yf_info.get('officers'),
                "phone": get_first_value(yf_info.get('phone'), finnhub_info.get('phone')),
                "address": get_first_value(yf_info.get('address'), finnhub_info.get('address')),
                "city": get_first_value(yf_info.get('city'), finnhub_info.get('city')),
                "state": get_first_value(yf_info.get('state'), finnhub_info.get('state')),
                "zip": get_first_value(yf_info.get('zip'), finnhub_info.get('zip')),
                "image": logo,
                "quote": yf_info.get('quote', {}),
                "key_metrics": yf_info.get('key_metrics', {}),
                "ttm_ratios": yf_info.get('ttm_ratios', {}),
                "last_updated": datetime.now()
            }
            
            # Remove None values to keep data clean
            combined_data = {k: v for k, v in combined_data.items() if v is not None}
            
            return combined_data if len(combined_data) > 5 else None
                
        except Exception as e:
            logger.error(f"Error processing {symbol}: {str(e)}")
            return None
           
    @classmethod
    async def update_stock_data(cls):
        """Update stock data for all S&P 500 companies"""
        if cls._is_updating:
            cls.logger.warning("Update already in progress, skipping this request")
            return

        cls._is_updating = True
        update_start_time = datetime.now()
        try:
            # Get S&P 500 symbols
            symbols = await cls._get_sp500_symbols()
            
            # For testing with shorter update times, you might want to limit the companies
            # Uncomment the next line to use only the first 50 companies for testing
            # symbols = symbols[:50]
            
            cls.logger.info(f"Starting update for {len(symbols)} companies")

            # Get database connection
            db = await MongoManager.get_database()

            # Update each company
            async with aiohttp.ClientSession() as session:
                # For testing, add a counter to track progress
                updated_count = 0
                
                for symbol in symbols:
                    try:
                        data = await cls.process_single_stock(symbol, session)
                        if data:
                            await db.companies.update_one(
                                {"ticker": data["ticker"]},
                                {"$set": data},
                                upsert=True
                            )
                            updated_count += 1
                            if updated_count % 10 == 0:  # Log every 10 companies
                                cls.logger.info(f"Updated {updated_count}/{len(symbols)} companies")
                        else:
                            cls.logger.warning(f"No data returned for {symbol}")
                        
                        # Rate limiting - be nice to the APIs
                        await asyncio.sleep(0.5)
                        
                    except Exception as e:
                        cls.logger.error(f"Error updating {symbol}: {str(e)}")

            update_duration = (datetime.now() - update_start_time).total_seconds()
            cls._last_update = datetime.now()
            cls.logger.info(f"Stock data update completed in {update_duration:.2f} seconds. Updated {updated_count} companies.")

        except Exception as e:
            cls.logger.error(f"Error in update process: {str(e)}")
        finally:
            cls._is_updating = False

    @classmethod
    async def _fetch_stock_data(cls, ticker: str, session: aiohttp.ClientSession):
        """Fetch stock data for a single company"""
        try:
            # Use yfinance for all data
            stock = yf.Ticker(ticker)
            info = stock.info

            # Combine data
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
                    "price": info.get('currentPrice', 0),
                    "change": info.get('regularMarketChange', 0),
                    "changesPercentage": info.get('regularMarketChangePercent', 0),
                    "volume": info.get('volume', 0),
                    "avgVolume": info.get('averageVolume', 0),
                    "previousClose": info.get('previousClose', 0),
                    "dayLow": info.get('dayLow', 0),
                    "dayHigh": info.get('dayHigh', 0),
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
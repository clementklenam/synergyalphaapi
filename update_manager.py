import asyncio
import logging
from typing import Optional, Dict, Any, List
import yfinance as yf
import pandas as pd
import aiohttp
from datetime import datetime, time, timedelta 
import time as time_module
from pydantic import BaseModel
import base64
import json
import pytz
from settings import Settings, settings
from database import MongoManager
from utils import clean_mongo_data
from yfinance.exceptions import YFRateLimitError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import random

# Configure root logger to see all logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StockData(BaseModel):
    ticker: str
    price: Optional[float] = None
    beta: Optional[float] = None
    volAvg: Optional[int] = None
    mktCap: Optional[float] = None  # Changed from int to float
    lastDiv: Optional[float] = None
    range: Optional[str] = None
    changes: Optional[float] = None
    companyName: Optional[str] = None
    currency: Optional[str] = None
    cusip: Optional[str] = None
    exchange: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    sector: Optional[str] = None
    country: Optional[str] = None
    fullTimeEmployees: Optional[int] = None
    ceo: Optional[str] = None
    officers: Optional[List[Dict[str, Any]]] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    image: Optional[str] = None
    quote: Optional[Dict[str, Any]] = None
    key_metrics: Optional[Dict[str, Any]] = None
    ttm_ratios: Optional[Dict[str, Any]] = None
    financial_statements: Optional[Dict[str, Any]] = None
    last_updated: Optional[datetime] = None
    market_status: Optional[str] = None
    financial_data_hash: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True



class MarketStatus:
    CLOSED = "closed"
    OPEN = "open"
    PRE_MARKET = "pre_market"
    AFTER_HOURS = "after_hours"


class UpdateManager:
    
    
    _semaphore = asyncio.Semaphore(2)  # Limit concurrent requests
    _last_request_time = {}  # Track last request time per symbol
    MIN_REQUEST_INTERVAL = 2.0  # Minimum seconds between requests per symbol
    
    
    _update_task: Optional[asyncio.Task] = None
    _last_check: Optional[datetime] = None
    _is_updating: bool = False
    _market_status: str = MarketStatus.CLOSED
    _force_refresh_symbols: List[str] = []
    logger = logging.getLogger(__name__)

    @classmethod
    async def start_updates(cls):
        """Start the automatic update check process"""
        if cls._update_task is None:
            cls._update_task = asyncio.create_task(cls._update_loop())
            cls.logger.info("Automated update checks started - running every %d seconds", Settings.CHECK_INTERVAL)
            
    @classmethod
    async def update_stock_data(cls, symbols=None):
        """Update stock data for specified symbols or all SP500 symbols"""
        try:
            if symbols is None:
                symbols = await cls._get_sp500_symbols()
                cls.logger.info(f"Fetched {len(symbols)} SP500 symbols for update")
            await cls._process_updates(symbols)
        except Exception as e:
            cls.logger.error(f"Error updating stock data: {str(e)}")

    @classmethod
    async def stop_updates(cls):
        """Stop the automatic update check process"""
        if cls._update_task:
            cls._update_task.cancel()
            try:
                await cls._update_task
            except asyncio.CancelledError:
                pass
            cls._update_task = None
            cls.logger.info("Automated update checks stopped")

    @classmethod
    async def force_update(cls, symbols: List[str]):
        """Force update for specific symbols, bypassing checking"""
        cls._force_refresh_symbols.extend(symbols)
        cls.logger.info(f"Scheduled forced update for symbols: {symbols}")
    
    @classmethod
    async def _update_loop(cls):
        """Main update loop that runs continuously, checking for new data"""
        cls.logger.info("Update loop started")
        
        while True:
            try:
                # Update market status at the beginning of each loop
                cls._market_status = await cls._get_current_market_status()
                cls.logger.info(f"Current market status: {cls._market_status}")
                
                # If we have forced update symbols, process them immediately
                if cls._force_refresh_symbols:
                    forced_symbols = cls._force_refresh_symbols.copy()
                    cls._force_refresh_symbols = []
                    cls.logger.info(f"Processing forced update for {len(forced_symbols)} symbols")
                    await cls._process_updates(forced_symbols)
                    
                # Check for new data based on current market status
                symbols_needing_update = []
                all_symbols = await cls._get_sp500_symbols()
                cls.logger.info(f"Fetched {len(all_symbols)} SP500 symbols for checking")
                
                # Get DB connection once for the batch
                db = await MongoManager.get_database()
                
                async with aiohttp.ClientSession() as session:
                    for symbol in all_symbols[:10]:  # Limit to 10 symbols for testing
                        db_data = await cls._get_company_data(symbol, db)
                        has_updates = await cls._check_symbol_for_updates(symbol, db_data, session)
                        if has_updates:
                            symbols_needing_update.append(symbol)
                            cls.logger.info(f"Symbol {symbol} needs update")
                
                if symbols_needing_update:
                    cls.logger.info(f"Found {len(symbols_needing_update)} symbols with new data")
                    await cls._process_updates(symbols_needing_update)
                else:
                    cls.logger.info("No new data available, skipping update")

                # Update last check time
                cls._last_check = datetime.now()
                
                # Adjust sleep interval based on market status
                sleep_interval = cls._get_adjusted_interval()
                next_check = datetime.now() + timedelta(seconds=sleep_interval)
                cls.logger.info(f"Next data check scheduled at: {next_check.strftime('%Y-%m-%d %H:%M:%S')}")
                await asyncio.sleep(sleep_interval)

            except Exception as e:
                cls.logger.error(f"Error in update loop: {str(e)}", exc_info=True)
                await asyncio.sleep(60)  # Wait 1 minute before retrying

    

    @classmethod
    async def _check_symbol_for_updates(cls, symbol: str, db_data: Optional[Dict], session: aiohttp.ClientSession) -> bool:
        """Check if a symbol has new data available from any source"""
        try:
            # Handle case where symbol doesn't exist in DB
            if not db_data:
                cls.logger.info(f"Symbol {symbol} not found in database, scheduling update")
                return True
            
            # Get latest data timestamp from DB
            db_timestamp = db_data.get('last_updated')
            if not db_timestamp:
                cls.logger.info(f"No last_updated timestamp for {symbol}, scheduling update")
                return True
            
            if isinstance(db_timestamp, str):
                db_timestamp = datetime.fromisoformat(db_timestamp.replace('Z', '+00:00'))
            
            # Determine time-based update strategy based on market status
            time_since_update = (datetime.now() - db_timestamp).total_seconds()
            
            # Update strategy based on market status
            if cls._market_status == MarketStatus.CLOSED:
                # During closed market, update once per day (86400 seconds)
                if time_since_update < 86400 and db_data.get('market_status') == MarketStatus.CLOSED:
                    return False
                else:
                    cls.logger.info(f"Symbol {symbol} last updated {time_since_update:.0f}s ago during closed market, scheduling update")
                    return True
            elif cls._market_status == MarketStatus.PRE_MARKET:
                # During pre-market, update more frequently (every 15 minutes)
                if time_since_update < 900:
                    return False
                else:
                    cls.logger.info(f"Symbol {symbol} last updated {time_since_update:.0f}s ago during pre-market, scheduling update")
                    return True
            elif cls._market_status == MarketStatus.OPEN:
                # During open market, check for price and volume changes
                if time_since_update < 300:  # At least 5 minutes between checks
                    return False
                
                # Check for price changes from Yahoo Finance
                try:
                    ticker = yf.Ticker(symbol)
                    latest_data = ticker.history(period="1d", interval="1m", prepost=True)
                    if not latest_data.empty:
                        latest_price = latest_data['Close'].iloc[-1]
                        latest_volume = latest_data['Volume'].iloc[-1]
                        db_price = db_data.get('price')
                        db_volume = db_data.get('quote', {}).get('volume')
                        
                        # Only compare if we have valid data
                        if db_price and db_volume and latest_price and latest_volume:
                            # Update if price changed by more than 0.1% or volume increased by 5%
                            if (abs((latest_price - db_price) / db_price) > 0.001 or
                                (latest_volume > db_volume * 1.05)):
                                cls.logger.info(f"{symbol} has significant price/volume change")
                                return True
                        else:
                            cls.logger.info(f"{symbol} missing price or volume data, scheduling update")
                            return True
                    else:
                        cls.logger.warning(f"Empty history data for {symbol}, scheduling update")
                        return True
                except Exception as e:
                    cls.logger.warning(f"Error checking Yahoo Finance data for {symbol}: {str(e)}")
                    return True  # Schedule update if we can't check the data
            
            elif cls._market_status == MarketStatus.AFTER_HOURS:
                # During after-hours, update less frequently (every 30 minutes)
                if time_since_update < 1800:
                    return False
                else:
                    cls.logger.info(f"Symbol {symbol} last updated {time_since_update:.0f}s ago during after-hours, scheduling update")
                    return True
            
            # Check for financial statement updates by comparing hashes
            try:
                ticker = yf.Ticker(symbol)
                
                # Get current financial statements safely
                income_annual = ticker.income_stmt.to_dict() if not ticker.income_stmt.empty else {}
                income_quarterly = ticker.quarterly_income_stmt.to_dict() if not ticker.quarterly_income_stmt.empty else {}
                balance_annual = ticker.balance_sheet.to_dict() if not ticker.balance_sheet.empty else {}
                balance_quarterly = ticker.quarterly_balance_sheet.to_dict() if not ticker.quarterly_balance_sheet.empty else {}
                cashflow_annual = ticker.cashflow.to_dict() if not ticker.cashflow.empty else {}
                cashflow_quarterly = ticker.quarterly_cashflow.to_dict() if not ticker.quarterly_cashflow.empty else {}
                
                # Get current financial statements if they exist
                financial_data = {
                    "income_statement": {
                        "annual": clean_mongo_data(income_annual),
                        "quarterly": clean_mongo_data(income_quarterly)
                    },
                    "balance_sheet": {
                        "annual": clean_mongo_data(balance_annual),
                        "quarterly": clean_mongo_data(balance_quarterly)
                    },
                    "cash_flow_statement": {
                        "annual": clean_mongo_data(cashflow_annual),
                        "quarterly": clean_mongo_data(cashflow_quarterly)
                    }
                }
                
                # Only generate hash if we have actual data
                all_empty = (
                    not income_annual and not income_quarterly and
                    not balance_annual and not balance_quarterly and
                    not cashflow_annual and not cashflow_quarterly
                )
                
                if not all_empty:
                    # Generate a hash from the financial data
                    financial_data_str = json.dumps(financial_data, sort_keys=True)
                    financial_data_hash = base64.b64encode(financial_data_str.encode()).decode()
                    
                    # Compare with stored hash
                    if financial_data_hash != db_data.get('financial_data_hash'):
                        cls.logger.info(f"{symbol} has new financial statement data")
                        return True
                else:
                    cls.logger.warning(f"No financial data available for {symbol}")
                    
            except Exception as e:
                cls.logger.warning(f"Error checking financial data for {symbol}: {str(e)}")
            
            # Check if market status changed
            if db_data.get('market_status') != cls._market_status:
                cls.logger.info(f"{symbol} market status changed from {db_data.get('market_status')} to {cls._market_status}")
                return True
            
            # Check logo
            if not db_data.get('image'):
                cls.logger.info(f"{symbol} needs logo")
                return True
                
            return False
            
        except Exception as e:
            cls.logger.error(f"Error checking updates for {symbol}: {str(e)}", exc_info=True)
            # Default to return True to be safe
            return True

    @classmethod
    async def _get_current_market_status(cls) -> str:
        """
        Check current market status: pre-market, open, after-hours, or closed
        """
        try:
            # Get current time in US Eastern timezone
            eastern = pytz.timezone('US/Eastern')
            now = datetime.now(eastern)
            current_time = now.time()
            current_day = now.weekday()
            
            # Check if it's a weekend
            if current_day >= 5:  # Saturday or Sunday
                return MarketStatus.CLOSED
                
            # Regular market hours: 9:30 AM - 4:00 PM ET, Monday-Friday
            market_open = time(9, 30, 0)
            market_close = time(16, 0, 0)
            
            # Pre-market hours: 4:00 AM - 9:30 AM ET
            pre_market_open = time(4, 0, 0)
            
            # After-hours: 4:00 PM - 8:00 PM ET
            after_hours_close = time(20, 0, 0)
            
            if pre_market_open <= current_time < market_open:
                return MarketStatus.PRE_MARKET
            elif market_open <= current_time < market_close:
                return MarketStatus.OPEN
            elif market_close <= current_time < after_hours_close:
                return MarketStatus.AFTER_HOURS
            else:
                return MarketStatus.CLOSED
                
        except Exception as e:
            cls.logger.error(f"Error determining market status: {str(e)}")
            return MarketStatus.CLOSED
    
    @classmethod
    def _get_adjusted_interval(cls) -> int:
        """Get adjusted check interval based on market status"""
        if cls._market_status == MarketStatus.OPEN:
            return Settings.CHECK_INTERVAL  # Default interval during market hours
        elif cls._market_status == MarketStatus.PRE_MARKET:
            return Settings.CHECK_INTERVAL * 2  # Check less frequently during pre-market
        elif cls._market_status == MarketStatus.AFTER_HOURS:
            return Settings.CHECK_INTERVAL * 3  # Check even less frequently after hours
        else:  # CLOSED
            return Settings.CHECK_INTERVAL * 6  # Check much less frequently when market closed
    
    @classmethod
    async def _get_sp500_symbols(cls):
        """Fetch S&P 500 symbols asynchronously"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies') as response:
                    if response.status == 200:
                        html = await response.text()
                        # Use StringIO to avoid FutureWarning
                        from io import StringIO
                        df = pd.read_html(StringIO(html))[0]
                        return df['Symbol'].tolist()
            # Fallback to direct pandas if aiohttp fails
            from io import StringIO
            import requests
            html = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies').text
            df = pd.read_html(StringIO(html))[0]
            return df['Symbol'].tolist()
        except Exception as e:
            cls.logger.error(f"Error fetching S&P 500 symbols: {str(e)}")
            # Return a small set of symbols for testing if fetching fails
            return ['AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META']

    @classmethod
    async def _get_company_data(cls, symbol: str, db) -> Optional[Dict]:
        """Get existing company data from database"""
        try:
            data = await db.companies.find_one({"ticker": symbol})
            if data:
                cls.logger.debug(f"Retrieved company data for {symbol} from database")
            else:
                cls.logger.info(f"No company data found for {symbol} in database")
            return data
        except Exception as e:
            cls.logger.error(f"Error getting company data for {symbol}: {str(e)}")
            return None

    @classmethod
    async def get_stock_logo(cls, symbol: str, session: aiohttp.ClientSession) -> Optional[str]:
        """Fetches the stock logo using logo.dev API"""
        try:
            url = f"https://img.logo.dev/ticker/{symbol.lower()}?token={settings.LOGO_API_TOKEN}"
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    content = await response.read()
                    return base64.b64encode(content).decode('utf-8')
                cls.logger.warning(f"Failed to fetch logo for {symbol} - Status code: {response.status}")
                return None
        except Exception as e:
            cls.logger.error(f"Error fetching logo for {symbol}: {str(e)}")
            return None
    
    
    @classmethod
    async def _process_updates(cls, symbols: List[str]):
        """Process updates for a list of symbols"""
        if cls._is_updating:
            cls.logger.warning("Update already in progress, queuing symbols for next run")
            cls._force_refresh_symbols.extend(symbols)
            return
        
        cls._is_updating = True
        successful_updates = 0
        failed_updates = 0
        
        try:
            cls.logger.info(f"Processing updates for {len(symbols)} symbols")
            async with aiohttp.ClientSession() as session:
                # Process in smaller batches
                batch_size = 3  # Reduced batch size
                for i in range(0, len(symbols), batch_size):
                    batch_symbols = symbols[i:i+batch_size]
                    
                    # Process batch concurrently with rate limiting
                    tasks = []
                    for symbol in batch_symbols:
                        # Ensure minimum time between requests for same symbol
                        last_request = cls._last_request_time.get(symbol, 0)
                        current_time = time_module.time()  # Use renamed time module
                        if current_time - last_request < cls.MIN_REQUEST_INTERVAL:
                            await asyncio.sleep(cls.MIN_REQUEST_INTERVAL - (current_time - last_request))
                        
                        cls._last_request_time[symbol] = current_time
                        
                        # Create task with semaphore
                        async with cls._semaphore:
                            task = asyncio.create_task(cls.process_single_stock(symbol, session))
                            tasks.append((symbol, task))
                    
                    # Wait for batch to complete
                    for symbol, task in tasks:
                        try:
                            result = await task
                            if result:
                                try:
                                    await MongoManager.update_company_data(symbol, result)
                                    cls.logger.info(f"Successfully updated {symbol}")
                                    successful_updates += 1
                                except Exception as e:
                                    cls.logger.error(f"Error saving data for {symbol}: {str(e)}")
                                    failed_updates += 1
                            else:
                                cls.logger.warning(f"No data returned for {symbol}")
                                failed_updates += 1
                        except Exception as e:
                            cls.logger.error(f"Failed to update {symbol}: {str(e)}")
                            failed_updates += 1
                    
                    # Add delay between batches
                    await asyncio.sleep(random.uniform(5, 8))  # Increased delay
                
                cls.logger.info(f"Completed updates: {successful_updates} successful, {failed_updates} failed")
        
        except Exception as e:
            cls.logger.error(f"Error processing updates: {str(e)}", exc_info=True)
        finally:
            cls._is_updating = False

    @classmethod
    @retry(
    retry=retry_if_exception_type(YFRateLimitError),
    wait=wait_exponential(multiplier=5, min=10, max=300),  # Increased wait times
    stop=stop_after_attempt(5)  # Increased attempts
    )
    async def _get_yf_data(cls, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch all other data from Yahoo Finance including financial statements"""
        try:
            await asyncio.sleep(random.uniform(0.5, 2.0))
            stock = yf.Ticker(symbol)
            
            try:
                info = stock.info
            except YFRateLimitError:
                raise  # Re-raise rate limit errors for retry
            except Exception as e:
                cls.logger.error(f"Error getting info for {symbol}: {str(e)}")
                return None
            
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
            
            # Get financial statements safely
            income_annual = stock.income_stmt.to_dict() if not stock.income_stmt.empty else {}
            income_quarterly = stock.quarterly_income_stmt.to_dict() if not stock.quarterly_income_stmt.empty else {}
            balance_annual = stock.balance_sheet.to_dict() if not stock.balance_sheet.empty else {}
            balance_quarterly = stock.quarterly_balance_sheet.to_dict() if not stock.quarterly_balance_sheet.empty else {}
            cashflow_annual = stock.cashflow.to_dict() if not stock.cashflow.empty else {}
            cashflow_quarterly = stock.quarterly_cashflow.to_dict() if not stock.quarterly_cashflow.empty else {}
            
            # Get financial statements
            financial_statements = {
                "income_statement": {
                    "annual": clean_mongo_data(income_annual),
                    "quarterly": clean_mongo_data(income_quarterly)
                },
                "balance_sheet": {
                    "annual": clean_mongo_data(balance_annual),
                    "quarterly": clean_mongo_data(balance_quarterly)
                },
                "cash_flow_statement": {
                    "annual": clean_mongo_data(cashflow_annual),
                    "quarterly": clean_mongo_data(cashflow_quarterly)
                }
            }
            
            # Generate a hash from the financial data for future comparison
            financial_data_str = json.dumps(financial_statements, sort_keys=True)
            financial_data_hash = base64.b64encode(financial_data_str.encode()).decode()
            
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
                "financial_statements": financial_statements,
                "financial_data_hash": financial_data_hash,
                "market_status": cls._market_status,
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
        except YFRateLimitError:
            raise  # Re-raise rate limit errors for retry
        except Exception as e:
            cls.logger.error(f"Error getting Yahoo Finance data for {symbol}: {str(e)}")
            return None
    
    @classmethod
    async def get_finnhub_data(cls, symbol: str, session: aiohttp.ClientSession) -> Optional[Dict[str, Any]]:
        """Fetches data from Finnhub API"""
        try:
            # Company Profile
            profile_url = f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}&token={settings.FINNHUB_API_KEY}"
            quote_url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={settings.FINNHUB_API_KEY}"
            metrics_url = f"https://finnhub.io/api/v1/stock/metric?symbol={symbol}&metric=all&token={settings.FINNHUB_API_KEY}"
            
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
            cls.logger.warning(f"Failed to fetch complete Finnhub data for {symbol}")
            return None
        except Exception as e:
            cls.logger.error(f"Error fetching Finnhub data for {symbol}: {str(e)}")
            return None

    # First, modify process_single_stock to be a regular async method instead of a classmethod
    @classmethod
    @retry(
    retry=retry_if_exception_type(YFRateLimitError),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(3)
    )
    async def process_single_stock(cls, symbol: str, session: aiohttp.ClientSession) -> Optional[Dict[str, Any]]:
        """Process a single stock symbol using Yahoo Finance and Finnhub data."""
        try:
            # Get data from different sources with proper error handling
            yf_data = None
            finnhub_data = None
            logo = None

            try:
                yf_data = await cls._get_yf_data(symbol)
            except YFRateLimitError:
                # Re-raise YFRateLimitError to trigger retry
                raise
            except Exception as e:
                cls.logger.error(f"Error getting Yahoo Finance data for {symbol}: {str(e)}")

            try:
                finnhub_data = await cls.get_finnhub_data(symbol, session)
            except Exception as e:
                cls.logger.error(f"Error getting Finnhub data for {symbol}: {str(e)}")

            try:
                logo = await cls.get_stock_logo(symbol, session)
            except Exception as e:
                cls.logger.error(f"Error getting logo for {symbol}: {str(e)}")

            # If both data sources failed, return None
            if yf_data is None and finnhub_data is None:
                cls.logger.warning(f"No data available for {symbol} from any source")
                return None

            # Initialize yf_data if it's None to avoid attribute errors
            if yf_data is None:
                yf_data = {}

            # Helper function
            def get_first_value(*args):
                return next((arg for arg in args if arg is not None), None)

            def ensure_type(value, target_type):
                if value is None:
                    return None
                try:
                    if target_type == int and isinstance(value, float):
                        return int(value)
                    return target_type(value)
                except (ValueError, TypeError):
                    cls.logger.warning(f"Type conversion error: cannot convert {value} to {target_type.__name__}")
                    return None

            # Combine data from all sources
            combined_data = {
                "ticker": symbol,
                "price": get_first_value(yf_data.get('price'), finnhub_data.get('price') if finnhub_data else None),
                "beta": get_first_value(yf_data.get('beta'), finnhub_data.get('beta') if finnhub_data else None),
                "volAvg": ensure_type(get_first_value(
                    yf_data.get('volAvg'), 
                    finnhub_data.get('volAvg') if finnhub_data else None
                ), int),
                "mktCap": get_first_value(yf_data.get('mktCap'), finnhub_data.get('mktCap') if finnhub_data else None),
                "lastDiv": get_first_value(yf_data.get('lastDiv'), finnhub_data.get('lastDiv') if finnhub_data else None),
                "range": yf_data.get('range'),
                "changes": get_first_value(yf_data.get('changes'), finnhub_data.get('changes') if finnhub_data else None),
                "companyName": get_first_value(
                    yf_data.get('companyName'), 
                    finnhub_data.get('companyName') if finnhub_data else None
                ),
                "currency": get_first_value(
                    yf_data.get('currency'), 
                    finnhub_data.get('currency') if finnhub_data else None,
                    'USD'
                ),
                "cusip": get_first_value(yf_data.get('cusip'), finnhub_data.get('cusip') if finnhub_data else None),
                "exchange": get_first_value(
                    yf_data.get('exchange'), 
                    finnhub_data.get('exchange') if finnhub_data else None
                ),
                "industry": get_first_value(
                    yf_data.get('industry'), 
                    finnhub_data.get('industry') if finnhub_data else None
                ),
                "website": get_first_value(yf_data.get('website'), finnhub_data.get('website') if finnhub_data else None),
                "description": get_first_value(
                    yf_data.get('description'), 
                    finnhub_data.get('description') if finnhub_data else None
                ),
                "sector": get_first_value(yf_data.get('sector'), finnhub_data.get('sector') if finnhub_data else None),
                "country": get_first_value(yf_data.get('country'), finnhub_data.get('country') if finnhub_data else None),
                "fullTimeEmployees": ensure_type(yf_data.get('fullTimeEmployees'), int),
                "ceo": yf_data.get('ceo'),
                "officers": yf_data.get('officers'),
                "phone": get_first_value(yf_data.get('phone'), finnhub_data.get('phone') if finnhub_data else None),
                "address": get_first_value(yf_data.get('address'), finnhub_data.get('address') if finnhub_data else None),
                "city": get_first_value(yf_data.get('city'), finnhub_data.get('city') if finnhub_data else None),
                "state": get_first_value(yf_data.get('state'), finnhub_data.get('state') if finnhub_data else None),
                "zip": get_first_value(yf_data.get('zip'), finnhub_data.get('zip') if finnhub_data else None),
                "image": logo,
                "quote": {
                    "price": get_first_value(
                        yf_data.get('price'), 
                        finnhub_data.get('price') if finnhub_data else None
                    ),
                    "change": yf_data.get('quote', {}).get('change'),
                    "changesPercentage": yf_data.get('quote', {}).get('changesPercentage'),
                    "volume": yf_data.get('quote', {}).get('volume'),
                    "avgVolume": yf_data.get('quote', {}).get('avgVolume'),
                    "previousClose": yf_data.get('quote', {}).get('previousClose'),
                    "dayLow": yf_data.get('quote', {}).get('dayLow'),
                    "dayHigh": yf_data.get('quote', {}).get('dayHigh'),
                    "yearLow": yf_data.get('quote', {}).get('yearLow'),
                    "yearHigh": yf_data.get('quote', {}).get('yearHigh'),
                    "marketCap": yf_data.get('quote', {}).get('marketCap'),
                    "timestamp": datetime.now().isoformat()
                },
                "key_metrics": {
                    "pe_ratio": yf_data.get('key_metrics', {}).get('pe_ratio'),
                    "forward_pe": yf_data.get('key_metrics', {}).get('forward_pe'),
                    "peg_ratio": yf_data.get('key_metrics', {}).get('peg_ratio'),
                    "price_to_book": yf_data.get('key_metrics', {}).get('price_to_book'),
                    "price_to_sales": yf_data.get('key_metrics', {}).get('price_to_sales'),
                    "beta": yf_data.get('key_metrics', {}).get('beta'),
                    "dividend_rate": yf_data.get('key_metrics', {}).get('dividend_rate'),
                    "dividend_yield": yf_data.get('key_metrics', {}).get('dividend_yield')
                },
                "ttm_ratios": {
                    "profit_margin": yf_data.get('ttm_ratios', {}).get('profit_margin'),
                    "operating_margin": yf_data.get('ttm_ratios', {}).get('operating_margin'),
                    "roa": yf_data.get('ttm_ratios', {}).get('roa'),
                    "roe": yf_data.get('ttm_ratios', {}).get('roe'),
                    "revenue_growth": yf_data.get('ttm_ratios', {}).get('revenue_growth'),
                    "earnings_growth": yf_data.get('ttm_ratios', {}).get('earnings_growth')
                },
                "financial_statements": yf_data.get('financial_statements', {}),
                "financial_data_hash": yf_data.get('financial_data_hash'),
                "market_status": cls._market_status,
                "last_updated": datetime.now()
            }
            
            # Remove None values
            combined_data = {k: v for k, v in combined_data.items() if v is not None}

            # Make sure we have at least some basic data
            required_fields = ["ticker", "price", "companyName"]
            if not all(field in combined_data for field in required_fields):
                if "ticker" in combined_data and any(field in combined_data for field in required_fields[1:]):
                    # At least we have ticker and one other required field, continue
                    pass
                else:
                    cls.logger.warning(f"Insufficient data for {symbol}, missing required fields")
                    return None

            return combined_data if len(combined_data) > 5 else None

        except Exception as e:
            cls.logger.error(f"Error processing {symbol}: {str(e)}")
            return None
        
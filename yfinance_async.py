"""
Async wrapper for yfinance to prevent blocking the event loop.
Uses ThreadPoolExecutor to run synchronous yfinance calls in separate threads.
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any
import yfinance as yf
import pandas as pd
from yfinance.exceptions import YFRateLimitError

logger = logging.getLogger(__name__)

# Create a thread pool executor for yfinance calls
_yfinance_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="yfinance")


async def get_yfinance_info_async(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Fetch yfinance info asynchronously using thread pool.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Dictionary containing stock info, or None if error
    """
    loop = asyncio.get_event_loop()
    
    def _fetch():
        try:
            stock = yf.Ticker(ticker)
            return stock.info
        except YFRateLimitError:
            raise  # Re-raise to handle in caller
        except Exception as e:
            logger.warning(f"Error fetching info for {ticker}: {e}")
            return None
    
    try:
        return await loop.run_in_executor(_yfinance_executor, _fetch)
    except YFRateLimitError:
        raise
    except Exception as e:
        logger.error(f"Error in async yfinance info fetch for {ticker}: {e}")
        return None


async def get_yfinance_history_async(ticker: str, period: str = "1y") -> Optional[pd.DataFrame]:
    """
    Fetch yfinance historical data asynchronously using thread pool.
    
    Args:
        ticker: Stock ticker symbol
        period: Period for historical data (e.g., "1y", "6mo", "1mo")
        
    Returns:
        DataFrame containing historical data, or None if error
    """
    loop = asyncio.get_event_loop()
    
    def _fetch():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)
            return hist if not hist.empty else None
        except YFRateLimitError:
            raise  # Re-raise to handle in caller
        except Exception as e:
            logger.warning(f"Error fetching history for {ticker}: {e}")
            return None
    
    try:
        return await loop.run_in_executor(_yfinance_executor, _fetch)
    except YFRateLimitError:
        raise
    except Exception as e:
        logger.error(f"Error in async yfinance history fetch for {ticker}: {e}")
        return None


async def get_yfinance_dividends_async(ticker: str) -> Optional[pd.Series]:
    """
    Fetch yfinance dividends asynchronously using thread pool.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Series containing dividend data, or None if error
    """
    loop = asyncio.get_event_loop()
    
    def _fetch():
        try:
            stock = yf.Ticker(ticker)
            dividends = stock.dividends
            return dividends if not dividends.empty else None
        except YFRateLimitError:
            raise  # Re-raise to handle in caller
        except Exception as e:
            logger.warning(f"Error fetching dividends for {ticker}: {e}")
            return None
    
    try:
        return await loop.run_in_executor(_yfinance_executor, _fetch)
    except YFRateLimitError:
        raise
    except Exception as e:
        logger.error(f"Error in async yfinance dividends fetch for {ticker}: {e}")
        return None


async def get_yfinance_stock_data_async(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Fetch comprehensive yfinance data (info, history, dividends, earnings) asynchronously.
    This batches multiple yfinance calls into a single thread execution for efficiency.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Dictionary containing:
            - info: Stock info dictionary
            - history: Historical price DataFrame (1 year)
            - dividends: Dividends Series
            - earnings: Earnings DataFrame (if available)
            - quarterly_earnings: Quarterly earnings DataFrame (if available)
            - earnings_history: Earnings history DataFrame (if available)
            - calendar: Earnings calendar DataFrame (if available)
        Or None if error
    """
    loop = asyncio.get_event_loop()
    
    def _fetch():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            result = {
                'info': stock.info,
                'history': hist if not hist.empty else None,
                'dividends': stock.dividends if not stock.dividends.empty else None,
            }
            
            # Try to get earnings data
            try:
                if hasattr(stock, 'earnings') and not stock.earnings.empty:
                    result['earnings'] = stock.earnings
                else:
                    result['earnings'] = None
            except Exception:
                result['earnings'] = None
            
            # Try to get quarterly earnings
            try:
                if hasattr(stock, 'quarterly_earnings') and not stock.quarterly_earnings.empty:
                    result['quarterly_earnings'] = stock.quarterly_earnings
                else:
                    result['quarterly_earnings'] = None
            except Exception:
                result['quarterly_earnings'] = None
            
            # Try to get earnings history
            try:
                if hasattr(stock, 'earnings_history') and not stock.earnings_history.empty:
                    result['earnings_history'] = stock.earnings_history
                else:
                    result['earnings_history'] = None
            except Exception:
                result['earnings_history'] = None
            
            # Try to get earnings calendar
            try:
                calendar = stock.calendar
                result['calendar'] = calendar if calendar is not None and not calendar.empty else None
            except Exception:
                result['calendar'] = None
            
            return result
        except YFRateLimitError:
            raise  # Re-raise to handle in caller
        except Exception as e:
            logger.warning(f"Error fetching stock data for {ticker}: {e}")
            return None
    
    try:
        return await loop.run_in_executor(_yfinance_executor, _fetch)
    except YFRateLimitError:
        raise
    except Exception as e:
        logger.error(f"Error in async yfinance stock data fetch for {ticker}: {e}")
        return None


def shutdown_executor():
    """Shutdown the thread pool executor (call on app shutdown)"""
    _yfinance_executor.shutdown(wait=False)


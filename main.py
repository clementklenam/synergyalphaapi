from fastapi import FastAPI, HTTPException, Query, Depends, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from typing import List, Optional
import logging
import os
from pydantic import BaseModel
from database import MongoManager, get_database
from motor.motor_asyncio import AsyncIOMotorDatabase
from update_manager import UpdateManager
from utils import clean_mongo_data
import math
import re
from typing import List, Dict, Any, Optional
import screener
from contextlib import asynccontextmanager
import asyncio
from realtime_prices import get_realtime_manager
from news_service import get_news_service
import yfinance as yf
import pandas as pd
from yfinance.exceptions import YFRateLimitError
import aiohttp
from bs4 import BeautifulSoup
import re


# Set up logging
from datetime import timedelta, datetime
from settings import Settings 

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('stock_api.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create database indexes for better performance
    await MongoManager.create_indexes()
    # Start the update loop when the application starts
    await UpdateManager.start_updates()
    # Start the real-time price manager
    realtime_manager = get_realtime_manager()
    await realtime_manager.start()
    yield
    # Stop the real-time price manager
    await realtime_manager.stop()
    # Stop the update loop when the application shuts down
    await UpdateManager.stop_updates()
    # Shutdown yfinance thread pool executor
    shutdown_executor()


app = FastAPI(
    title="Stock Market Data API", 
    description="API for accessing S&P 500 stock data",
    lifespan=lifespan
)


app.include_router(screener.router)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add GZip compression middleware for faster responses
app.add_middleware(GZipMiddleware, minimum_size=1000)
 

@app.get("/companies", response_model=List[dict])
async def get_all_companies(db: AsyncIOMotorDatabase = Depends(get_database)):
    """Get basic information for all companies"""
    try:
        companies = await db.companies.find(
            {},
            {
                "ticker": 1,
                "name": 1,
                "sector": 1,
                "industry": 1,
                "market_cap": 1,
                "exchange": 1,
                "_id": 0
            }
        ).to_list(length=None)
        return clean_mongo_data(companies)
    except Exception as e:
        logger.error(f"Error fetching companies: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/search")
async def search_companies(
    query: str = Query(..., description="Search by ticker, name, or sector"),
    limit: int = Query(20, description="Number of results to return", ge=1, le=100),
    page: int = Query(1, description="Page number for pagination", ge=1),
    db: AsyncIOMotorDatabase = Depends(get_database)
) -> Dict[str, Any]:
    """
    Enhanced search for companies with improved ticker matching:
    - Single letter queries focus exclusively on ticker matches
    - Exact ticker matches appear first
    - Prefix matches for tickers are prioritized
    - Name and sector matches appear after ticker matches
    
    Returns paginated results sorted by relevance and market cap.
    """
    try:
        skip = (page - 1) * limit
        query = query.strip()
        
        # Build search pipeline
        pipeline: List[Dict[str, Any]] = []
        
        # Different search logic based on query length
        if len(query) == 1:
            # Single letter - only search tickers
            pipeline.extend([
                {
                    "$match": {
                        "ticker": {"$regex": f"^{re.escape(query.upper())}"}
                    }
                }
            ])
        else:
            # Multi-character search with prioritized matching
            pipeline.extend([
                {
                    "$match": {
                        "$or": [
                            # Exact ticker match
                            {"ticker": query.upper()},
                            # Ticker starts with query
                            {"ticker": {"$regex": f"^{re.escape(query.upper())}"}},
                            # Ticker contains query
                            {"ticker": {"$regex": f"{re.escape(query.upper())}", "$options": "i"}},
                            # Name contains query
                            {"name": {"$regex": f"{re.escape(query)}", "$options": "i"}},
                            # Sector contains query
                            {"sector": {"$regex": f"{re.escape(query)}", "$options": "i"}}
                        ]
                    }
                },
                {
                    "$addFields": {
                        "matchScore": {
                            "$switch": {
                                "branches": [
                                    # Exact ticker match gets highest priority
                                    {
                                        "case": {"$eq": ["$ticker", query.upper()]},
                                        "then": 5
                                    },
                                    # Ticker starts with query gets second priority
                                    {
                                        "case": {
                                            "$regexMatch": {
                                                "input": "$ticker",
                                                "regex": f"^{re.escape(query.upper())}"
                                            }
                                        },
                                        "then": 4
                                    },
                                    # Ticker contains query gets third priority
                                    {
                                        "case": {
                                            "$regexMatch": {
                                                "input": "$ticker",
                                                "regex": f"{re.escape(query.upper())}",
                                                "options": "i"
                                            }
                                        },
                                        "then": 3
                                    },
                                    # Name matches get fourth priority
                                    {
                                        "case": {
                                            "$regexMatch": {
                                                "input": "$name",
                                                "regex": f"{re.escape(query)}",
                                                "options": "i"
                                            }
                                        },
                                        "then": 2
                                    },
                                    # Sector matches get lowest priority
                                    {
                                        "case": {
                                            "$regexMatch": {
                                                "input": "$sector",
                                                "regex": f"{re.escape(query)}",
                                                "options": "i"
                                            }
                                        },
                                        "then": 1
                                    }
                                ],
                                "default": 0
                            }
                        }
                    }
                }
            ])

        # Add sorting, projection, and pagination
        pipeline.extend([
            {
                "$sort": {
                    "matchScore": -1,
                    "market_cap": -1
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "ticker": 1,
                    "name": 1,
                    "sector": 1,
                    "industry": 1,
                    "market_cap": 1,
                    "market_cap_billions": {
                        "$round": [{"$divide": ["$market_cap", 1000000000]}, 2]
                    },
                    "exchange": 1,
                    "quote.price": 1,
                    "quote.change": 1,
                    "quote.changesPercentage": 1,
                    "quote.volume": 1
                }
            },
            {"$skip": skip},
            {"$limit": limit}
        ])

        # Execute pipeline and get total count
        results = await db.companies.aggregate(pipeline).to_list(length=limit)
        total_count = await db.companies.count_documents({})

        return clean_mongo_data({
            "count": len(results),
            "total": total_count,
            "page": page,
            "pages": -(-total_count // limit),  # Ceiling division
            "results": results
        })

    except Exception as e:
        logger.error(f"Error in search: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/updates/status")
async def get_update_status():
    """Get the current status of data updates"""
    next_update_time = None
    if UpdateManager._last_check:
        next_update_time = UpdateManager._last_check + timedelta(seconds=Settings.UPDATE_INTERVAL)
    
    return {
        "last_update": UpdateManager._last_check,
        "next_update": next_update_time,
        "is_updating": UpdateManager._is_updating,
        "update_interval": f"{Settings.UPDATE_INTERVAL} seconds ({Settings.UPDATE_INTERVAL / 60} minutes)"
    }


@app.post("/api/trigger-update", status_code=202)
async def trigger_update(background_tasks: BackgroundTasks):
    background_tasks.add_task(UpdateManager.start_updates)
    return {"message": "Background update process started"}

@app.post("/api/update-all-companies", status_code=202)
async def update_all_companies(background_tasks: BackgroundTasks, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Trigger an update for all companies in the database"""
    try:
        # Get all tickers from database
        companies = await db.companies.find({}, {"ticker": 1, "_id": 0}).to_list(length=None)
        symbols = [company["ticker"] for company in companies if "ticker" in company]
        
        if not symbols:
            return {"message": "No companies found in database", "status": "error"}
        
        background_tasks.add_task(UpdateManager.update_stock_data, symbols)
        return {
            "message": f"Update triggered for {len(symbols)} companies",
            "status": "processing",
            "count": len(symbols)
        }
    except Exception as e:
        logger.error(f"Error triggering update for all companies: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/update-company/{ticker}", status_code=202)
async def update_company(ticker: str, background_tasks: BackgroundTasks):
    """Trigger an update for a specific company"""
    ticker = ticker.upper()
    background_tasks.add_task(UpdateManager.update_stock_data, [ticker])
    return {"message": f"Update triggered for {ticker}", "ticker": ticker}
# @app.post("/updates/trigger")
# async def trigger_update(background_tasks: BackgroundTasks):
#     """Manually trigger a data update"""
#     if UpdateManager._is_updating:
#         raise HTTPException(status_code=400, detail="Update already in progress")
    
#     background_tasks.add_task(UpdateManager.update_stock_data)
#     return {"message": "Update triggered", "timestamp": datetime.now()}

@app.get("/symbols")
async def get_symbols(db: AsyncIOMotorDatabase = Depends(get_database)):
    """Get list of all symbols in the database"""
    try:
        symbols = await db.companies.find(
            {},
            {
                "_id": 0,
                "ticker": 1,
                "name": 1
            }
        ).to_list(length=None)
        return clean_mongo_data(symbols)
    except Exception as e:
        logger.error(f"Error fetching symbols: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/companies/{ticker}")
async def get_company_details(
    ticker: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get detailed information for a specific company"""
    try:
        company = await db.companies.find_one(
            {"ticker": ticker.upper()},
            {"_id": 0}
        )
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        return clean_mongo_data(company)
    except Exception as e:
        logger.error(f"Error fetching company {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/companies/{ticker}/quote")
async def get_company_quote(
    ticker: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get current quote for a specific company"""
    try:
        company = await db.companies.find_one(
            {"ticker": ticker.upper()},
            {"quote": 1, "_id": 0}
        )
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        return clean_mongo_data(company["quote"])
    except Exception as e:
        logger.error(f"Error fetching quote for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/companies/{ticker}/prices")
async def get_stock_prices(
    ticker: str,
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get historical stock prices for a specific company"""
    try:
        company = await db.companies.find_one(
            {"ticker": ticker.upper()},
            {"stock_prices": 1, "_id": 0}
        )
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        
        prices = company["stock_prices"]
        
        if start_date:
            prices = [p for p in prices if p["date"] >= start_date]
        if end_date:
            prices = [p for p in prices if p["date"] <= end_date]
            
        return clean_mongo_data(prices)
    except Exception as e:
        logger.error(f"Error fetching prices for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sectors")
async def get_sectors(db: AsyncIOMotorDatabase = Depends(get_database)):
    """Get list of all sectors and their companies"""
    try:
        pipeline = [
            {
                "$group": {
                    "_id": "$sector",
                    "companies": {
                        "$push": {
                            "ticker": "$ticker",
                            "name": "$name",
                            "market_cap": "$market_cap"
                        }
                    }
                }
            }
        ]
        cursor = db.companies.aggregate(pipeline)
        sectors = await cursor.to_list(length=None)
        return clean_mongo_data(sectors)
    except Exception as e:
        logger.error(f"Error fetching sectors: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
    
@app.get("/companies/{ticker}/income-statement")
async def get_income_statement(
    ticker: str,
    period: str = Query("annual", enum=["annual", "quarterly"], description="Choose annual or quarterly data"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Retrieve income statement for a company"""
    try:
        # Ensure the ticker is uppercase for consistency
        ticker = ticker.upper()

        # Fetch only the relevant part of the financial statement
        company = await db.companies.find_one(
            {"ticker": ticker},
            {"financial_statements.income_statement": 1, "_id": 0}
        )

        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")

        # Extract income statement safely
        income_statement = company.get("financial_statements", {}).get("income_statement", {})

        if period not in income_statement:
            raise HTTPException(status_code=404, detail=f"Income statement for {ticker} ({period}) not found")

        return clean_mongo_data(income_statement[period])

    except HTTPException:
        # Re-raise HTTPException (like 404) as-is
        raise
    except Exception as e:
        logger.error(f"Error fetching income statement for {ticker}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/companies/{ticker}/balance-sheet")
async def get_balance_sheet(
    ticker: str,
    period: str = Query("annual", enum=["annual", "quarterly"], description="Choose annual or quarterly data"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Retrieve balance sheet for a company"""
    try:
        ticker = ticker.upper()

        company = await db.companies.find_one(
            {"ticker": ticker},
            {"financial_statements.balance_sheet": 1, "_id": 0}
        )

        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")

        balance_sheet = company.get("financial_statements", {}).get("balance_sheet", {})

        if period not in balance_sheet:
            raise HTTPException(status_code=404, detail=f"Balance sheet for {ticker} ({period}) not found")

        return clean_mongo_data(balance_sheet[period])

    except HTTPException:
        # Re-raise HTTPException (like 404) as-is
        raise
    except Exception as e:
        logger.error(f"Error fetching balance sheet for {ticker}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/companies/{ticker}/cash-flow-statement")
async def get_cash_flow_statement(
    ticker: str,
    period: str = Query("annual", enum=["annual", "quarterly"], description="Choose annual or quarterly data"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Retrieve cash flow statement for a company"""
    try:
        ticker = ticker.upper()

        company = await db.companies.find_one(
            {"ticker": ticker},
            {"financial_statements.cash_flow_statement": 1, "_id": 0}
        )

        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")

        cash_flow_statement = company.get("financial_statements", {}).get("cash_flow_statement", {})

        if period not in cash_flow_statement:
            raise HTTPException(status_code=404, detail=f"Cash flow statement for {ticker} ({period}) not found")

        return clean_mongo_data(cash_flow_statement[period])

    except HTTPException:
        # Re-raise HTTPException (like 404) as-is
        raise
    except Exception as e:
        logger.error(f"Error fetching cash flow statement for {ticker}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Add these endpoints to your existing FastAPI app

@app.get("/companies/{ticker}/officers")
async def get_company_officers(
    ticker: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get company officers and management team information"""
    try:
        company = await db.companies.find_one(
            {"ticker": ticker.upper()},
            {
                "officers": 1,
                "ceo": 1,
                "_id": 0
            }
        )
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        return clean_mongo_data(company)
    except Exception as e:
        logger.error(f"Error fetching officers for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/companies/{ticker}/logo")
async def get_company_logo(
    ticker: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get company logo as base64 encoded image"""
    try:
        company = await db.companies.find_one(
            {"ticker": ticker.upper()},
            {"image": 1, "_id": 0}
        )
        if not company or "image" not in company:
            raise HTTPException(status_code=404, detail=f"Logo for {ticker} not found")
        return {"image": f"data:image/jpeg;base64,{company['image']}"}
    except Exception as e:
        logger.error(f"Error fetching logo for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/companies/compare")
async def compare_companies(
    tickers: List[str] = Query(..., description="List of tickers to compare"),
    metrics: List[str] = Query(
        ["price", "market_cap", "beta", "volume"],
        description="Metrics to compare"
    ),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Compare multiple companies across specified metrics"""
    try:
        # Convert tickers to uppercase
        tickers = [ticker.upper() for ticker in tickers]
        
        # Fetch companies data
        companies = await db.companies.find(
            {"ticker": {"$in": tickers}},
            {
                "ticker": 1,
                "name": 1,
                "price": 1,
                "market_cap": 1,
                "beta": 1,
                "volume": 1,
                "sector": 1,
                "industry": 1,
                "_id": 0
            }
        ).to_list(length=None)
        
        if not companies:
            raise HTTPException(status_code=404, detail="No companies found")
            
        return clean_mongo_data({
            "metrics": metrics,
            "companies": companies
        })
    except Exception as e:
        logger.error(f"Error comparing companies: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/market-overview")
async def get_market_overview(
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get market overview with top gainers, losers, and most active stocks"""
    try:
        pipeline = [
            {
                "$project": {
                    "ticker": 1,
                    "name": 1,
                    "price": 1,
                    "changes": 1,
                    "volume": 1,
                    "market_cap": 1,
                    "_id": 0
                }
            },
            {
                "$sort": {"changes": -1}
            }
        ]
        
        all_stocks = await db.companies.aggregate(pipeline).to_list(length=None)
        
        # Get top 10 gainers and losers
        gainers = sorted(all_stocks, key=lambda x: x.get('changes', 0) or 0, reverse=True)[:10]
        losers = sorted(all_stocks, key=lambda x: x.get('changes', 0) or 0)[:10]
        
        # Get most active by volume
        most_active = sorted(all_stocks, key=lambda x: x.get('volume', 0) or 0, reverse=True)[:10]
        
        return clean_mongo_data({
            "top_gainers": gainers,
            "top_losers": losers,
            "most_active": most_active
        })
    except Exception as e:
        logger.error(f"Error fetching market overview: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/companies/{ticker}/key-stats")
async def get_company_key_stats(
    ticker: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get key statistics and ratios for a company"""
    try:
        company = await db.companies.find_one(
            {"ticker": ticker.upper()},
            {
                "ticker": 1,
                "name": 1,
                "market_cap": 1,
                "beta": 1,
                "price_to_earnings": 1,
                "price_to_book": 1,
                "dividend_yield": 1,
                "debt_to_equity": 1,
                "current_ratio": 1,
                "return_on_equity": 1,
                "return_on_assets": 1,
                "profit_margin": 1,
                "_id": 0
            }
        )
        
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
            
        return clean_mongo_data(company)
    except Exception as e:
        logger.error(f"Error fetching key stats for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/companies/{ticker}/peers")
async def get_company_peers(
    ticker: str,
    limit: int = Query(5, description="Number of peer companies to return"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get peer companies in the same sector/industry"""
    try:
        # First get the company's sector and industry
        company = await db.companies.find_one(
            {"ticker": ticker.upper()},
            {"sector": 1, "industry": 1, "market_cap": 1, "_id": 0}
        )
        
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
            
        # Find peers in the same industry with similar market cap
        peers = await db.companies.find(
            {
                "ticker": {"$ne": ticker.upper()},
                "industry": company["industry"],
                "sector": company["sector"]
            },
            {
                "ticker": 1,
                "name": 1,
                "market_cap": 1,
                "price": 1,
                "changes": 1,
                "_id": 0
            }
        ).sort([
            ("market_cap", -1)
        ]).limit(limit).to_list(length=None)
        
        return clean_mongo_data({
            "company": company,
            "peers": peers
        })
    except Exception as e:
        logger.error(f"Error fetching peers for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# News endpoints

@app.get("/companies/{ticker}/news")
async def get_company_news(
    ticker: str,
    limit: int = Query(10, description="Maximum number of news articles to return", ge=1, le=50),
    include_content: bool = Query(True, description="Include full article content (set to false for faster responses)"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get latest news articles for a specific company
    
    Fetches recent news articles related to the company from Yahoo Finance.
    By default includes full article content. Set include_content=false for faster responses with metadata only.
    """
    try:
        ticker = ticker.upper()
        
        # Verify company exists in database
        company = await db.companies.find_one(
            {"ticker": ticker},
            {"ticker": 1, "_id": 0}
        )
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        
        # Fetch news using news service
        news_service = get_news_service()
        news_articles = await news_service.get_news(ticker, limit, include_content)
        
        return {
            "ticker": ticker,
            "count": len(news_articles),
            "include_content": include_content,
            "articles": clean_mongo_data(news_articles)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching news for {ticker}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/news/batch")
async def get_news_batch(
    tickers: List[str] = Query(..., description="List of tickers to get news for"),
    limit: int = Query(10, description="Maximum number of articles per ticker", ge=1, le=50),
    include_content: bool = Query(True, description="Include full article content (set to false for faster responses)"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get news articles for multiple tickers
    
    Fetches news articles for multiple companies concurrently.
    By default includes full article content. Set include_content=false for faster responses with metadata only.
    """
    try:
        tickers = [t.upper() for t in tickers]
        
        if len(tickers) > 20:
            raise HTTPException(status_code=400, detail="Maximum 20 tickers allowed per request")
        
        # Fetch news using news service
        news_service = get_news_service()
        news_dict = await news_service.get_news_batch(tickers, limit, include_content)
        
        # Format response
        result = {
            "count": len(tickers),
            "tickers": tickers,
            "news": {}
        }
        
        for ticker in tickers:
            result["news"][ticker] = {
                "count": len(news_dict.get(ticker, [])),
                "articles": clean_mongo_data(news_dict.get(ticker, []))
            }
        
        return clean_mongo_data(result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching batch news: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Comprehensive data endpoint

@app.get("/companies/{ticker}/comprehensive")
async def get_comprehensive_data(
    ticker: str,
    news_limit: int = Query(20, description="Maximum number of news articles", ge=1, le=50),
    include_news_content: bool = Query(True, description="Include full news article content"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get comprehensive data for a company including:
    1. Company Profile Data (name, symbol, exchange, industry, sector, logo, description, CEO, employees, website, marketCap, price, beta)
    2. Quote (price, change, changesPercentage, dayLow, dayHigh, yearLow, yearHigh, open, previousClose, volume, avgVolume, marketCap, pe, eps, beta, dividendYield, sector)
    3. Historical Price Data (365+ days with date and close fields)
    4. News Data (up to 20 articles with headline, summary, url, datetime, source)
    5. Valuation Data (key metrics TTM, income statements, enterprise values, financial growth)
    6. Financial Health Data (ratios, income statements, cash flow statements)
    7. Earnings Data (calendar, history, dates)
    """
    try:
        ticker = ticker.upper()
        
        # Verify company exists
        company = await db.companies.find_one(
            {"ticker": ticker},
            {"_id": 0}
        )
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        
        # Fetch shares outstanding and EPS data from yfinance early (we'll use it in multiple places)
        shares_outstanding = None
        info = None
        try:
            info = await get_yfinance_info_async(ticker)
            if info:
                shares_outstanding = info.get('sharesOutstanding')
        except Exception:
            pass
        
        # 1. Company Profile Data
        profile = {
            "companyName": company.get("companyName") or company.get("name"),
            "symbol": ticker,
            "exchange": company.get("exchange"),
            "industry": company.get("industry"),
            "sector": company.get("sector"),
            "image": company.get("image"),
            "description": company.get("description"),
            "ceo": company.get("ceo"),
            "fullTimeEmployees": company.get("fullTimeEmployees"),
            "website": company.get("website"),
            "marketCap": company.get("mktCap") or company.get("marketCap") or company.get("quote", {}).get("marketCap"),
            "price": company.get("price") or company.get("quote", {}).get("price"),
            "beta": company.get("beta"),
            "sharesOutstanding": shares_outstanding
        }
        
        # 2. Quote Data
        quote_data = company.get("quote", {})
        quote = {
            "price": quote_data.get("price") or company.get("price"),
            "change": quote_data.get("change"),
            "changesPercentage": quote_data.get("changesPercentage"),
            "dayLow": quote_data.get("dayLow"),
            "dayHigh": quote_data.get("dayHigh"),
            "yearLow": quote_data.get("yearLow"),
            "yearHigh": quote_data.get("yearHigh"),
            "open": quote_data.get("open"),
            "previousClose": quote_data.get("previousClose"),
            "volume": quote_data.get("volume"),
            "avgVolume": quote_data.get("avgVolume") or company.get("volAvg"),
            "marketCap": quote_data.get("marketCap") or company.get("mktCap") or company.get("marketCap"),
            "pe": quote_data.get("pe") or company.get("key_metrics", {}).get("pe_ratio"),
            "eps": company.get("key_metrics", {}).get("eps"),
            "beta": company.get("beta"),
            "dividendYield": company.get("key_metrics", {}).get("dividend_yield") or quote_data.get("dividendYield"),
            "sector": company.get("sector"),
            "sharesOutstanding": shares_outstanding
        }
        
        # Add EPS data from yfinance if available
        if info:
            trailing_eps = info.get('trailingEps')
            eps_trailing_twelve_months = info.get('epsTrailingTwelveMonths')
            eps_current_year = info.get('epsCurrentYear')
            forward_eps = info.get('forwardEps') or info.get('epsForward')
            
            if trailing_eps is not None:
                quote["trailingEps"] = trailing_eps
            if eps_trailing_twelve_months is not None:
                quote["epsTrailingTwelveMonths"] = eps_trailing_twelve_months
            if eps_current_year is not None:
                quote["epsCurrentYear"] = eps_current_year
            if forward_eps is not None:
                quote["forwardEps"] = forward_eps
        
        # 3. Historical Price Data (fetch from yfinance - 365+ days)
        historical_data = []
        try:
            hist = await get_yfinance_history_async(ticker, period="1y")
            if hist is not None and not hist.empty:
                # Convert to list of dicts with date and close
                hist_reset = hist.reset_index()
                historical_data = [
                    {
                        "date": row["Date"].strftime("%Y-%m-%d") if hasattr(row["Date"], "strftime") else str(row["Date"]),
                        "close": float(row["Close"]) if pd.notna(row["Close"]) else None
                    }
                    for _, row in hist_reset.iterrows()
                ]
        except YFRateLimitError:
            logger.warning(f"Rate limit hit while fetching historical data for {ticker}")
            historical_data = []
        except Exception as e:
            logger.warning(f"Error fetching historical data for {ticker}: {e}")
            historical_data = []
        
        # 4. News Data
        news_data = []
        try:
            news_service = get_news_service()
            news_articles = await news_service.get_news(ticker, news_limit, include_news_content)
            news_data = [
                {
                    "headline": article.get("title"),
                    "summary": article.get("summary"),
                    "url": article.get("url"),
                    "datetime": article.get("publish_date"),
                    "source": article.get("provider"),
                    "thumbnail_url": article.get("thumbnail_url")
                }
                for article in news_articles
            ]
        except Exception as e:
            logger.warning(f"Error fetching news for {ticker}: {e}")
            news_data = []
        
        # 5. Valuation Data
        key_metrics = company.get("key_metrics", {})
        financial_statements = company.get("financial_statements", {})
        valuation = {
            "key_metrics_ttm": {
                "pe_ratio": key_metrics.get("pe_ratio"),
                "forward_pe": key_metrics.get("forward_pe"),
                "peg_ratio": key_metrics.get("peg_ratio"),
                "price_to_book": key_metrics.get("price_to_book"),
                "price_to_sales": key_metrics.get("price_to_sales"),
                "beta": key_metrics.get("beta"),
                "dividend_yield": key_metrics.get("dividend_yield"),
                "dividend_rate": key_metrics.get("dividend_rate")
            },
            "income_statements": {
                "annual": financial_statements.get("income_statement", {}).get("annual", {}),
                "quarterly": financial_statements.get("income_statement", {}).get("quarterly", {})
            },
            "enterprise_values": {
                "market_cap": company.get("mktCap") or company.get("marketCap"),
                "enterprise_value": company.get("enterprise_value")
            },
            "financial_growth": company.get("ttm_ratios", {})
        }
        
        # 6. Financial Health Data
        ttm_ratios = company.get("ttm_ratios", {})
        ratios = {
            "profit_margin": ttm_ratios.get("profit_margin"),
            "operating_margin": ttm_ratios.get("operating_margin"),
            "roa": ttm_ratios.get("roa"),
            "roe": ttm_ratios.get("roe")
        }
        # Only include revenue_growth and earnings_growth if they're not null
        revenue_growth = ttm_ratios.get("revenue_growth")
        earnings_growth = ttm_ratios.get("earnings_growth")
        if revenue_growth is not None:
            ratios["revenue_growth"] = revenue_growth
        if earnings_growth is not None:
            ratios["earnings_growth"] = earnings_growth
        
        financial_health = {
            "ratios": ratios,
            "income_statements": {
                "current_annual": financial_statements.get("income_statement", {}).get("annual", {}),
                "current_quarterly": financial_statements.get("income_statement", {}).get("quarterly", {}),
                "previous_annual": {},  # Could be enhanced to store historical
                "previous_quarterly": {}  # Could be enhanced to store historical
            },
            "cash_flow_statements": {
                "annual": financial_statements.get("cash_flow_statement", {}).get("annual", {}),
                "quarterly": financial_statements.get("cash_flow_statement", {}).get("quarterly", {})
            }
        }
        
        # 7. Earnings Data (fetch from yfinance)
        earnings_data = {}
        try:
            # Reuse info if we already have it, otherwise fetch
            if info is None:
                info = await get_yfinance_info_async(ticker)
            
            # Fetch comprehensive stock data (includes earnings if available)
            stock_data = await get_yfinance_stock_data_async(ticker)
            
            earnings_calendar = stock_data.get('calendar') if stock_data else None
            earnings_annual = stock_data.get('earnings') if stock_data else None
            earnings_quarterly = stock_data.get('quarterly_earnings') if stock_data else None
            earnings_history = stock_data.get('earnings_history') if stock_data else None
            
            earnings_data = {
                "earnings_calendar": clean_mongo_data(earnings_calendar.to_dict()) if earnings_calendar is not None and hasattr(earnings_calendar, 'to_dict') and not earnings_calendar.empty else {},
                "earnings_dates": info.get("earningsDates", []) if info else [],
                "earnings_history": clean_mongo_data(earnings_history.to_dict()) if earnings_history is not None and hasattr(earnings_history, 'to_dict') and not earnings_history.empty else {},
                "earnings_quarterly": clean_mongo_data(earnings_quarterly.to_dict()) if earnings_quarterly is not None and hasattr(earnings_quarterly, 'to_dict') and not earnings_quarterly.empty else {},
                "earnings_annual": clean_mongo_data(earnings_annual.to_dict()) if earnings_annual is not None and hasattr(earnings_annual, 'to_dict') and not earnings_annual.empty else {}
            }
        except YFRateLimitError:
            logger.warning(f"Rate limit hit while fetching earnings data for {ticker}")
            earnings_data = {}
        except Exception as e:
            logger.warning(f"Error fetching earnings data for {ticker}: {e}")
            earnings_data = {}
        
        # Combine all data
        comprehensive_data = {
            "ticker": ticker,
            "companyProfile": clean_mongo_data(profile),
            "quote": clean_mongo_data(quote),
            "historicalPrices": clean_mongo_data(historical_data),
            "news": clean_mongo_data(news_data),
            "valuation": clean_mongo_data(valuation),
            "financialHealth": clean_mongo_data(financial_health),
            "earnings": clean_mongo_data(earnings_data),
            "last_updated": company.get("last_updated")
        }
        
        return comprehensive_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching comprehensive data for {ticker}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


# Real-time price streaming endpoints

@app.websocket("/ws/quote/{ticker}")
async def websocket_quote(websocket: WebSocket, ticker: str):
    """
    WebSocket endpoint for real-time stock price updates.
    Clients connect to receive live price updates for a specific ticker.
    """
    realtime_manager = get_realtime_manager()
    ticker = ticker.upper()
    
    await websocket.accept()
    logger.info(f"WebSocket connection established for {ticker}")
    
    try:
        # Subscribe to price updates
        await realtime_manager.subscriptions.subscribe(ticker, websocket)
        
        # Send initial price if available
        cached_price = await realtime_manager.cache.get(ticker)
        if cached_price:
            await websocket.send_json({
                "ticker": ticker,
                "data": cached_price,
                "timestamp": cached_price.get("last_updated", datetime.utcnow()).isoformat(),
                "type": "initial"
            })
        else:
            # Fetch initial price
            await realtime_manager.get_price(ticker)
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages (or timeout to keep connection alive)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Handle ping/pong or other messages if needed
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})
            except WebSocketDisconnect:
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {ticker}")
    except Exception as e:
        logger.error(f"Error in WebSocket connection for {ticker}: {e}", exc_info=True)
    finally:
        # Unsubscribe when connection closes
        await realtime_manager.subscriptions.unsubscribe(ticker, websocket)


@app.get("/quote/realtime/{ticker}")
async def get_realtime_quote(ticker: str):
    """
    Get real-time (cached) stock quote.
    Returns the latest cached price data. Updates cache if stale.
    """
    try:
        realtime_manager = get_realtime_manager()
        ticker = ticker.upper()
        
        # Get price (will fetch if not cached or stale)
        price_data = await realtime_manager.get_price(ticker)
        
        if not price_data:
            raise HTTPException(status_code=404, detail=f"Price data not available for {ticker}")
        
        return clean_mongo_data(price_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching real-time quote for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/quote/realtime")
async def get_realtime_quotes(tickers: List[str] = Query(..., description="List of tickers to get quotes for")):
    """
    Get real-time quotes for multiple tickers.
    Returns the latest cached price data for all requested tickers.
    """
    try:
        realtime_manager = get_realtime_manager()
        tickers = [t.upper() for t in tickers]
        
        results = {}
        for ticker in tickers:
            price_data = await realtime_manager.get_price(ticker)
            if price_data:
                results[ticker] = clean_mongo_data(price_data)
            else:
                results[ticker] = None
        
        return results
        
    except Exception as e:
        logger.error(f"Error fetching real-time quotes: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/quote/realtime/status")
async def get_realtime_status():
    """Get status of the real-time price streaming service"""
    try:
        realtime_manager = get_realtime_manager()
        active_tickers = await realtime_manager.subscriptions.get_active_tickers()
        all_cached = await realtime_manager.cache.get_all()
        
        return {
            "is_running": realtime_manager._is_running,
            "active_subscriptions": len(active_tickers),
            "active_tickers": list(active_tickers),
            "cached_tickers": len(all_cached),
            "poll_interval_seconds": realtime_manager._poll_interval
        }
    except Exception as e:
        logger.error(f"Error getting real-time status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Dividend endpoint

@app.get("/companies/{ticker}/dividends")
async def get_dividend_data(
    ticker: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get comprehensive dividend data for a company including:
    1. Dividend Metrics (yield, annual payout, payout ratio, growth streak, EPS, frequency)
    2. Upcoming Dividend Payouts (ex-dividend date, amount, payment date)
    3. Dividend History Table (exDivDate, amount, fiscal year/quarter)
    4. Dividend Yield Chart Data (date, yield percentage)
    5. Payout History Chart Data (year, payout amount, growth percentage)
    6. Quick Stats (frequency, last/next payment dates, current payout, growth)
    
    Data Source:
    - yfinance: All dividend data (free, no API key required)
    
    Note: Only fields with actual values are returned (null fields are excluded).
    Fields like recordDate, declareDate, and payoutType are not available from yfinance.
    """
    try:
        ticker = ticker.upper()
        
        # Verify company exists
        company = await db.companies.find_one(
            {"ticker": ticker},
            {"ticker": 1, "sector": 1, "_id": 0}
        )
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        
        # Fetch dividend data from yfinance
        info = await get_yfinance_info_async(ticker)
        
        # Get dividend history
        dividends_dict = {}
        try:
            dividends_series = await get_yfinance_dividends_async(ticker)
            if dividends_series is not None and not dividends_series.empty:
                # Convert pandas Series to dict with date strings as keys
                dividends_dict = {}
                for date, value in dividends_series.items():
                    date_str = date.strftime("%Y-%m-%d") if hasattr(date, 'strftime') else str(date)
                    dividends_dict[date_str] = float(value) if pd.notna(value) else None
        except Exception as e:
            logger.warning(f"Error fetching dividend history for {ticker}: {e}")
            dividends_dict = {}
        
        # 1. Dividend Metrics
        eps = info.get('trailingEps') or info.get('epsTrailing12Months')
        dividend_yield = info.get('dividendYield') or info.get('trailingAnnualDividendYield')
        dividend_rate = info.get('dividendRate') or info.get('trailingAnnualDividendRate')
        payout_ratio = info.get('payoutRatio')
        five_year_avg_yield = info.get('fiveYearAvgDividendYield')
        
        # Calculate annual payout (dividend rate or last dividend * frequency)
        annual_payout = dividend_rate
        if annual_payout is None and dividends_dict:
            # Try to calculate from recent dividends
            try:
                recent_dividends = list(dividends_dict.values())[-4:] if dividends_dict else []
                if recent_dividends:
                    annual_payout = sum([d for d in recent_dividends if d is not None]) if len(recent_dividends) >= 4 else sum([d for d in recent_dividends if d is not None]) * (4 / len(recent_dividends))
            except Exception:
                pass
        
        # Calculate growth_streak from yfinance dividend data (we can calculate from historical dividends)
        growth_streak = None
        if dividends_dict:
            try:
                # Group dividends by year and calculate totals
                yearly_totals = {}
                for date_str, amount in dividends_dict.items():
                    if date_str and amount:
                        try:
                            year = int(date_str.split('-')[0])
                            if year not in yearly_totals:
                                yearly_totals[year] = 0
                            yearly_totals[year] += float(amount) if amount else 0
                        except Exception:
                            continue
                
                # Calculate consecutive years of growth
                if len(yearly_totals) > 1:
                    sorted_years = sorted(yearly_totals.keys(), reverse=True)
                    streak = 0
                    for i in range(len(sorted_years) - 1):
                        current_year = sorted_years[i]
                        prev_year = sorted_years[i + 1]
                        if yearly_totals[current_year] > yearly_totals[prev_year]:
                            streak += 1
                        else:
                            break
                    growth_streak = streak if streak > 0 else None
            except Exception as e:
                logger.debug(f"Error calculating growth streak for {ticker}: {e}")
                growth_streak = None
        
        # Build dividend metrics with only non-null values
        dividend_metrics = {}
        if dividend_yield is not None:
            dividend_metrics["dividend_yield"] = dividend_yield
        if annual_payout is not None:
            dividend_metrics["annual_payout"] = annual_payout
        if payout_ratio is not None:
            dividend_metrics["payout_ratio"] = payout_ratio
        if growth_streak is not None:
            dividend_metrics["growth_streak"] = growth_streak
        if info.get('dividendFrequency') is not None:
            dividend_metrics["payout_frequency"] = info.get('dividendFrequency')
        if eps is not None:
            dividend_metrics["eps"] = eps
        if five_year_avg_yield is not None:
            dividend_metrics["five_year_avg_yield"] = five_year_avg_yield
        if info.get('lastDividendValue') is not None:
            dividend_metrics["last_dividend_value"] = info.get('lastDividendValue')
        if info.get('trailingAnnualDividendRate') is not None:
            dividend_metrics["trailing_annual_dividend_rate"] = info.get('trailingAnnualDividendRate')
        if info.get('trailingAnnualDividendYield') is not None:
            dividend_metrics["trailing_annual_dividend_yield"] = info.get('trailingAnnualDividendYield')
        
        # 2. Upcoming Dividend Payouts
        ex_dividend_date = info.get('exDividendDate')
        dividend_date = info.get('dividendDate')
        
        # Format dates if they exist (yfinance returns timestamps)
        ex_dividend_date_str = None
        dividend_date_str = None
        if ex_dividend_date:
            try:
                if isinstance(ex_dividend_date, (int, float)):
                    ex_dividend_date_str = datetime.fromtimestamp(ex_dividend_date).strftime("%Y-%m-%d")
                else:
                    ex_dividend_date_str = str(ex_dividend_date)
            except Exception:
                ex_dividend_date_str = str(ex_dividend_date) if ex_dividend_date else None
        
        if dividend_date:
            try:
                if isinstance(dividend_date, (int, float)):
                    dividend_date_str = datetime.fromtimestamp(dividend_date).strftime("%Y-%m-%d")
                else:
                    dividend_date_str = str(dividend_date)
            except Exception:
                dividend_date_str = str(dividend_date) if dividend_date else None
        
        # Calculate days until dates
        days_until_ex_div = None
        days_until_payment = None
        try:
            if ex_dividend_date_str:
                ex_div_dt = datetime.strptime(ex_dividend_date_str, "%Y-%m-%d")
                days_until_ex_div = (ex_div_dt - datetime.now()).days
            if dividend_date_str:
                payment_dt = datetime.strptime(dividend_date_str, "%Y-%m-%d")
                days_until_payment = (payment_dt - datetime.now()).days
        except Exception:
            pass
        
        # Build upcoming payouts with only non-null values
        upcoming_payouts = {}
        if ex_dividend_date_str:
            upcoming_payouts["exDividendDate"] = ex_dividend_date_str
        if annual_payout is not None:
            upcoming_payouts["exDividendAmount"] = annual_payout
        if dividend_date_str:
            upcoming_payouts["paymentDate"] = dividend_date_str
        if days_until_ex_div is not None:
            upcoming_payouts["daysUntilExDividend"] = days_until_ex_div
        if days_until_payment is not None:
            upcoming_payouts["daysUntilPayment"] = days_until_payment
        
        # 3. Dividend History Table
        dividend_history = []
        if dividends_dict:
            try:
                # Convert dividends dict to list format (only yfinance data)
                for date_str, amount in sorted(dividends_dict.items(), reverse=True):
                    try:
                        # Parse date
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                        
                        # Build history entry with only available data
                        history_entry = {
                            "exDivDate": date_str,
                            "amount": amount,
                            "fiscalYear": date_obj.year,
                            "fiscalQuarter": ((date_obj.month - 1) // 3) + 1
                        }
                        dividend_history.append(history_entry)
                    except Exception as e:
                        logger.debug(f"Error parsing dividend date {date_str}: {e}")
                        continue
            except Exception as e:
                logger.warning(f"Error processing dividend history for {ticker}: {e}")
                dividend_history = []
        
        # 4. Dividend Yield Chart Data
        yield_chart_data = []
        if dividends_dict and dividend_yield:
            try:
                # Calculate yield for each dividend date (simplified - using current price)
                current_price = info.get('currentPrice') or info.get('regularMarketPrice')
                if current_price:
                    for date_str, amount in sorted(dividends_dict.items()):
                        try:
                            if amount is not None:
                                yield_value = (amount / current_price * 100) if current_price else None
                                yield_chart_data.append({
                                    "date": date_str,
                                    "yield": yield_value,
                                    "amount": amount
                                })
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"Error creating yield chart data for {ticker}: {e}")
        
        # 5. Payout History Chart Data
        payout_chart_data = []
        if dividends_dict:
            try:
                # Group by year and calculate totals
                yearly_payouts = {}
                for date_str, amount in dividends_dict.items():
                    try:
                        if isinstance(date_str, str):
                            year = int(date_str.split('-')[0])
                        else:
                            year = date_str.year if hasattr(date_str, 'year') else datetime.fromtimestamp(date_str).year
                        
                        if year not in yearly_payouts:
                            yearly_payouts[year] = 0
                        if amount is not None:
                            yearly_payouts[year] += amount
                    except Exception:
                        continue
                
                # Convert to list and calculate growth
                sorted_years = sorted(yearly_payouts.keys(), reverse=True)
                for i, year in enumerate(sorted_years):
                    payout = yearly_payouts[year]
                    growth = None
                    if i < len(sorted_years) - 1:
                        prev_year_payout = yearly_payouts[sorted_years[i + 1]]
                        if prev_year_payout > 0:
                            growth = ((payout - prev_year_payout) / prev_year_payout) * 100
                    
                    payout_chart_data.append({
                        "year": year,
                        "payout": payout,
                        "growth": growth
                    })
                
                # Calculate CAGR (if we have enough years)
                if len(payout_chart_data) >= 2:
                    first_payout = payout_chart_data[-1]["payout"]
                    last_payout = payout_chart_data[0]["payout"]
                    years = payout_chart_data[0]["year"] - payout_chart_data[-1]["year"]
                    if first_payout > 0 and years > 0:
                        cagr = ((last_payout / first_payout) ** (1 / years) - 1) * 100
                        payout_chart_data[0]["cagr"] = cagr
            except Exception as e:
                logger.warning(f"Error creating payout chart data for {ticker}: {e}")
        
        # Calculate summary stats
        current_payout = payout_chart_data[0]["payout"] if payout_chart_data else annual_payout
        yoy_growth = payout_chart_data[0]["growth"] if payout_chart_data else None
        
        # 6. Quick Stats
        last_payment_date = None
        next_payment_date = dividend_date_str
        if dividend_history:
            last_payment_date = dividend_history[0].get("exDivDate") if dividend_history else None
        
        # Build quick stats with only non-null values
        quick_stats = {}
        if info.get('dividendFrequency') is not None:
            quick_stats["frequency"] = info.get('dividendFrequency')
        if last_payment_date:
            quick_stats["lastPaymentDate"] = last_payment_date
        if next_payment_date:
            quick_stats["nextPaymentDate"] = next_payment_date
        if current_payout is not None:
            quick_stats["currentPayout"] = current_payout
        if yoy_growth is not None:
            quick_stats["yoyGrowth"] = yoy_growth
        if payout_chart_data and payout_chart_data[0].get("cagr") is not None:
            quick_stats["cagr"] = payout_chart_data[0].get("cagr")
        
        # Combine all data
        dividend_data = {
            "ticker": ticker,
            "dividendMetrics": clean_mongo_data(dividend_metrics),
            "upcomingPayouts": clean_mongo_data(upcoming_payouts),
            "dividendHistory": clean_mongo_data(dividend_history),
            "yieldChartData": clean_mongo_data(yield_chart_data),
            "payoutChartData": clean_mongo_data(payout_chart_data),
            "quickStats": clean_mongo_data(quick_stats)
        }
        
        return dividend_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching dividend data for {ticker}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


import os
import uvicorn

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

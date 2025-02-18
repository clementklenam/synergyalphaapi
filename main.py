from fastapi import FastAPI, HTTPException, Query, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import logging
import os
from database import MongoManager, get_database
from motor.motor_asyncio import AsyncIOMotorDatabase
from update_manager import UpdateManager
from utils import clean_mongo_data
import math
import re
from typing import List, Dict, Any, Optional
import screener
<<<<<<< HEAD
from datetime import timedelta

# Set up logging
=======
from datetime import timedelta, datetime
from config import Settings
>>>>>>> db45b6f (update to update data every 15 minute)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('stock_api.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


app = FastAPI(title="Stock Market Data API", description="API for accessing S&P 500 stock data")

app.include_router(screener.router)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    logger.info("Starting up the application...")
    logger.info(f"Database will update every {Settings.UPDATE_INTERVAL} seconds")
    
    # Initialize the database connection
    await MongoManager.get_database()
    
    # Start the automatic update process
    await UpdateManager.start_updates()
    logger.info("Automatic updates initialized")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down the application...")
    
    # Stop the automatic update process
    await UpdateManager.stop_updates()
    
    # Close database connections
    await MongoManager.close_connections()

 

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
    if UpdateManager._last_update:
        next_update_time = UpdateManager._last_update + timedelta(seconds=Settings.UPDATE_INTERVAL)
    
    return {
        "last_update": UpdateManager._last_update,
        "next_update": next_update_time,
        "is_updating": UpdateManager._is_updating,
        "update_interval": f"{Settings.UPDATE_INTERVAL} seconds ({Settings.UPDATE_INTERVAL / 60} minutes)"
    }

@app.post("/updates/trigger")
async def trigger_update(background_tasks: BackgroundTasks):
    """Manually trigger a data update"""
    if UpdateManager._is_updating:
        raise HTTPException(status_code=400, detail="Update already in progress")
    
    background_tasks.add_task(UpdateManager.update_stock_data)
    return {"message": "Update triggered", "timestamp": datetime.now()}

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

    except Exception as e:
        logger.error(f"Error fetching cash flow statement for {ticker}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")\
            
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

    
import os
import uvicorn

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

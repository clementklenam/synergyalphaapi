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
# Set up logging
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

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

 


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
):
    """
    Search for companies by ticker symbol in the database.
    Returns matching companies sorted by market cap.
    """
    try:
        # Ensure the query is properly formatted
        search_query = {}
        if query:
            search_query["ticker"] = {"$regex": query.upper(), "$options": "i"}

        projection = {
            "_id": 0,
            "ticker": 1,
            "name": 1,
            "sector": 1,
            "industry": 1,
            "market_cap": 1,
            "exchange": 1,
            "quote.price": 1,
            "quote.change": 1,
            "quote.changesPercentage": 1,
            "quote.volume": 1
        }

        # Fetch data from MongoDB
        cursor = db.companies.find(search_query, projection).sort("market_cap", -1).limit(limit)
        results = await cursor.to_list(length=limit)  # Ensure to use `await` for async operations

        # Format market cap
        for company in results:
            if company.get("market_cap"):
                company["market_cap_billions"] = round(company["market_cap"] / 1_000_000_000, 2)

        return clean_mongo_data({
            "count": len(results),
            "results": results
        })

    except Exception as e:
        logger.error(f"Error in search: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/updates/status")
async def get_update_status():
    """Get the current status of data updates"""
    return {
        "last_update": UpdateManager._last_update,
        "next_update": (
            UpdateManager._last_update + timedelta(seconds=settings.UPDATE_INTERVAL)
            if UpdateManager._last_update
            else None
        ),
        "is_updating": UpdateManager._is_updating
    }

@app.post("/updates/trigger")
async def trigger_update(background_tasks: BackgroundTasks):
    """Manually trigger a data update"""
    if UpdateManager._is_updating:
        raise HTTPException(status_code=400, detail="Update already in progress")
    
    background_tasks.add_task(UpdateManager.update_stock_data)
    return {"message": "Update triggered"}

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
        raise HTTPException(status_code=500, detail="Internal Server Error")

    
import os
import uvicorn

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 1000))
    uvicorn.run(app, host="0.0.0.0", port=port)

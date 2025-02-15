from fastapi import FastAPI, HTTPException, Query
from pymongo import MongoClient
from typing import List, Optional
from datetime import datetime
import logging
from fastapi.middleware.cors import CORSMiddleware
import json
import numpy as np
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

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.floating)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif math.isnan(float(obj)) if isinstance(obj, (float, int)) else False:
            return None
        return super().default(obj)

def clean_mongo_data(data):
    """Clean data retrieved from MongoDB to handle non-JSON serializable values"""
    if isinstance(data, dict):
        return {k: clean_mongo_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_mongo_data(item) for item in data]
    elif isinstance(data, (float, np.floating)) and (math.isnan(data) or math.isinf(data)):
        return None
    elif isinstance(data, (np.integer, np.floating)):
        return float(data)
    elif isinstance(data, datetime):
        return data.isoformat()
    return data

app = FastAPI(title="Stock Market Data API", description="API for accessing S&P 500 stock data")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB connection
MONGODB_URL = "mongodb+srv://admin:Admin123@cluster0.nj0wmq4.mongodb.net/synergy_alpha?retryWrites=true&w=majority"

def get_database():
    client = MongoClient(MONGODB_URL)
    return client["synergy_alpha"]

@app.get("/companies", response_model=List[dict])
async def get_all_companies():
    """Get basic information for all companies"""
    try:
        db = get_database()
        companies = list(db.companies.find({}, {
            "ticker": 1,
            "name": 1,
            "sector": 1,
            "industry": 1,
            "market_cap": 1,
            "exchange": 1,
            "_id": 0
        }))
        return clean_mongo_data(companies)
    except Exception as e:
        logging.error(f"Error fetching companies: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search")
async def search_companies(
    query: Optional[str] = Query(None, description="Search by ticker symbol"),
    limit: int = Query(20, description="Number of results to return", ge=1, le=100)
):
    """
    Search for companies by ticker symbol in the database.
    Returns matching companies sorted by market cap.
    """
    try:
        db = get_database()
        
        # Build the search query for symbols
        search_query = {}
        if query:
            search_query["ticker"] = {"$regex": query.upper(), "$options": "i"}
        
        # Execute search with projection to return relevant fields
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
        
        results = list(db.companies
                      .find(search_query, projection)
                      .sort("market_cap", -1)  # Sort by market cap descending
                      .limit(limit))
        
        # Add formatted market cap in billions for display
        for company in results:
            if company.get("market_cap"):
                company["market_cap_billions"] = round(company["market_cap"] / 1_000_000_000, 2)
        
        return clean_mongo_data({
            "count": len(results),
            "results": results
        })
        
    except Exception as e:
        logging.error(f"Error in search: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/symbols")
async def get_symbols():
    """Get list of all symbols in the database"""
    try:
        db = get_database()
        symbols = list(db.companies.find({}, {
            "_id": 0,
            "ticker": 1,
            "name": 1
        }))
        return clean_mongo_data(symbols)
    except Exception as e:
        logging.error(f"Error fetching symbols: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/companies/{ticker}")
async def get_company_details(ticker: str):
    """Get detailed information for a specific company"""
    try:
        db = get_database()
        company = db.companies.find_one({"ticker": ticker.upper()}, {"_id": 0})
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        return clean_mongo_data(company)
    except Exception as e:
        logging.error(f"Error fetching company {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/companies/{ticker}/quote")
async def get_company_quote(ticker: str):
    """Get current quote for a specific company"""
    try:
        db = get_database()
        company = db.companies.find_one({"ticker": ticker.upper()}, {"quote": 1, "_id": 0})
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        return clean_mongo_data(company["quote"])
    except Exception as e:
        logging.error(f"Error fetching quote for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/companies/{ticker}/prices")
async def get_stock_prices(
    ticker: str,
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format")
):
    """Get historical stock prices for a specific company"""
    try:
        db = get_database()
        company = db.companies.find_one({"ticker": ticker.upper()}, {"stock_prices": 1, "_id": 0})
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        
        prices = company["stock_prices"]
        
        # Filter by date range if provided
        if start_date:
            prices = [p for p in prices if p["date"] >= start_date]
        if end_date:
            prices = [p for p in prices if p["date"] <= end_date]
            
        return clean_mongo_data(prices)
    except Exception as e:
        logging.error(f"Error fetching prices for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/companies/{ticker}/financials")
async def get_financial_statements(ticker: str):
    """Get financial statements for a specific company"""
    try:
        db = get_database()
        company = db.companies.find_one({"ticker": ticker.upper()}, {"financial_statements": 1, "_id": 0})
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        return clean_mongo_data(company["financial_statements"])
    except Exception as e:
        logging.error(f"Error fetching financials for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/companies/{ticker}/metrics")
async def get_key_metrics(ticker: str):
    """Get key metrics for a specific company"""
    try:
        db = get_database()
        company = db.companies.find_one(
            {"ticker": ticker.upper()},
            {"key_metrics": 1, "ttm_ratios": 1, "_id": 0}
        )
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        return clean_mongo_data({
            "key_metrics": company["key_metrics"],
            "ttm_ratios": company["ttm_ratios"]
        })
    except Exception as e:
        logging.error(f"Error fetching metrics for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/sectors")
async def get_sectors():
    """Get list of all sectors and their companies"""
    try:
        db = get_database()
        pipeline = [
            {"$group": {
                "_id": "$sector",
                "companies": {"$push": {
                    "ticker": "$ticker",
                    "name": "$name",
                    "market_cap": "$market_cap"
                }}
            }}
        ]
        sectors = list(db.companies.aggregate(pipeline))
        return clean_mongo_data(sectors)
    except Exception as e:
        logging.error(f"Error fetching sectors: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

import os

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 1000))
    uvicorn.run(app, host="0.0.0.0", port=port)

from enum import Enum
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, Query, Depends, APIRouter
from motor.motor_asyncio import AsyncIOMotorDatabase
import math
import logging
from database import get_database
from utils import clean_mongo_data


router = APIRouter(
    prefix="/screener",
    tags=["screener"]
)

logger = logging.getLogger(__name__)

class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"

class ScreenerFilter(BaseModel):
    market_cap_min: Optional[float] = None
    market_cap_max: Optional[float] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    volume_min: Optional[int] = None
    volume_max: Optional[int] = None
    beta_min: Optional[float] = None
    beta_max: Optional[float] = None
    dividend_yield_min: Optional[float] = None
    dividend_yield_max: Optional[float] = None
    pe_ratio_min: Optional[float] = None
    pe_ratio_max: Optional[float] = None
    price_to_book_min: Optional[float] = None
    price_to_book_max: Optional[float] = None
    debt_to_equity_min: Optional[float] = None
    debt_to_equity_max: Optional[float] = None
    current_ratio_min: Optional[float] = None
    current_ratio_max: Optional[float] = None
    profit_margin_min: Optional[float] = None
    profit_margin_max: Optional[float] = None
    roe_min: Optional[float] = None
    roe_max: Optional[float] = None
    roa_min: Optional[float] = None
    roa_max: Optional[float] = None
    sectors: Optional[List[str]] = None
    industries: Optional[List[str]] = None
    exchanges: Optional[List[str]] = None

@router.post("/screen")
async def screen_stocks(
    filters: ScreenerFilter,
    sort_by: str = Query("market_cap", description="Field to sort by"),
    sort_order: SortOrder = Query(SortOrder.desc, description="Sort order"),
    limit: int = Query(50, ge=1, le=500, description="Number of results to return"),
    page: int = Query(1, ge=1, description="Page number"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Screen stocks based on multiple financial and market criteria.
    Returns paginated results sorted by specified field.
    """
    try:
        # Build the match conditions
        match_conditions: Dict[str, Any] = {}

        # Market Cap Filter
        if filters.market_cap_min is not None or filters.market_cap_max is not None:
            match_conditions["market_cap"] = {}
            if filters.market_cap_min is not None:
                match_conditions["market_cap"]["$gte"] = filters.market_cap_min
            if filters.market_cap_max is not None:
                match_conditions["market_cap"]["$lte"] = filters.market_cap_max

        # Price Filter
        if filters.price_min is not None or filters.price_max is not None:
            match_conditions["price"] = {}
            if filters.price_min is not None:
                match_conditions["price"]["$gte"] = filters.price_min
            if filters.price_max is not None:
                match_conditions["price"]["$lte"] = filters.price_max

        # Volume Filter
        if filters.volume_min is not None or filters.volume_max is not None:
            match_conditions["volume"] = {}
            if filters.volume_min is not None:
                match_conditions["volume"]["$gte"] = filters.volume_min
            if filters.volume_max is not None:
                match_conditions["volume"]["$lte"] = filters.volume_max

        # Beta Filter
        if filters.beta_min is not None or filters.beta_max is not None:
            match_conditions["beta"] = {}
            if filters.beta_min is not None:
                match_conditions["beta"]["$gte"] = filters.beta_min
            if filters.beta_max is not None:
                match_conditions["beta"]["$lte"] = filters.beta_max

        # Dividend Yield Filter
        if filters.dividend_yield_min is not None or filters.dividend_yield_max is not None:
            match_conditions["dividend_yield"] = {}
            if filters.dividend_yield_min is not None:
                match_conditions["dividend_yield"]["$gte"] = filters.dividend_yield_min
            if filters.dividend_yield_max is not None:
                match_conditions["dividend_yield"]["$lte"] = filters.dividend_yield_max

        # P/E Ratio Filter
        if filters.pe_ratio_min is not None or filters.pe_ratio_max is not None:
            match_conditions["price_to_earnings"] = {}
            if filters.pe_ratio_min is not None:
                match_conditions["price_to_earnings"]["$gte"] = filters.pe_ratio_min
            if filters.pe_ratio_max is not None:
                match_conditions["price_to_earnings"]["$lte"] = filters.pe_ratio_max

        # Price to Book Filter
        if filters.price_to_book_min is not None or filters.price_to_book_max is not None:
            match_conditions["price_to_book"] = {}
            if filters.price_to_book_min is not None:
                match_conditions["price_to_book"]["$gte"] = filters.price_to_book_min
            if filters.price_to_book_max is not None:
                match_conditions["price_to_book"]["$lte"] = filters.price_to_book_max

        # Debt to Equity Filter
        if filters.debt_to_equity_min is not None or filters.debt_to_equity_max is not None:
            match_conditions["debt_to_equity"] = {}
            if filters.debt_to_equity_min is not None:
                match_conditions["debt_to_equity"]["$gte"] = filters.debt_to_equity_min
            if filters.debt_to_equity_max is not None:
                match_conditions["debt_to_equity"]["$lte"] = filters.debt_to_equity_max

        # Current Ratio Filter
        if filters.current_ratio_min is not None or filters.current_ratio_max is not None:
            match_conditions["current_ratio"] = {}
            if filters.current_ratio_min is not None:
                match_conditions["current_ratio"]["$gte"] = filters.current_ratio_min
            if filters.current_ratio_max is not None:
                match_conditions["current_ratio"]["$lte"] = filters.current_ratio_max

        # Profit Margin Filter
        if filters.profit_margin_min is not None or filters.profit_margin_max is not None:
            match_conditions["profit_margin"] = {}
            if filters.profit_margin_min is not None:
                match_conditions["profit_margin"]["$gte"] = filters.profit_margin_min
            if filters.profit_margin_max is not None:
                match_conditions["profit_margin"]["$lte"] = filters.profit_margin_max

        # ROE Filter
        if filters.roe_min is not None or filters.roe_max is not None:
            match_conditions["return_on_equity"] = {}
            if filters.roe_min is not None:
                match_conditions["return_on_equity"]["$gte"] = filters.roe_min
            if filters.roe_max is not None:
                match_conditions["return_on_equity"]["$lte"] = filters.roe_max

        # ROA Filter
        if filters.roa_min is not None or filters.roa_max is not None:
            match_conditions["return_on_assets"] = {}
            if filters.roa_min is not None:
                match_conditions["return_on_assets"]["$gte"] = filters.roa_min
            if filters.roa_max is not None:
                match_conditions["return_on_assets"]["$lte"] = filters.roa_max

        # Sector Filter
        if filters.sectors:
            match_conditions["sector"] = {"$in": filters.sectors}

        # Industry Filter
        if filters.industries:
            match_conditions["industry"] = {"$in": filters.industries}

        # Exchange Filter
        if filters.exchanges:
            match_conditions["exchange"] = {"$in": filters.exchanges}

        # Calculate skip for pagination
        skip = (page - 1) * limit

        # Build the aggregation pipeline
        pipeline = [
            {"$match": match_conditions},
            {"$sort": {sort_by: 1 if sort_order == SortOrder.asc else -1}},
            {"$skip": skip},
            {"$limit": limit},
            {
                "$project": {
                    "_id": 0,
                    "ticker": 1,
                    "name": 1,
                    "sector": 1,
                    "industry": 1,
                    "exchange": 1,
                    "market_cap": 1,
                    "price": 1,
                    "changes": 1,
                    "volume": 1,
                    "beta": 1,
                    "dividend_yield": 1,
                    "price_to_earnings": 1,
                    "price_to_book": 1,
                    "debt_to_equity": 1,
                    "current_ratio": 1,
                    "profit_margin": 1,
                    "return_on_equity": 1,
                    "return_on_assets": 1
                }
            }
        ]

        # Execute the aggregation
        results = await db.companies.aggregate(pipeline).to_list(length=limit)
        
        # Get total count of matching documents
        total_count = await db.companies.count_documents(match_conditions)

        # Calculate total pages
        total_pages = math.ceil(total_count / limit)

        return clean_mongo_data({
            "page": page,
            "total_pages": total_pages,
            "total_results": total_count,
            "results_per_page": limit,
            "results": results
        })

    except Exception as e:
        logger.error(f"Error in stock screener: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Helper endpoint to get available values for filters
@router.get("/filter-options")
async def get_screener_filter_options(
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get available options for screener filters"""
    try:
        # Get unique sectors
        sectors = await db.companies.distinct("sector")
        
        # Get unique industries
        industries = await db.companies.distinct("industry")
        
        # Get unique exchanges
        exchanges = await db.companies.distinct("exchange")
        
        # Get ranges for numerical filters
        ranges = await db.companies.aggregate([
            {
                "$group": {
                    "_id": None,
                    "min_market_cap": {"$min": "$market_cap"},
                    "max_market_cap": {"$max": "$market_cap"},
                    "min_price": {"$min": "$price"},
                    "max_price": {"$max": "$price"},
                    "min_volume": {"$min": "$volume"},
                    "max_volume": {"$max": "$volume"},
                    "min_pe_ratio": {"$min": "$price_to_earnings"},
                    "max_pe_ratio": {"$max": "$price_to_earnings"}
                }
            }
        ]).to_list(length=1)

        return clean_mongo_data({
            "sectors": sectors,
            "industries": industries,
            "exchanges": exchanges,
            "ranges": ranges[0] if ranges else {}
        })

    except Exception as e:
        logger.error(f"Error fetching screener options: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import logging
from settings import settings
from typing import Optional
from typing import Dict, Any

logger = logging.getLogger(__name__)

class MongoManager:
    _client: Optional[AsyncIOMotorClient] = None
    _db: Optional[AsyncIOMotorDatabase] = None

    @classmethod
    async def get_database(cls) -> AsyncIOMotorDatabase:
        """Get or create database connection"""
        if cls._db is None:
            await cls._connect()
        return cls._db

    @classmethod
    async def _connect(cls) -> None:
        """Create database connection"""
        if cls._client is None:
            try:
                cls._client = AsyncIOMotorClient(settings.MONGODB_URL)
                cls._db = cls._client[settings.DATABASE_NAME]
                # Verify connection
                await cls._db.command('ping')
                logger.info("Connected to MongoDB")
            except Exception as e:
                logger.error(f"Error connecting to MongoDB: {str(e)}")
                cls._client = None
                cls._db = None
                raise


# Add your new method here
    @classmethod
    async def update_company_data(cls, symbol: str, data: Dict[str, Any]) -> bool:
        """
        Update company data in the database
        
        Args:
            symbol: Stock ticker symbol
            data: Dictionary containing updated company data
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            db = await cls.get_database()
            result = await db.companies.update_one(
                {"ticker": symbol},
                {"$set": data},
                upsert=True
            )
            logger.info(f"Updated {symbol} in database: matched={result.matched_count}, modified={result.modified_count}, upserted={result.upserted_id is not None}")
            return True
        except Exception as e:
            logger.error(f"Error updating company data for {symbol}: {str(e)}")
            return False
    @classmethod
    async def close_connections(cls) -> None:
        """Close database connections"""
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            cls._db = None
            logger.info("Closed MongoDB connections")

async def get_database() -> AsyncIOMotorDatabase:
    """FastAPI dependency for database access"""
    db = await MongoManager.get_database()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection not available")
    return db
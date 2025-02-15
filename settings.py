
from pydantic_settings import BaseSettings
import logging
from functools import lru_cache

class Settings(BaseSettings):
    # MongoDB settings
    MONGODB_URL: str = "mongodb+srv://admin:Admin123@cluster0.nj0wmq4.mongodb.net/synergy_alpha?retryWrites=true&w=majority"
    DATABASE_NAME: str = "synergy_alpha"
    
    # Logging settings
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = '%(asctime)s - %(levelname)s - %(message)s'
    
    # API settings
    UPDATE_INTERVAL: int = 3600  # 1 hour in seconds
    FMP_API_KEY: str = "2BZ4GCJ340NBnmb5v09MJbXBAIjhIHOP"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
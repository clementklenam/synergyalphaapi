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
    UPDATE_INTERVAL: int = 900  # 15 minutes in seconds for testing
    
    # API keys
    FMP_API_KEY: str = "kP8vRt8RSXMr8BHEsk1iT23zzm8Mrf7m"
    FINNHUB_API_KEY: str = "cpdoi4hr01qh24fljfigcpdoi4hr01qh24fljfj0"  # Add your key here
    LOGO_API_TOKEN: str = "pk_XyGwTpIsTY6mPXuKHI6DDA"  # Add your token here
    
    # Testing settings
    UPDATE_CONCURRENCY: int = 5
    UPDATE_TIMEOUT: int = 10  # API request timeout in seconds
    MAX_COMPANIES_PER_UPDATE: int = 503  # Limit company updates for testing
    
    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
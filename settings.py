import asyncio
import logging
from typing import Optional, Dict, Any, List
import yfinance as yf
import pandas as pd
import aiohttp
from datetime import datetime
from pydantic import BaseModel
from pydantic_settings import BaseSettings
import base64
import os

logger = logging.getLogger(__name__)

# First, create the Pydantic settings model
class _Settings(BaseSettings):
    # MongoDB settings
    MONGODB_URL: str = "mongodb+srv://admin:Admin123@cluster0.nj0wmq4.mongodb.net/synergy_alpha?retryWrites=true&w=majority"
    DATABASE_NAME: str = "synergy_alpha"
    
    # Logging settings
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = '%(asctime)s - %(levelname)s - %(message)s'
    
    # API settings
    CHECK_INTERVAL: int = 300  # Check for new data every 5 minutes
    UPDATE_INTERVAL: int = 3600
    
    # API keys
    FMP_API_KEY: str = "kP8vRt8RSXMr8BHEsk1iT23zzm8Mrf7m"
    FINNHUB_API_KEY: str = "cpdoi4hr01qh24fljfigcpdoi4hr01qh24fljfj0"
    LOGO_API_TOKEN: str = "pk_Wh0bWpJsTpWNjoJeNcw_Cw"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Then, create a singleton instance
_settings = _Settings()

# Create a class that provides class-level access to the instance values
class Settings:
    # MongoDB settings
    MONGODB_URL = _settings.MONGODB_URL
    DATABASE_NAME = _settings.DATABASE_NAME
    
    # Logging settings
    LOG_LEVEL = _settings.LOG_LEVEL
    LOG_FORMAT = _settings.LOG_FORMAT
    
    # API settings
    CHECK_INTERVAL = _settings.CHECK_INTERVAL
    UPDATE_INTERVAL = _settings.UPDATE_INTERVAL
    
    # API keys
    FMP_API_KEY = _settings.FMP_API_KEY
    FINNHUB_API_KEY = _settings.FINNHUB_API_KEY
    LOGO_API_TOKEN = _settings.LOGO_API_TOKEN

# For backwards compatibility, keep the settings instance too
settings = _settings
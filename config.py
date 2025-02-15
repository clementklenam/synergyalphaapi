from pydantic import BaseModel
import logging

class Settings:
    MONGODB_URL = "mongodb+srv://admin:Admin123@cluster0.nj0wmq4.mongodb.net/synergy_alpha?retryWrites=true&w=majority"
    DATABASE_NAME = "synergy_alpha"
    LOG_LEVEL = logging.INFO
    LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
    UPDATE_INTERVAL = 3600  # 1 hour in seconds
    FMP_API_KEY = "2BZ4GCJ340NBnmb5v09MJbXBAIjhIHOP"

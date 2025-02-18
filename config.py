from pydantic import BaseModel
import logging

class Settings:
    MONGODB_URL = "mongodb+srv://admin:Admin123@cluster0.nj0wmq4.mongodb.net/synergy_alpha?retryWrites=true&w=majority"
    DATABASE_NAME = "synergy_alpha"
    LOG_LEVEL = logging.INFO
    LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
    UPDATE_INTERVAL = 3600  # 1 hour in seconds
    FMP_API_KEY = "kP8vRt8RSXMr8BHEsk1iT23zzm8Mrf7m"
    FINNHUB_API_KEY: str = "cpdoi4hr01qh24fljfigcpdoi4hr01qh24fljfj0"
    LOGO_API_TOKEN: str = "pk_Wh0bWpJsTpWNjoJeNcw_Cw"
    
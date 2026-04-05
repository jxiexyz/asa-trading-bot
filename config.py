import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = "llama-3.1-8b-instant"
    RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    WALLET_KEY = os.getenv("WALLET_PRIVATE_KEY")
    MAX_BUY_SOL = float(os.getenv("MAX_BUY_SOL", "0.1"))
    STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PERCENT", "20"))
    TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PERCENT", "50"))
    MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY_USD", "10000"))
    MIN_VOLUME = float(os.getenv("MIN_VOLUME_24H", "5000"))
    SCAN_INTERVAL = 30

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Админы
ADMINS_RAW = os.getenv("ADMIN_IDS", "")
ADMINS = [int(x.strip()) for x in ADMINS_RAW.split(",") if x.strip().isdigit()]

# PostgreSQL (Supabase pooler)
DB_HOST = os.getenv("DB_HOST", "")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "postgres")

# AI (n1n.ai, OpenAI-совместимый)
N1N_API_KEY = os.getenv("N1N_API_KEY", "")
N1N_BASE_URL = os.getenv("N1N_BASE_URL", "https://api.n1n.ai/v1")
N1N_MODEL = os.getenv("N1N_MODEL", "gpt-4o-mini")

# Gemini (vision, fallback)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Биржи
BINANCE_TESTNET_KEY = os.getenv("BINANCE_TESTNET_KEY", "")
BINANCE_TESTNET_SECRET = os.getenv("BINANCE_TESTNET_SECRET", "")
BYBIT_TESTNET_KEY = os.getenv("BYBIT_TESTNET_KEY", "")
BYBIT_TESTNET_SECRET = os.getenv("BYBIT_TESTNET_SECRET", "")

# Прочее
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
PORT = int(os.getenv("PORT", "10000"))
FREE_MODE = os.getenv("FREE_MODE", "true").lower() in ("1", "true", "yes", "on")
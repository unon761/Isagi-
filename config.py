"""
Configuration for Isagi Bot.

All secrets are read from environment variables (or a .env file loaded via
python-dotenv). Nothing sensitive is hardcoded here — see .env for local
values and README.md for deployment notes.
"""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# Telegram user_id of the bot owner/admin.
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7568676840"))

# Groq models
VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")
TEXT_MODEL = os.environ.get("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")

# Groq allows a max of 5 images per vision request.
MAX_IMAGES_PER_VISION_CALL = 5

# Economy
COST_PER_GENERATION = 4
FREE_TRIAL_GENERATIONS = 3

# SQLite database file
DB_PATH = os.environ.get("DB_PATH", "isagi_bot.db")

# Plans: name -> duration in days
PLAN_DAYS = {
    "1day": 1,
    "3day": 3,
    "7day": 7,
    "15day": 15,
    "31day": 31,
    "365day": 365,
}

OWNER_CONTACT = "@Tanjiro7709"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Put it in your .env file or environment.")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set. Put it in your .env file or environment.")

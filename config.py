from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "sentiment.db"
MODELS_DIR = BASE_DIR / "models"

LOCAL_AI_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

MAX_INTERNAL_LINKS = 8
MAX_INTERNAL_PAGES_TO_READ = 5
MAX_PAGE_TEXT_CHARS = 15000
MAX_TOTAL_AI_TEXT_CHARS = 28000
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'users.db')

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN не установлен")

YANDEX_GPT_API_KEY = os.getenv("YANDEX_GPT_API_KEY")
YANDEX_GPT_FOLDER_ID = os.getenv("YANDEX_GPT_FOLDER_ID")
YANDEX_SPEECH_API_KEY = os.getenv("YANDEX_SPEECH_API_KEY")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# RateLimiter Config
MAX_REQUESTS_PER_MINUTE = 2      # <-- 3 запроса в минуту на пользователя
WINDOW_SECONDS = 60              # окно в секундах для подсчёта
CONCURRENT_GPT = 10              # <-- глобальный лимит одновременных запросов к GPT

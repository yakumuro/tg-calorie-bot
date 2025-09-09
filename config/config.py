import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Определяем корень проекта
BASE_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'users.db')

# Проверка наличия обязательных переменных
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("FATAL: TELEGRAM_TOKEN не установлен в .env или переменных окружения")

YANDEX_GPT_API_KEY = os.getenv("YANDEX_GPT_API_KEY")
YANDEX_GPT_FOLDER_ID = os.getenv("YANDEX_GPT_FOLDER_ID")

# Уровень логирования
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
import logging
from logging.handlers import RotatingFileHandler
import os

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Настройка логирования
logger = logging.getLogger("calorie_bot")
logger.setLevel(logging.DEBUG)  # DEBUG — максимально подробное логирование

# Лог в файл с ротацией
file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "bot.log"),
    maxBytes=5*1024*1024,  # 5 МБ на файл
    backupCount=5,          # храним 5 старых файлов
    encoding="utf-8"
)
file_formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
file_handler.setFormatter(file_formatter)

# Лог в консоль
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
console_handler.setFormatter(console_formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

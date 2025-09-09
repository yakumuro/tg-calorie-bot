import sqlite3
import os
from config.config import DATABASE_PATH

logger = __import__('logging').getLogger(__name__)


def init_db():
    """Создаёт папку data и таблицу users."""
    try:
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row  # доступ по имени колонки
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                weight REAL NOT NULL,
                height INTEGER NOT NULL,
                age INTEGER NOT NULL,
                gender TEXT NOT NULL,
                activity_level TEXT NOT NULL,
                daily_calories REAL NOT NULL
            )
        ''')
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована успешно.")
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {e}")
        raise


def get_db_connection():
    """Возвращает подключение к БД с row_factory."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def add_user(user_id, name, weight, height, age, gender, activity_level, daily_calories):
    """Добавляет или обновляет пользователя."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, name, weight, height, age, gender, activity_level, daily_calories)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, name, weight, height, age, gender, activity_level, daily_calories))
        conn.commit()
        conn.close()
        logger.info(f"Пользователь {user_id} добавлен/обновлён.")
    except Exception as e:
        logger.error(f"Ошибка при добавлении пользователя {user_id}: {e}")
        raise


def get_user(user_id):
    """Получает пользователя по ID."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        logger.info(f"Пользователь {user_id} получен: {'да' if user else 'нет'}")
        return user
    except Exception as e:
        logger.error(f"Ошибка при получении пользователя {user_id}: {e}")
        raise
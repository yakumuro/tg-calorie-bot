import sqlite3
import os

DB_PATH = "data/users.db"

def init_db():
    """Создаёт таблицы при первом запуске"""
    os.makedirs("data", exist_ok=True)  # папка для БД
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            weight REAL NOT NULL,
            height REAL NOT NULL,
            age INTEGER NOT NULL,
            gender TEXT NOT NULL,  -- 'male' или 'female'
            daily_calorie_limit REAL
        )
    """)

    # Таблица приёмов пищи
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            food_text TEXT NOT NULL,
            calories REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")
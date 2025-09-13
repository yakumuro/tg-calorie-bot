import sqlite3
import os
from config.config import DATABASE_PATH

def init_db():
    try:
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
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
            daily_calories REAL NOT NULL,
            protein_norm REAL DEFAULT 0,
            fat_norm REAL DEFAULT 0,
            carbs_norm REAL DEFAULT 0
        )
    ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                food_text TEXT NOT NULL,
                calories REAL NOT NULL,
                protein REAL DEFAULT 0,
                fat REAL DEFAULT 0,
                carbs REAL DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        conn.commit()
        conn.close()
        print("База данных инициализирована")
    except Exception as e:
        print(f"Ошибка БД: {e}")
        raise


def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def calculate_macros(weight: float, daily_calories: float) -> tuple[float, float, float]:
    protein_g = weight * 1.8
    fat_g = weight * 1.0
    protein_cal = protein_g * 4
    fat_cal = fat_g * 9
    carbs_cal = daily_calories - (protein_cal + fat_cal)
    carbs_g = max(carbs_cal / 4, 0)
    return round(protein_g), round(fat_g), round(carbs_g)


def add_user(user_id, name, weight, height, age, gender, activity_level, daily_calories):
    protein_norm, fat_norm, carbs_norm = calculate_macros(weight, daily_calories)

    conn = get_db_connection()
    conn.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, name, weight, height, age, gender, activity_level, daily_calories, protein_norm, fat_norm, carbs_norm)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, name, weight, height, age, gender, activity_level,
          daily_calories, protein_norm, fat_norm, carbs_norm))
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return user


def add_meal(user_id, food_text, calories, protein=0, fat=0, carbs=0):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO meals (user_id, food_text, calories, protein, fat, carbs) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, food_text, calories, protein, fat, carbs)
    )
    conn.commit()
    conn.close()


def _row_to_safe_dict(row):
    """Конвертирует sqlite row в словарь с безопасными числами"""
    if not row:
        return {"calories": 0, "protein": 0, "fat": 0, "carbs": 0}
    return {k: row[k] if row[k] is not None else 0 for k in ["calories", "protein", "fat", "carbs"]}

def get_stats(user_id):
    conn = get_db_connection()
    
    row = conn.execute("""
        SELECT SUM(calories) as calories,
               SUM(protein) as protein,
               SUM(fat) as fat,
               SUM(carbs) as carbs
        FROM meals
        WHERE user_id = ? AND date(timestamp) = date('now')
    """, (user_id,)).fetchone()
    day = _row_to_safe_dict(row)
    
    row = conn.execute("""
        SELECT SUM(calories) as calories,
               SUM(protein) as protein,
               SUM(fat) as fat,
               SUM(carbs) as carbs
        FROM meals
        WHERE user_id = ? AND date(timestamp) >= date('now', '-6 days')
    """, (user_id,)).fetchone()
    week = _row_to_safe_dict(row)
    
    row = conn.execute("""
        SELECT SUM(calories) as calories,
               SUM(protein) as protein,
               SUM(fat) as fat,
               SUM(carbs) as carbs
        FROM meals
        WHERE user_id = ? AND date(timestamp) >= date('now', '-29 days')
    """, (user_id,)).fetchone()
    month = _row_to_safe_dict(row)
    
    conn.close()
    return {"day": day, "week": week, "month": month}



def get_meals_last_7_days(user_id):
    """Возвращает приёмы пищи за последние 7 дней"""
    conn = get_db_connection()
    meals = conn.execute("""
        SELECT food_text, calories, timestamp 
        FROM meals 
        WHERE user_id = ? 
          AND date(timestamp) >= date('now', '-6 days')
        ORDER BY timestamp DESC
    """, (user_id,)).fetchall()
    conn.close()
    return meals

def delete_meals_for_day(user_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM meals WHERE user_id=? AND date(timestamp, 'localtime') = date('now', 'localtime')",
        (user_id,)
    )
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_count > 0
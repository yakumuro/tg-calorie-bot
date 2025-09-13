import sqlite3
import os
from config.config import DATABASE_PATH
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def init_db():
    try:
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Создаём таблицу с новыми полями (если ещё нет)
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
            carbs_norm REAL DEFAULT 0,
            goal_type TEXT DEFAULT 'maintain',
            target_weight REAL,
            goal_rate TEXT
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

        # Миграция: если таблица users была старой — добавим колонки (без потери данных)
        existing = [r["name"] for r in cursor.execute("PRAGMA table_info(users)").fetchall()]
        if 'goal_type' not in existing:
            cursor.execute("ALTER TABLE users ADD COLUMN goal_type TEXT DEFAULT 'maintain'")
        if 'target_weight' not in existing:
            cursor.execute("ALTER TABLE users ADD COLUMN target_weight REAL")
        if 'goal_rate' not in existing:
            cursor.execute("ALTER TABLE users ADD COLUMN goal_rate TEXT")
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

# --- Макросы: добавлены параметры факторности (по умолчанию старые значения) ---
def calculate_macros(weight: float, daily_calories: float, protein_factor: float = 1.8, fat_factor: float = 1.0):
    protein_g = weight * protein_factor
    fat_g = weight * fat_factor
    protein_cal = protein_g * 4
    fat_cal = fat_g * 9
    carbs_cal = daily_calories - (protein_cal + fat_cal)
    carbs_g = max(carbs_cal / 4, 0)
    return round(protein_g), round(fat_g), round(carbs_g)


def add_user(user_id, name, weight, height, age, gender, activity_level, daily_calories,
             goal_type=None, target_weight=None, goal_rate=None):
    """
    Сохраняет или обновляет пользователя.
    goal_type/target_weight/goal_rate опциональны: если None — берутся из существующей записи (чтобы не затирать при правках).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Получаем существующего user, если есть — чтобы сохранить goal-поля, если не передали
    existing = cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

    if existing:
        if goal_type is None:
            goal_type = existing["goal_type"]
        if target_weight is None:
            target_weight = existing["target_weight"]
        if goal_rate is None:
            goal_rate = existing["goal_rate"]
    else:
        if goal_type is None:
            goal_type = 'maintain'

    protein_norm, fat_norm, carbs_norm = calculate_macros(weight, daily_calories)

    cursor.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, name, weight, height, age, gender, activity_level, daily_calories, protein_norm, fat_norm, carbs_norm, goal_type, target_weight, goal_rate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, name, weight, height, age, gender, activity_level,
          daily_calories, protein_norm, fat_norm, carbs_norm, goal_type, target_weight, goal_rate))
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def add_meal(user_id, food_text, calories, protein=0, fat=0, carbs=0):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO meals (user_id, food_text, calories, protein, fat, carbs) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, food_text, calories, protein, fat, carbs)
    )
    conn.commit()
    conn.close()


# --- Безопасная конвертация row -> dict с числами, заменяем None на 0 ---
def _row_to_safe_dict(row):
    if not row:
        return {"calories": 0, "protein": 0, "fat": 0, "carbs": 0}
    return {
        "calories": row["calories"] if row["calories"] is not None else 0,
        "protein": row["protein"] if row["protein"] is not None else 0,
        "fat": row["fat"] if row["fat"] is not None else 0,
        "carbs": row["carbs"] if row["carbs"] is not None else 0
    }


def get_stats(user_id):
    conn = get_db_connection()
    row = conn.execute("""
        SELECT 
            SUM(calories) as calories,
            SUM(protein) as protein,
            SUM(fat) as fat,
            SUM(carbs) as carbs
        FROM meals 
        WHERE user_id = ? AND date(timestamp) = date('now')
    """, (user_id,)).fetchone()
    day = _row_to_safe_dict(row)

    row = conn.execute("""
        SELECT 
            SUM(calories) as calories,
            SUM(protein) as protein,
            SUM(fat) as fat,
            SUM(carbs) as carbs
        FROM meals 
        WHERE user_id = ? AND date(timestamp) >= date('now', '-6 days')
    """, (user_id,)).fetchone()
    week = _row_to_safe_dict(row)

    row = conn.execute("""
        SELECT 
            SUM(calories) as calories,
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

def get_meals_last_30_days(user_id: int):
    """Получает приёмы пищи за последние 30 дней"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT food_text, calories, protein, fat, carbs, timestamp
        FROM meals 
        WHERE user_id = ? AND date(timestamp) >= date('now', '-30 days')
        ORDER BY timestamp DESC
    """, (user_id,))
    
    meals = []
    for row in cursor.fetchall():
        meals.append({
            'food_text': row[0],
            'calories': row[1],
            'protein': row[2],
            'fat': row[3],
            'carbs': row[4],
            'timestamp': row[5]
        })
    
    conn.close()
    return meals

def get_user_goal_info(user_id: int):
    """Получает информацию о цели пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT goal_type, target_weight, goal_rate, weight
        FROM users 
        WHERE user_id = ?
    """, (user_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0] != 'maintain':  # Если цель не "поддерживать"
        return {
            'goal_type': row[0],
            'target_weight': row[1],
            'goal_rate': row[2],
            'current_weight': row[3]
        }
    return None

def update_goal_start_date(user_id: int, start_date: datetime):
    """Обновляет дату начала цели"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Проверяем существование колонки
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'goal_start_date' not in columns:
            logger.info(f"Adding goal_start_date column for user {user_id}")
            cursor.execute("ALTER TABLE users ADD COLUMN goal_start_date TEXT")
        
        cursor.execute("""
            UPDATE users 
            SET goal_start_date = ? 
            WHERE user_id = ?
        """, (start_date.isoformat(), user_id))
        
        conn.commit()
        logger.info(f"Goal start date updated for user {user_id}: {start_date.isoformat()}")
        
    except Exception as e:
        logger.error(f"Error updating goal start date for user {user_id}: {e}")
        conn.rollback()
    finally:
        conn.close()

def get_goal_start_date(user_id: int):
    """Получает дату начала цели"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Проверяем существование колонки
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'goal_start_date' not in columns:
            logger.warning(f"goal_start_date column doesn't exist for user {user_id}")
            return None
            
        cursor.execute("SELECT goal_start_date FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        if row and row[0]:
            start_date = datetime.fromisoformat(row[0])
            logger.info(f"Retrieved goal start date for user {user_id}: {start_date}")
            return start_date
        else:
            logger.warning(f"No goal start date found for user {user_id}")
            return None
            
    except Exception as e:
        logger.error(f"Error getting goal start date for user {user_id}: {e}")
        return None
    finally:
        conn.close()
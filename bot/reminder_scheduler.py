from datetime import time, timedelta, datetime
import pytz
from bot.database import get_db_connection
from logger_config import logger

# Функция для отправки напоминаний
async def send_reminder(context):
    application = context.application

    cutoff = datetime.utcnow() - timedelta(hours=12)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.user_id 
        FROM users u
        LEFT JOIN (
            SELECT user_id, MAX(timestamp) as last_meal
            FROM meals GROUP BY user_id
        ) m ON u.user_id = m.user_id
        WHERE u.notifications_enabled = 1
          AND (m.last_meal IS NULL OR datetime(m.last_meal) < ?)
    """, (cutoff.isoformat(),))
    users = [row[0] for row in cursor.fetchall()]
    conn.close()

    for user_id in users:
        try:
            await application.bot.send_message(
                chat_id=user_id,
                text=(
                    "Не забывай вносить приёмы пищи!\n\n"
                    "Если будешь записывать — достигнешь своей цели быстрее 💪\n\n"
                    "Уведомления можно отключить в ⚙ Настройках."
                )
            )
            logger.info(f"Sent reminder to user {user_id}")
        except Exception as e:
            logger.error(f"Error sending reminder to user {user_id}: {e}")

# Регистрация задачи
def setup_scheduler(application):
    moscow_tz = pytz.timezone("Europe/Moscow")
    # Каждый день в 10:00 по Москве
    application.job_queue.run_daily(
        send_reminder,
        time=time(hour=10, minute=00, tzinfo=moscow_tz)
    )
    logger.info("Reminder scheduler started (daily at 10:00 MSK)")

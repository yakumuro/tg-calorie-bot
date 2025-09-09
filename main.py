import logging
import os
from telegram.ext import Application
from config.config import TELEGRAM_TOKEN, DATABASE_PATH, LOG_LEVEL
from bot.handlers import conv_handler, profile_handler
from bot.database import init_db

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO)
)
logger = logging.getLogger(__name__)


async def error_handler(update, context):
    """Логирует исключения и уведомляет пользователя."""
    logger.error(f"Update {update} вызвал ошибку: {context.error}", exc_info=True)
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "Произошла ошибка. Попробуй ещё раз или напиши /start."
        )


def main():
    """Запускает бота."""
    # Инициализируем базу данных
    init_db()

    # Создаём приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавляем обработчики
    application.add_handler(conv_handler)
    application.add_handler(profile_handler)
    application.add_error_handler(error_handler)

    logger.info("Бот запущен. Ожидание обновлений...")
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
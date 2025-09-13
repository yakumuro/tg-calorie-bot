import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
from config.config import TELEGRAM_TOKEN, LOG_LEVEL
from bot.database import init_db
from bot.handlers import (
    conv_handler,
    profile_handler,
    meal_conv_handler,
    stats_handler,
    edit_conv_handler,
    confirm_handler,
    retry_handler,
    last_7_days_handler,
    clear_today_handler,
    fallback_handler,
    # edit_goal_conv
)

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO)
)
logger = logging.getLogger(__name__)


# Глобальный обработчик ошибок
async def error_handler(update, context):
    logger.error(f"Error: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text("Ошибка. Попробуй ещё раз.")


def main():
    # Инициализация базы
    init_db()

    # Создаём приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # 🔹 Регистрация всех обработчиков
    app.add_handler(conv_handler)          # регистрация (имя, вес, рост, пол, активность)
    app.add_handler(profile_handler)       # просмотр профиля
    app.add_handler(meal_conv_handler)     # добавление приёмов пищи
    app.add_handler(stats_handler)         # статистика
    app.add_handler(edit_conv_handler)     # редактирование профиля (с edit_field_handler внутри!)
    app.add_handler(confirm_handler)       # подтверждение еды
    app.add_handler(retry_handler)         # повтор ввода еды
    app.add_handler(last_7_days_handler)   # просмотр меню за 7 дней
    app.add_handler(clear_today_handler)   # удаление пищи за текущий день
    # app.add_handler(edit_goal_conv) # редактирвоание целей

    # Обработчик ошибок
    app.add_error_handler(error_handler)

    # Обработчик ввода в чат без выбора кнопки меню
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_handler))

    logger.info("Бот запущен ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
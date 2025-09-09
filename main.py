import logging
from telegram.ext import Application
from config.config import TELEGRAM_TOKEN, LOG_LEVEL
from bot.database import init_db
from bot.handlers import last_7_days_handler, retry_handler, confirm_handler, conv_handler, profile_handler, meal_conv_handler, stats_handler, edit_conv_handler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO)
)
logger = logging.getLogger(__name__)


async def error_handler(update, context):
    logger.error(f"Error: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text("Ошибка. Попробуй ещё раз.")


def main():
    init_db()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(conv_handler)
    app.add_handler(profile_handler)
    app.add_handler(meal_conv_handler)
    app.add_handler(stats_handler)
    app.add_handler(edit_conv_handler)
    app.add_handler(confirm_handler)
    app.add_handler(retry_handler)
    app.add_handler(last_7_days_handler)
    app.add_error_handler(error_handler)

    logger.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
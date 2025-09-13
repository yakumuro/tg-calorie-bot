import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
from config.config import TELEGRAM_TOKEN, LOG_LEVEL
from bot.database import init_db
from bot.handlers import (
    conv_handler,
    profile_handler,
    meal_conv_handler,
    stats_handler,
    confirm_handler,
    retry_handler,
    last_7_days_handler,
    clear_today_handler,
    fallback_handler,
    # Новые обработчики для редактирования профиля
    edit_profile_handler,
    edit_name_handler,
    edit_weight_handler,
    edit_height_handler,
    edit_age_handler,
    edit_gender_handler,
    edit_activity_handler,
    edit_goal_handler,
    set_gender_male_handler,
    set_gender_female_handler,
    set_activity_none_handler,
    set_activity_low_handler,
    set_activity_medium_handler,
    set_activity_high_handler,
    set_goal_maintain_handler,
    set_goal_lose_handler,
    set_goal_gain_handler,
    set_rate_lose_slow_handler,
    set_rate_lose_medium_handler,
    set_rate_lose_fast_handler,
    set_rate_gain_slow_handler,
    set_rate_gain_medium_handler,
    set_rate_gain_fast_handler,
    handle_all_text_input,
    show_weekly_chart,
    show_monthly_chart,
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
    
    # Новые обработчики редактирования профиля (заменяют edit_conv_handler)
    app.add_handler(edit_profile_handler)  # начало редактирования профиля
    app.add_handler(edit_name_handler)     # редактирование имени
    app.add_handler(edit_weight_handler)   # редактирование веса
    app.add_handler(edit_height_handler)   # редактирование роста
    app.add_handler(edit_age_handler)      # редактирование возраста
    app.add_handler(edit_gender_handler)   # редактирование пола
    app.add_handler(edit_activity_handler) # редактирование активности
    app.add_handler(edit_goal_handler)     # редактирование цели
    
    # Обработчики для кнопок выбора пола
    app.add_handler(set_gender_male_handler)
    app.add_handler(set_gender_female_handler)
    
    # Обработчики для кнопок выбора активности
    app.add_handler(set_activity_none_handler)
    app.add_handler(set_activity_low_handler)
    app.add_handler(set_activity_medium_handler)
    app.add_handler(set_activity_high_handler)
    
    # Обработчики для кнопок выбора цели
    app.add_handler(set_goal_maintain_handler)
    app.add_handler(set_goal_lose_handler)
    app.add_handler(set_goal_gain_handler)
    
    # Обработчики для выбора темпа достижения цели
    app.add_handler(set_rate_lose_slow_handler)
    app.add_handler(set_rate_lose_medium_handler)
    app.add_handler(set_rate_lose_fast_handler)
    app.add_handler(set_rate_gain_slow_handler)
    app.add_handler(set_rate_gain_medium_handler)
    app.add_handler(set_rate_gain_fast_handler)

    # Обработчики графиков
    app.add_handler(CallbackQueryHandler(show_weekly_chart, pattern="chart_week"))
    app.add_handler(CallbackQueryHandler(show_monthly_chart, pattern="chart_month"))
    
    # Обработчики текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_text_input))
    
    # Остальные обработчики
    app.add_handler(confirm_handler)       # подтверждение еды
    app.add_handler(retry_handler)         # повтор ввода еды
    app.add_handler(last_7_days_handler)   # просмотр меню за 7 дней
    app.add_handler(clear_today_handler)   # удаление пищи за текущий день

    # Обработчик ошибок
    app.add_error_handler(error_handler)

    # Обработчик ввода в чат без выбора кнопки меню
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_handler))

    logger.info("Бот запущен ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
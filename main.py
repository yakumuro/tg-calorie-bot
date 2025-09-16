from logger_config import logger
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
from config.config import TELEGRAM_TOKEN
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
    show_goal_chart,
    show_current_progress,
    voice_message_handler,
)


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

    # Регистрация всех обработчиков (ВАЖЕН ПОРЯДОК!)
    
    # 1. Сначала ConversationHandler'ы
    app.add_handler(conv_handler)          # регистрация
    app.add_handler(meal_conv_handler)     # добавление приёмов пищи
    
    # 2. Потом обычные обработчики
    app.add_handler(profile_handler)       # просмотр профиля
    app.add_handler(stats_handler)         # статистика
    
    # 3. Обработчики редактирования профиля
    app.add_handler(edit_profile_handler)
    app.add_handler(edit_name_handler)
    app.add_handler(edit_weight_handler)
    app.add_handler(edit_height_handler)
    app.add_handler(edit_age_handler)
    app.add_handler(edit_gender_handler)
    app.add_handler(edit_activity_handler)
    app.add_handler(edit_goal_handler)
    
    # 4. Обработчики кнопок
    app.add_handler(set_gender_male_handler)
    app.add_handler(set_gender_female_handler)
    app.add_handler(set_activity_none_handler)
    app.add_handler(set_activity_low_handler)
    app.add_handler(set_activity_medium_handler)
    app.add_handler(set_activity_high_handler)
    app.add_handler(set_goal_maintain_handler)
    app.add_handler(set_goal_lose_handler)
    app.add_handler(set_goal_gain_handler)
    app.add_handler(set_rate_lose_slow_handler)
    app.add_handler(set_rate_lose_medium_handler)
    app.add_handler(set_rate_lose_fast_handler)
    app.add_handler(set_rate_gain_slow_handler)
    app.add_handler(set_rate_gain_medium_handler)
    app.add_handler(set_rate_gain_fast_handler)

    # 5. Обработчики графиков
    app.add_handler(CallbackQueryHandler(show_weekly_chart, pattern="chart_week"))
    app.add_handler(CallbackQueryHandler(show_monthly_chart, pattern="chart_month"))
    app.add_handler(CallbackQueryHandler(show_goal_chart, pattern="goal_chart"))
    app.add_handler(CallbackQueryHandler(show_current_progress, pattern="current_progress"))
    
    # 6. Остальные обработчики
    app.add_handler(confirm_handler)
    app.add_handler(retry_handler)
    app.add_handler(last_7_days_handler)
    app.add_handler(clear_today_handler)
    app.add_handler(voice_message_handler)

    # 7. Обработчики текста (В САМОМ КОНЦЕ!)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_text_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_handler))

    # 8. Обработчик ошибок
    app.add_error_handler(error_handler)

    logger.info("Handlers registered, bot running...")
    app.run_polling()
if __name__ == "__main__":
    main()
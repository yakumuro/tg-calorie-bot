import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from bot.database import add_user, get_user
from bot.utils import calculate_daily_calories

logger = logging.getLogger(__name__)

# Состояния диалога
NAME, WEIGHT, HEIGHT, AGE, GENDER, ACTIVITY = range(6)

# Метки активности
ACTIVITY_LABELS = {
    'none': 'Нет активности (сидячий образ)',
    'low': 'Минимальная активность',
    'medium': 'Средняя активность',
    'high': 'Высокая активность'
}


async def start(update, context):
    """Начинает процесс регистрации."""
    context.user_data.clear()  # Очищаем старые данные
    user_id = update.effective_user.id

    logger.info(f"Пользователь {user_id} начал /start")

    try:
        user = get_user(user_id)
        if user:
            await update.message.reply_text("Ты уже зарегистрирован! Напиши /profile, чтобы посмотреть данные.")
            return ConversationHandler.END

        await update.message.reply_text(
            "Привет! Я бот для подсчёта калорий. Давай зарегистрируем тебя!\n\n"
            "Как тебя зовут?"
        )
        return NAME
    except Exception as e:
        logger.error(f"Ошибка в start: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуй позже.")
        return ConversationHandler.END


async def name_handler(update, context):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Введи свой вес (в кг, например, 70.5):")
    return WEIGHT


async def weight_handler(update, context):
    try:
        weight = float(update.message.text)
        if not (20 <= weight <= 300):
            raise ValueError("Вес вне разумных пределов")
        context.user_data['weight'] = weight
        await update.message.reply_text("Введи свой рост (в см, например, 175):")
        return HEIGHT
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи корректный вес (например, 70.5):")
        return WEIGHT


async def height_handler(update, context):
    try:
        height = int(update.message.text)
        if not (100 <= height <= 250):
            raise ValueError("Рост вне разумных пределов")
        context.user_data['height'] = height
        await update.message.reply_text("Введи свой возраст (12–120):")
        return AGE
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи рост числом (например, 175):")
        return HEIGHT


async def age_handler(update, context):
    try:
        age = int(update.message.text)
        if not (12 <= age <= 120):
            raise ValueError("Возраст вне разумных пределов")
        context.user_data['age'] = age

        keyboard = [
            [InlineKeyboardButton("Мужской", callback_data='male'),
             InlineKeyboardButton("Женский", callback_data='female')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выбери свой пол:", reply_markup=reply_markup)
        return GENDER
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи возраст числом (например, 30):")
        return AGE


async def gender_handler(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['gender'] = query.data

    keyboard = [
        [InlineKeyboardButton("Нет активности", callback_data='none'),
         InlineKeyboardButton("Минимальная", callback_data='low')],
        [InlineKeyboardButton("Средняя", callback_data='medium'),
         InlineKeyboardButton("Высокая", callback_data='high')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выбери уровень активности:", reply_markup=reply_markup)
    return ACTIVITY


async def activity_handler(update, context):
    query = update.callback_query
    await query.answer()
    activity_code = query.data
    context.user_data['activity_level'] = activity_code

    user_id = update.effective_user.id
    name = context.user_data['name']
    weight = context.user_data['weight']
    height = context.user_data['height']
    age = context.user_data['age']
    gender = context.user_data['gender']

    try:
        daily_calories = calculate_daily_calories(weight, height, age, gender, activity_code)
        activity_label = ACTIVITY_LABELS[activity_code]

        add_user(user_id, name, weight, height, age, gender, activity_label, daily_calories)

        await query.message.reply_text(
            f"✅ Регистрация завершена!\n\n"
            f"Имя: {name}\n"
            f"Вес: {weight} кг\n"
            f"Рост: {height} см\n"
            f"Возраст: {age}\n"
            f"Пол: {'Мужской' if gender == 'male' else 'Женский'}\n"
            f"Активность: {activity_label}\n"
            f"Дневная норма калорий: {daily_calories} ккал"
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в activity_handler: {e}")
        await query.message.reply_text("Произошла ошибка. Попробуй начать с /start.")
        return ConversationHandler.END


async def cancel(update, context):
    await update.message.reply_text("Регистрация отменена. Напиши /start, чтобы начать заново.")
    return ConversationHandler.END


async def profile(update, context):
    """Показывает профиль пользователя."""
    user_id = update.effective_user.id
    try:
        user = get_user(user_id)
        if not user:
            await update.message.reply_text("Ты не зарегистрирован! Напиши /start, чтобы зарегистрироваться.")
            return

        _, name, weight, height, age, gender, activity_level, daily_calories = user
        await update.message.reply_text(
            f"👤 Твой профиль:\n\n"
            f"Имя: {name}\n"
            f"Вес: {weight} кг\n"
            f"Рост: {height} см\n"
            f"Возраст: {age}\n"
            f"Пол: {'Мужской' if gender == 'male' else 'Женский'}\n"
            f"Активность: {activity_level}\n"
            f"Дневная норма калорий: {daily_calories} ккал"
        )
    except Exception as e:
        logger.error(f"Ошибка в profile: {e}")
        await update.message.reply_text("Произошла ошибка при получении данных. Попробуй позже.")


# Обработчик команды /profile
profile_handler = CommandHandler('profile', profile)

# Настройка ConversationHandler
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_handler)],
        WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, weight_handler)],
        HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, height_handler)],
        AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age_handler)],
        GENDER: [CallbackQueryHandler(gender_handler)],
        ACTIVITY: [CallbackQueryHandler(activity_handler)]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_chat=True,
    per_user=True
)
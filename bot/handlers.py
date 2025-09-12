from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
from bot.database import add_user, get_user, add_meal, get_stats, get_meals_last_7_days
from bot.utils import calculate_daily_calories, get_main_menu
from bot.yandex_gpt import analyze_food_with_gpt
from config.config import YANDEX_GPT_API_KEY, YANDEX_GPT_FOLDER_ID
import logging
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)

# --- Состояния ---
NAME, WEIGHT, HEIGHT, AGE, GENDER, ACTIVITY = range(6)
EDIT_NAME, EDIT_WEIGHT, EDIT_HEIGHT, EDIT_AGE, EDIT_GENDER, EDIT_ACTIVITY = range(6, 12)
ADD_MEAL, AWAIT_CONFIRM = range(12, 14)

ACTIVITY_LABELS = {
    'none': 'Нет активности',
    'low': 'Минимальная',
    'medium': 'Средняя',
    'high': 'Высокая'
}


# --- Регистрация ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user_id = update.effective_user.id
    user = get_user(user_id)

    if user:
        await update.message.reply_text("Добро пожаловать!", reply_markup=get_main_menu())
        return ConversationHandler.END

    await update.message.reply_text(
        "Привет! Я помогу посчитать калории.\nКак тебя зовут?",
        reply_markup=None
    )
    return NAME


async def name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Введи свой вес (в кг, например, 70.5):")
    return WEIGHT


async def weight_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        weight = float(update.message.text)
        if weight <= 0: raise ValueError
        context.user_data['weight'] = weight
        await update.message.reply_text("Введи свой рост (в см, например, 175):")
        return HEIGHT
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи вес числом (например, 70.5):")
        return WEIGHT


async def height_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        height = int(update.message.text)
        if height <= 0: raise ValueError
        context.user_data['height'] = height
        await update.message.reply_text("Введи свой возраст:")
        return AGE
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи рост числом (например, 175):")
        return HEIGHT


async def age_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        age = int(update.message.text)
        if age <= 0: raise ValueError
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


async def gender_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['gender'] = query.data

    keyboard = [
        [InlineKeyboardButton("Нет активности", callback_data='none')],
        [InlineKeyboardButton("Минимальная", callback_data='low')],
        [InlineKeyboardButton("Средняя", callback_data='medium')],
        [InlineKeyboardButton("Высокая", callback_data='high')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выбери уровень активности:", reply_markup=reply_markup)
    return ACTIVITY


async def activity_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            f"✅ Готово!\nНорма: {daily_calories} ккал",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(e)
        await query.message.reply_text("Ошибка. Попробуй /start заново.")
        return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.", reply_markup=get_main_menu())
    return ConversationHandler.END


# --- Профиль ---
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("Нет профиля. /start", reply_markup=None)
        return

    _, name, weight, height, age, gender, activity_level, daily_calories = user
    gender_str = "Мужской" if gender == "male" else "Женский"

    keyboard = [[InlineKeyboardButton("✏️ Редактировать", callback_data="edit_profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👤 <b>Профиль</b>:\n\n"
        f"Имя: {name}\nВес: {weight} кг\nРост: {height} см\n"
        f"Возраст: {age}\nПол: {gender_str}\n"
        f"Активность: {activity_level}\n"
        f"Норма: <b>{daily_calories} ккал</b>",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )


# --- Редактирование профиля: начало ---
async def edit_profile_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Введите новое имя:")
    return EDIT_NAME


# --- Редактирование профиля: шаги ---
async def edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Новый вес (в кг):")
    return EDIT_WEIGHT


async def edit_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        weight = float(update.message.text)
        if weight <= 0: raise ValueError
        context.user_data['weight'] = weight
        await update.message.reply_text("Новый рост (в см):")
        return EDIT_HEIGHT
    except ValueError:
        await update.message.reply_text("Введите число (например, 70.5):")
        return EDIT_WEIGHT


async def edit_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        height = int(update.message.text)
        if height <= 0: raise ValueError
        context.user_data['height'] = height
        await update.message.reply_text("Новый возраст:")
        return EDIT_AGE
    except ValueError:
        await update.message.reply_text("Введите число (например, 175):")
        return EDIT_HEIGHT


async def edit_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        age = int(update.message.text)
        if age <= 0: raise ValueError
        context.user_data['age'] = age

        keyboard = [
            [InlineKeyboardButton("Мужской", callback_data="edit_male"),
             InlineKeyboardButton("Женский", callback_data="edit_female")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выберите пол:", reply_markup=reply_markup)
        return EDIT_GENDER
    except ValueError:
        await update.message.reply_text("Введите число:")
        return EDIT_AGE


async def edit_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['gender'] = 'male' if 'male' in query.data else 'female'
    await query.message.reply_text("Выберите уровень активности:")

    keyboard = [
        [InlineKeyboardButton("Нет активности", callback_data="edit_none")],
        [InlineKeyboardButton("Минимальная", callback_data="edit_low")],
        [InlineKeyboardButton("Средняя", callback_data="edit_medium")],
        [InlineKeyboardButton("Высокая", callback_data="edit_high")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Уровень активности:", reply_markup=reply_markup)
    return EDIT_ACTIVITY


async def edit_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    activity_code = query.data.replace("edit_", "")
    context.user_data['activity_level_code'] = activity_code

    weight = context.user_data['weight']
    height = context.user_data['height']
    age = context.user_data['age']
    gender = context.user_data['gender']

    try:
        new_calories = calculate_daily_calories(weight, height, age, gender, activity_code)
        user_id = update.effective_user.id
        name = context.user_data['name']
        activity_label = ACTIVITY_LABELS[activity_code]
        add_user(user_id, name, weight, height, age, gender, activity_label, new_calories)

        await query.message.reply_text(
            f"✅ Профиль обновлён!\nНовая норма: {new_calories} ккал",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка при редактировании: {e}")
        await query.message.reply_text("Ошибка. Попробуй снова.")
        return ConversationHandler.END


# --- Добавление еды ---
async def add_meal_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Опиши, что ты съел:", reply_markup=None)
    return ADD_MEAL


async def handle_food_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    food_text = update.message.text

    if not YANDEX_GPT_API_KEY or not YANDEX_GPT_FOLDER_ID:
        await update.message.reply_text("Ошибка: GPT не настроен.", reply_markup=get_main_menu())
        return ConversationHandler.END

    try:
        await context.bot.send_chat_action(update.effective_chat.id, "typing")
        result = await analyze_food_with_gpt(food_text, YANDEX_GPT_API_KEY, YANDEX_GPT_FOLDER_ID)

        items = result.get("items", [])
        total_calories = result.get("total_calories", 0)

        context.user_data['pending_meal'] = {
            'food_text': food_text,
            'calories': total_calories,
            'items': items
        }

        product_list = "\n".join(
            [f"• {item['product']} — {item['quantity']} — {item['calories']} ккал" for item in items]
        ) if items else "• Не удалось распознать отдельные продукты."

        summary = f"""
<b>Распознано:</b>

{product_list}

<b>Общее количество калорий:</b> {total_calories} ккал

Выбери действие:
        """

        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_meal")],
            [InlineKeyboardButton("🔁 Ввести заново", callback_data="retry_meal")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(summary.strip(), reply_markup=reply_markup, parse_mode="HTML")
        return AWAIT_CONFIRM

    except Exception as e:
        logger.error(f"GPT error: {e}")
        await update.message.reply_text(
            "❌ Не удалось распознать. Попробуй описать подробнее.",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END


async def confirm_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pending = context.user_data.get('pending_meal')
    if not pending:
        await query.message.reply_text("❌ Данные устарели. Попробуй снова.")
        return ConversationHandler.END

    food_text = pending['food_text']
    calories = pending['calories']

    add_meal(update.effective_user.id, food_text, calories)

    await query.message.reply_text(
        f"✅ Приём пищи сохранён!\nДобавлено: <b>{calories} ккал</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END


async def retry_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Опиши, что ты съел:")
    return ADD_MEAL


async def cancel_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Добавление отменено.", reply_markup=get_main_menu())
    return ConversationHandler.END


# --- Статистика ---
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    daily_norm = user[7] if user else 0
    stats_data = get_stats(user_id)

    keyboard = [[InlineKeyboardButton("📅 Меню за 7 дней", callback_data="last_7_days")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📊 <b>Статистика</b>:\n\n"
        f"Сегодня: {stats_data['day']} / {daily_norm} ккал\n"
        f"Неделя: {stats_data['week']} ккал\n"
        f"Месяц: {stats_data['month']} ккал",
        parse_mode="HTML",
        reply_markup=reply_markup
    )


async def show_last_7_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    meals = get_meals_last_7_days(user_id)

    if not meals:
        await query.message.reply_text("За последние 7 дней приёмы пищи не добавлены.", reply_markup=get_main_menu())
        return

    daily_meals = defaultdict(list)
    total_per_day = defaultdict(float)

    for meal in meals:
        date_str = meal['timestamp'].split()[0]
        date_friendly = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m")
        daily_meals[date_friendly].append(f"• {meal['food_text']} — {meal['calories']} ккал")
        total_per_day[date_friendly] += meal['calories']

    message = "📅 <b>Меню за последние 7 дней</b>:\n\n"
    for date, items in daily_meals.items():
        total = total_per_day[date]
        message += f"<u><b>{date}</b> (всего: {total} ккал)</u>\n"
        message += "\n".join(items)
        message += "\n\n"

    await query.message.reply_text(message, parse_mode="HTML", reply_markup=get_main_menu())


# --- Обработчики ---
profile_handler = MessageHandler(filters.Regex("^👤 Профиль$"), profile)
stats_handler = MessageHandler(filters.Regex("^📊 Статистика$"), stats)

meal_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^📝 Добавить приём пищи$"), add_meal_start)],
    states={
        ADD_MEAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_food_input)],
        AWAIT_CONFIRM: [
            CallbackQueryHandler(confirm_meal, pattern="^confirm_meal$"),
            CallbackQueryHandler(retry_meal, pattern="^retry_meal$")
        ]
    },
    fallbacks=[CommandHandler('cancel', cancel_meal)],
    per_user=True
)

edit_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(edit_profile_start, pattern="edit_profile")],
    states={
        EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_name)],
        EDIT_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_weight)],
        EDIT_HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_height)],
        EDIT_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_age)],
        EDIT_GENDER: [CallbackQueryHandler(edit_gender)],
        EDIT_ACTIVITY: [CallbackQueryHandler(edit_activity)]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_user=True
)

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
    per_user=True
)

# Отдельные обработчики
confirm_handler = CallbackQueryHandler(confirm_meal, pattern="^confirm_meal$")
retry_handler = CallbackQueryHandler(retry_meal, pattern="^retry_meal$")
last_7_days_handler = CallbackQueryHandler(show_last_7_days, pattern="^last_7_days$")
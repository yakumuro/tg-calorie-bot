from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
from bot.database import add_user, get_user, add_meal, get_stats, get_meals_last_7_days
from bot.utils import calculate_daily_calories, get_main_menu
from bot.database import calculate_macros
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

        protein_norm, fat_norm, carbs_norm = calculate_macros(weight, daily_calories)

        add_user(user_id, name, weight, height, age, gender, activity_label, daily_calories)

        await query.message.reply_text(
            f"✅ Готово!\n\n"
            f"🎯 Твоя ежедневная норма:\n"
            f"<b>{daily_calories} ккал</b>\n"
            f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
            parse_mode="HTML",
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

    (_, name, weight, height, age, gender, activity_level,
     daily_calories, protein_norm, fat_norm, carbs_norm) = user

    gender_str = "Мужской" if gender == "male" else "Женский"

    keyboard = [[InlineKeyboardButton("✏️ Редактировать", callback_data="edit_profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👤 <b>Профиль</b>:\n\n"
        f"<b>Имя</b>: {name}\n<b>Вес</b>: {weight} кг\n<b>Рост</b>: {height} см\n"
        f"<b>Возраст</b>: {age}\n<b>Пол</b>: {gender_str}\n"
        f"<b>Активность</b>: {activity_level}\n\n"
        f"<b>🎯 Норма</b>: {daily_calories} ккал\n"
        f"<b>🥩Б</b>: {protein_norm} г, <b>🥑Ж</b>: {fat_norm} г, <b>🍞У</b>: {carbs_norm} г",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )


# --- Редактирование профиля: начало ---
async def edit_profile_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("👤 Имя", callback_data="edit_field_name"),
         InlineKeyboardButton("⚖️ Вес", callback_data="edit_field_weight")],
        [InlineKeyboardButton("📏 Рост", callback_data="edit_field_height"),
         InlineKeyboardButton("🎂 Возраст", callback_data="edit_field_age")],
        [InlineKeyboardButton("🚻 Пол", callback_data="edit_field_gender"),
         InlineKeyboardButton("🏃 Активность", callback_data="edit_field_activity")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text("Что хочешь изменить?", reply_markup=reply_markup)
    return "FIELD"


# --- Редактирование профиля: шаги ---
async def edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user:
        await update.message.reply_text("Ошибка: профиль не найден.")
        return ConversationHandler.END

    (_, _, weight, height, age, gender, activity_level,
     daily_calories, protein_norm, fat_norm, carbs_norm) = user

    add_user(user_id, new_name, weight, height, age, gender, activity_level, daily_calories)

    await update.message.reply_text("✅Имя обновлено!", reply_markup=get_main_menu())
    return ConversationHandler.END


async def edit_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        weight = float(update.message.text)
        if weight <= 0: raise ValueError

        user_id = update.effective_user.id
        user = get_user(user_id)
        if not user:
            await update.message.reply_text("Ошибка: профиль не найден.")
            return ConversationHandler.END

        (_, name, _, height, age, gender, activity_level,
         _, _, _, _) = user

        # пересчёт
        activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == activity_level][0]
        new_calories = calculate_daily_calories(weight, height, age, gender, activity_code)
        protein_norm, fat_norm, carbs_norm = calculate_macros(weight, new_calories)

        add_user(user_id, name, weight, height, age, gender, activity_level, new_calories)

        await update.message.reply_text(
            f"✅ Вес обновлён!\nНовая норма: {new_calories} ккал\n"
            f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
            parse_mode="HTML",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Введите число (например, 70.5):")
        return EDIT_WEIGHT


async def edit_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        height = int(update.message.text)
        if height <= 0: raise ValueError

        user_id = update.effective_user.id
        user = get_user(user_id)
        if not user:
            await update.message.reply_text("Ошибка: профиль не найден.")
            return ConversationHandler.END

        (_, name, weight, _, age, gender, activity_level,
         _, _, _, _) = user

        activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == activity_level][0]
        new_calories = calculate_daily_calories(weight, height, age, gender, activity_code)
        protein_norm, fat_norm, carbs_norm = calculate_macros(weight, new_calories)

        add_user(user_id, name, weight, height, age, gender, activity_level, new_calories)

        await update.message.reply_text(
            f"✅ Рост обновлён!\nНовая норма: {new_calories} ккал\n"
            f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
            parse_mode="HTML",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Введите число (например, 175):")
        return EDIT_HEIGHT


async def edit_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        age = int(update.message.text)
        if age <= 0: raise ValueError

        user_id = update.effective_user.id
        user = get_user(user_id)
        if not user:
            await update.message.reply_text("Ошибка: профиль не найден.")
            return ConversationHandler.END

        (_, name, weight, height, _, gender, activity_level,
         _, _, _, _) = user

        activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == activity_level][0]
        new_calories = calculate_daily_calories(weight, height, age, gender, activity_code)
        protein_norm, fat_norm, carbs_norm = calculate_macros(weight, new_calories)

        add_user(user_id, name, weight, height, age, gender, activity_level, new_calories)

        await update.message.reply_text(
            f"✅ Возраст обновлён!\nНовая норма: {new_calories} ккал\n"
            f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
            parse_mode="HTML",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Введите число (например, 25):")
        return EDIT_AGE


async def edit_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gender = "male" if query.data == "edit_gender_male" else "female"

    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await query.message.reply_text("Ошибка: профиль не найден.")
        return ConversationHandler.END

    (_, name, weight, height, age, _, activity_level,
     _, _, _, _) = user

    activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == activity_level][0]
    new_calories = calculate_daily_calories(weight, height, age, gender, activity_code)
    protein_norm, fat_norm, carbs_norm = calculate_macros(weight, new_calories)

    add_user(user_id, name, weight, height, age, gender, activity_level, new_calories)

    await query.message.reply_text(
        f"✅ Пол обновлён!\nНовая норма: {new_calories} ккал\n"
        f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END


async def edit_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    activity_code = query.data.replace("edit_act_", "")
    activity_label = ACTIVITY_LABELS[activity_code]

    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await query.message.reply_text("Ошибка: профиль не найден.")
        return ConversationHandler.END

    (_, name, weight, height, age, gender, _, _, _, _, _) = user

    new_calories = calculate_daily_calories(weight, height, age, gender, activity_code)
    protein_norm, fat_norm, carbs_norm = calculate_macros(weight, new_calories)

    add_user(user_id, name, weight, height, age, gender, activity_label, new_calories)

    await query.message.reply_text(
        f"✅ Активность обновлена!\nНовая норма: {new_calories} ккал\n"
        f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END


# --- Добавление еды ---
async def add_meal_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Подробно опишите, что съели. Пишите максимально подробно, указывая вес порций и ингредиенты:", reply_markup=None)
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
        totals = result.get("total", {"calories": 0, "protein": 0, "fat": 0, "carbs": 0})

        context.user_data['pending_meal'] = {
            'food_text': food_text,
            'calories': totals["calories"],
            'protein': totals["protein"],
            'fat': totals["fat"],
            'carbs': totals["carbs"],
            'items': items
        }

        product_list = "\n".join(
        [f"• {i['product']} — {i['quantity']} — {i['calories']} ккал, Б: {i['protein']} г, Ж: {i['fat']} г, У: {i['carbs']} г" for i in items]
        )

        summary = f"""
<b>Распознано:</b>

{product_list}

<b>🍽 Итого:</b> {totals['calories']} ккал  
🥩Б: {totals['protein']} г, 🥑Ж: {totals['fat']} г, 🍞У: {totals['carbs']} г

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

    add_meal(
        update.effective_user.id,
        pending['food_text'],
        pending['calories'],
        pending['protein'],
        pending['fat'],
        pending['carbs']
    )

    await query.message.reply_text(
        f"✅ Приём пищи сохранён!\n"
        f"🍽 Добавлено: {pending['calories']} ккал\n"
        f"🥩Б: {pending['protein']} г, 🥑Ж: {pending['fat']} г, 🍞У: {pending['carbs']} г",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END


async def retry_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Подробно опишите, что съели. Пишите максимально подробно, указывая вес порций и ингредиенты:")
    return ADD_MEAL


async def cancel_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Добавление отменено.", reply_markup=get_main_menu())
    return ConversationHandler.END


# --- Статистика ---
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    daily_norm = user["daily_calories"]
    protein_norm = user["protein_norm"]
    fat_norm = user["fat_norm"]
    carbs_norm = user["carbs_norm"]
    stats_data = get_stats(user_id)

    keyboard = [[InlineKeyboardButton("📅 Меню за 7 дней", callback_data="last_7_days")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📊 <b>Статистика</b>:\n\n"
        f"<b>Сегодня</b>:\n\n 🍽Калорий: {stats_data['day']['calories']} / {daily_norm} ккал\n"
        f"🥩Белков: {stats_data['day']['protein']} / {protein_norm} г\n🥑Жиров: {stats_data['day']['fat']} / {fat_norm} г\n🍞Углеводов: {stats_data['day']['carbs']} / {carbs_norm} г\n\n"
        f"<b>📅Неделя</b>: {stats_data['week']['calories']} ккал (Б: {stats_data['week']['protein']} г, Ж: {stats_data['week']['fat']} г, У: {stats_data['week']['carbs']} г)\n"
        f"<b>📅Месяц</b>: {stats_data['month']['calories']} ккал (Б: {stats_data['month']['protein']} г, Ж: {stats_data['month']['fat']} г, У: {stats_data['month']['carbs']} г)",
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
        daily_meals[date_friendly].append(f"▪️ {meal['food_text']} — {meal['calories']} ккал")
        total_per_day[date_friendly] += meal['calories']

    message = "🗓 <b>Меню за последние 7 дней</b>:\n\n"
    for date, items in daily_meals.items():
        total = total_per_day[date]
        message += f"📌<u><b>{date}</b> (всего: {total} ккал)</u>\n"
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

async def edit_field_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field = query.data.replace("edit_field_", "")
    context.user_data['edit_field'] = field

    if field == "name":
        await query.message.reply_text("Введите новое имя:")
        return EDIT_NAME
    elif field == "weight":
        await query.message.reply_text("Введите новый вес (кг):")
        return EDIT_WEIGHT
    elif field == "height":
        await query.message.reply_text("Введите новый рост (см):")
        return EDIT_HEIGHT
    elif field == "age":
        await query.message.reply_text("Введите новый возраст:")
        return EDIT_AGE
    elif field == "gender":
        keyboard = [
            [InlineKeyboardButton("Мужской", callback_data="edit_gender_male"),
             InlineKeyboardButton("Женский", callback_data="edit_gender_female")]
        ]
        await query.message.reply_text("Выберите пол:", reply_markup=InlineKeyboardMarkup(keyboard))
        return EDIT_GENDER
    elif field == "activity":
        keyboard = [
            [InlineKeyboardButton("Нет активности", callback_data="edit_act_none")],
            [InlineKeyboardButton("Минимальная", callback_data="edit_act_low")],
            [InlineKeyboardButton("Средняя", callback_data="edit_act_medium")],
            [InlineKeyboardButton("Высокая", callback_data="edit_act_high")]
        ]
        await query.message.reply_text("Выберите уровень активности:", reply_markup=InlineKeyboardMarkup(keyboard))
        return EDIT_ACTIVITY

edit_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(edit_profile_start, pattern="edit_profile")],
    states={
        # обработка выбора поля
        "FIELD": [CallbackQueryHandler(edit_field_handler, pattern="^edit_field_")],

        # ввод новых значений
        EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_name)],
        EDIT_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_weight)],
        EDIT_HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_height)],
        EDIT_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_age)],
        EDIT_GENDER: [CallbackQueryHandler(edit_gender, pattern="^edit_gender_")],
        EDIT_ACTIVITY: [CallbackQueryHandler(edit_activity, pattern="^edit_act_")],
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
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
from bot.database import add_user, get_user, add_meal, get_stats, get_meals_last_7_days
from bot.utils import calculate_daily_calories, get_main_menu, render_progress_bar
from bot.database import calculate_macros, delete_meals_for_day
from bot.yandex_gpt import analyze_food_with_gpt
from config.config import YANDEX_GPT_API_KEY, YANDEX_GPT_FOLDER_ID
import logging
from datetime import datetime, date
from collections import defaultdict

logger = logging.getLogger(__name__)

# --- Состояния ---
# Регистрация
NAME, WEIGHT, HEIGHT, AGE, GENDER, ACTIVITY, GOAL, TARGET_WEIGHT, GOAL_RATE = range(9)

# Редактирование профиля
EDIT_NAME, EDIT_WEIGHT, EDIT_HEIGHT, EDIT_AGE, EDIT_GENDER, EDIT_ACTIVITY = range(9, 15)

EDIT_GOAL, EDIT_TARGET_WEIGHT, EDIT_GOAL_RATE = range(17, 20)

# Добавление еды
ADD_MEAL, AWAIT_CONFIRM = range(15, 17)

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

    tutorial_text = (
        "Добро пожаловать! 👋\n\n"
        "Я помогу тебе отслеживать питание и подсчитывать калории.\n\n"
        "👤 Введи свои данные, и я рассчитую твою дневную норму калорий.\n"
        "📝 Добавляй приёмы пищи — я подсчитаю калории, белки, жиры и углеводы.\n"
        "📊 Смотри свои показатели, чтобы видеть, как близко ты к своей норме.\n\n"
        "**Что начать, напиши свое имя!**"
    )

    user_text = (
            "Привет! 👋\n\n"
            "Ты уже зарегистрирован, и я знаю твою дневную норму калорий.\n\n"
            "- 📝 Добавляй новые приёмы пищи — я подсчитаю калории и макросы.\n"
            "- 📊 Смотри свои показатели, чтобы контролировать питание.\n"
            "- 👤 Редактируй данные профиля, если что-то изменилось.\n\n"
            "Просто выбери нужное действие в меню ниже."
        )

    if user:
        await update.message.reply_text(user_text, parse_mode="Markdown", reply_markup=get_main_menu())
        return ConversationHandler.END

    await update.message.reply_text(tutorial_text, parse_mode="Markdown", reply_markup=None)
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
    activity_code = query.data  # 'none', 'low', 'medium', 'high'
    context.user_data['activity_code'] = activity_code  # код для вычислений
    context.user_data['activity_level'] = ACTIVITY_LABELS[activity_code]  # метка для профиля

    # Запрашиваем цель (похудеть / набрать / поддерживать)
    keyboard = [
        [InlineKeyboardButton("Похудеть", callback_data='goal_lose'),
         InlineKeyboardButton("Набрать", callback_data='goal_gain')],
        [InlineKeyboardButton("Поддерживать", callback_data='goal_maintain')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выбери цель:", reply_markup=reply_markup)
    return GOAL


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

    name = user["name"]
    weight = user["weight"]
    height = user["height"]
    age = user["age"]
    gender = user["gender"]
    activity_level = user["activity_level"]
    daily_calories = user["daily_calories"] or 0
    protein_norm = user["protein_norm"] or 0
    fat_norm = user["fat_norm"] or 0
    carbs_norm = user["carbs_norm"] or 0
    goal_type = user.get("goal_type", "maintain")
    target_weight = user.get("target_weight")
    goal_rate = user.get("goal_rate")

    gender_str = "Мужской" if gender == "male" else "Женский"

    keyboard = [[InlineKeyboardButton("✏️ Редактировать", callback_data="edit_profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    extra = ""
    if goal_type and goal_type != "maintain":
        extra = f"\n<b>Цель</b>: {'Похудеть' if goal_type=='lose' else 'Набрать'}\n"
        extra += f"<b>Целевой вес</b>: {target_weight} кг\n<b>Темп</b>: {goal_rate}\n\n"

    await update.message.reply_text(
        f"👤 <b>Профиль</b>:\n\n"
        f"<b>Имя</b>: {name}\n<b>Вес</b>: {weight} кг\n<b>Рост</b>: {height} см\n"
        f"<b>Возраст</b>: {age}\n<b>Пол</b>: {gender_str}\n"
        f"<b>Активность</b>: {activity_level}\n\n"
        f"{extra}"
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
        InlineKeyboardButton("🏃 Активность", callback_data="edit_field_activity")],
        [InlineKeyboardButton("🎯 Цель", callback_data="edit_goal")]
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

    add_user(user_id, new_name, user["weight"], user["height"], user["age"], user["gender"], user["activity_level"], user["daily_calories"],
             goal_type=user.get("goal_type"), target_weight=user.get("target_weight"), goal_rate=user.get("goal_rate"))

    await update.message.reply_text("✅ Имя обновлено!", reply_markup=get_main_menu())
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

        # пересчёт
        activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == user["activity_level"]][0]
        new_calories = calculate_daily_calories(weight, user["height"], user["age"], user["gender"], activity_code)
        protein_norm, fat_norm, carbs_norm = calculate_macros(weight, new_calories)

        add_user(user_id, user["name"], weight, user["height"], user["age"], user["gender"], user["activity_level"], new_calories,
                 goal_type=user.get("goal_type"), target_weight=user.get("target_weight"), goal_rate=user.get("goal_rate"))

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

        activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == user["activity_level"]][0]
        new_calories = calculate_daily_calories(user["weight"], height, user["age"], user["gender"], activity_code)
        protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], new_calories)

        add_user(user_id, user["name"], user["weight"], height, user["age"], user["gender"], user["activity_level"], new_calories,
                 goal_type=user.get("goal_type"), target_weight=user.get("target_weight"), goal_rate=user.get("goal_rate"))

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

        activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == user["activity_level"]][0]
        new_calories = calculate_daily_calories(user["weight"], user["height"], age, user["gender"], activity_code)
        protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], new_calories)

        add_user(user_id, user["name"], user["weight"], user["height"], age, user["gender"], user["activity_level"], new_calories,
                 goal_type=user.get("goal_type"), target_weight=user.get("target_weight"), goal_rate=user.get("goal_rate"))

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

    activity_level = user["activity_level"]
    activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == activity_level][0]
    new_calories = calculate_daily_calories(user["weight"], user["height"], user["age"], gender, activity_code)
    protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], new_calories)

    add_user(user_id, user["name"], user["weight"], user["height"], user["age"], gender, activity_level, new_calories,
             goal_type=user.get("goal_type"), target_weight=user.get("target_weight"), goal_rate=user.get("goal_rate"))

    # Удаляем старое сообщение с меню выбора пола
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение с меню пола: {e}")

    await query.message.chat.send_message(
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

    new_calories = calculate_daily_calories(user["weight"], user["height"], user["age"], user["gender"], activity_code)
    protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], new_calories)

    add_user(user_id, user["name"], user["weight"], user["height"], user["age"], user["gender"], activity_label, new_calories,
             goal_type=user.get("goal_type"), target_weight=user.get("target_weight"), goal_rate=user.get("goal_rate"))

    # Удаляем старое сообщение с меню выбора активности
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение с меню активности: {e}")

    await query.message.chat.send_message(
        f"✅ Активность обновлена!\nНовая норма: {new_calories} ккал\n"
        f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END

async def edit_goal_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("Похудеть", callback_data="edit_goal_lose")],
        [InlineKeyboardButton("Набрать", callback_data="edit_goal_gain")],
        [InlineKeyboardButton("Поддерживать", callback_data="edit_goal_maintain")]
    ]
    await query.message.edit_text("Выбери новую цель:", reply_markup=InlineKeyboardMarkup(keyboard))
    return EDIT_GOAL

async def edit_goal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    goal = query.data.replace("edit_goal_", "")
    context.user_data['edit_goal'] = goal

    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await query.message.edit_text("Ошибка: профиль не найден.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if goal == "maintain":
        activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == user["activity_level"]][0]
        daily_calories = calculate_daily_calories(user["weight"], user["height"], user["age"], user["gender"], activity_code)
        protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], daily_calories)
        add_user(user_id, user["name"], user["weight"], user["height"], user["age"], user["gender"],
                 user["activity_level"], daily_calories, goal_type='maintain', target_weight=None, goal_rate=None)
        
        # Используем send_message вместо edit_text для избежания ошибки
        await query.message.delete()  # Удаляем старое сообщение
        await query.message.chat.send_message(
            f"✅ Цель обновлена на «Поддерживать»!\n"
            f"🎯 Норма: {daily_calories} ккал\n"
            f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
            parse_mode="HTML",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END

    # Если цель похудеть или набрать → редактируем сообщение и просим ввести целевой вес
    await query.message.edit_text("Введите целевой вес (в кг):", reply_markup=None)
    return EDIT_TARGET_WEIGHT

async def edit_target_weight_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        target_weight = float(text)
        if target_weight <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Введите корректный вес числом (например, 70.0):")
        return EDIT_TARGET_WEIGHT

    goal = context.user_data.get('edit_goal')
    current_weight = get_user(update.effective_user.id)["weight"]

    if goal == "lose" and not (target_weight < current_weight):
        await update.message.reply_text("Целевой вес должен быть меньше текущего:")
        return EDIT_TARGET_WEIGHT
    if goal == "gain" and not (target_weight > current_weight):
        await update.message.reply_text("Целевой вес должен быть больше текущего:")
        return EDIT_TARGET_WEIGHT

    context.user_data['edit_target_weight'] = target_weight

    # Предлагаем темп
    if goal == "lose":
        keyboard = [
            [InlineKeyboardButton("Долго и легко — 0.25 кг/нед", callback_data="edit_rate_lose_slow")],
            [InlineKeyboardButton("Сбалансированно — 0.5 кг/нед", callback_data="edit_rate_lose_medium")],
            [InlineKeyboardButton("Быстро — 1.0 кг/нед", callback_data="edit_rate_lose_fast")]
        ]
    else:  # gain
        keyboard = [
            [InlineKeyboardButton("Медленно — 0.25 кг/нед", callback_data="edit_rate_gain_slow")],
            [InlineKeyboardButton("Сбалансированно — 0.5 кг/нед", callback_data="edit_rate_gain_medium")],
            [InlineKeyboardButton("Быстро — 0.75 кг/нед", callback_data="edit_rate_gain_fast")]
        ]

    await update.message.reply_text("Выбери темп достижения цели:", reply_markup=InlineKeyboardMarkup(keyboard))
    return EDIT_GOAL_RATE

async def edit_goal_rate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat = query.message.chat  # сохраняем до удаления

    data = query.data.split("_")
    goal_type, rate_key = data[2], data[3]  # edit_rate_lose_medium → ['edit','rate','lose','medium']

    kg_mapping = {
        "lose": {"slow": 0.25, "medium": 0.5, "fast": 1.0},
        "gain": {"slow": 0.25, "medium": 0.5, "fast": 0.75}
    }

    kg_per_week = kg_mapping[goal_type][rate_key]

    user_id = update.effective_user.id
    user = get_user(user_id)
    activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == user["activity_level"]][0]

    maintenance = calculate_daily_calories(user["weight"], user["height"], user["age"], user["gender"], activity_code)
    daily_adjustment = (kg_per_week * 7700) / 7.0
    daily_calories = round(maintenance - daily_adjustment, 1) if goal_type == "lose" else round(maintenance + daily_adjustment, 1)

    protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], daily_calories)

    # Сохраняем цель
    add_user(user_id, user["name"], user["weight"], user["height"], user["age"], user["gender"],
             user["activity_level"], daily_calories, goal_type=goal_type,
             target_weight=context.user_data.get('edit_target_weight'),
             goal_rate=f"{kg_per_week}кг/нед")

    try:
        await query.message.delete()
    except Exception:
        pass

    await chat.send_message(
        f"✅ Цель обновлена!\n"
        f"🎯 {('Похудеть' if goal_type=='lose' else 'Набрать')} ({kg_per_week} кг/нед)\n"
        f"🎯 Целевой вес: {context.user_data.get('edit_target_weight')} кг\n"
        f"🎯 Норма с учётом цели: {daily_calories} ккал\n"
        f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END



# --- Добавление еды ---
async def add_meal_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Подробно опиши, что съел. Пиши максимально подробно, указывая вес порций и ингредиенты:", reply_markup=None)
    return ADD_MEAL


async def handle_food_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    food_text = update.message.text

    # 🕒 Сообщение "обрабатываем"
    processing_msg = await update.message.reply_text("⏳ Обрабатываем ваш запрос...")

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

        # Удаляем сообщение "обрабатываем"
        try:
            await processing_msg.delete()
        except Exception:
            pass

        # Формируем текст с продуктами и прогрессом
        user_id = update.effective_user.id
        stats_data = get_stats(user_id)
        daily_norm = get_user(user_id)["daily_calories"]
        already_eaten = stats_data['day']['calories'] or 0
        projected = already_eaten + totals['calories'] or 0

        progress_after = render_progress_bar(projected, daily_norm)

        product_list = "\n".join(
            [f"• {i['product']} — {i['quantity']} — {i['calories']} ккал, "
             f"Б: {i['protein']} г, Ж: {i['fat']} г, У: {i['carbs']} г" for i in items]
        )

        summary = f"""
<b>Распознано:</b>

{product_list}

<b>🍽 Итого:</b> {totals['calories']} ккал  
🥩Б: {totals['protein']} г, 🥑Ж: {totals['fat']} г, 🍞У: {totals['carbs']} г

<b>📊 Норма после добавления:</b>
{progress_after}

Выбери действие:
        """

        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_meal")],
            [InlineKeyboardButton("🔁 Ввести заново", callback_data="retry_meal")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Отправляем сообщение с кнопками и сохраняем message_id
        msg = await update.message.reply_text(summary.strip(), reply_markup=reply_markup, parse_mode="HTML")
        context.user_data['last_meal_message_id'] = msg.message_id

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

    # Удаляем сообщение с текстом еды + кнопками
    last_message_id = context.user_data.get('last_meal_message_id')
    if last_message_id:
        try:
            await query.message.chat.delete_message(last_message_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить старое сообщение с едой: {e}")
        context.user_data.pop('last_meal_message_id', None)

    # Отправляем подтверждение
    await query.message.chat.send_message(
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

    # Удаляем старое сообщение с текстом еды + кнопками
    last_message_id = context.user_data.get('last_meal_message_id')
    if last_message_id:
        try:
            await query.message.chat.delete_message(last_message_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить старое сообщение с едой: {e}")
        context.user_data.pop('last_meal_message_id', None)

    # Просим пользователя ввести еду заново
    await query.message.chat.send_message(
        "Подробно опишите, что съели. Пишите максимально подробно, указывая вес порций и ингредиенты:"
    )
    return ADD_MEAL



async def cancel_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Добавление отменено.", reply_markup=get_main_menu())
    return ConversationHandler.END


# --- Статистика ---
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user:
        await update.message.reply_text("Нет профиля. /start", reply_markup=None)
        return

    # Получаем норму из профиля
    daily_norm = user["daily_calories"] or 0
    protein_norm = user["protein_norm"] or 0
    fat_norm = user["fat_norm"] or 0
    carbs_norm = user["carbs_norm"] or 0

    stats_data = get_stats(user_id)

    progress_today = render_progress_bar(stats_data['day']['calories'], daily_norm)

    # Если статистика ещё пустая, подставляем 0
    day_stats = stats_data.get('day', {})
    week_stats = stats_data.get('week', {})
    month_stats = stats_data.get('month', {})

    day_calories = day_stats.get('calories') or 0
    day_protein = day_stats.get('protein') or 0
    day_fat = day_stats.get('fat') or 0
    day_carbs = day_stats.get('carbs') or 0

    week_calories = week_stats.get('calories') or 0
    week_protein = week_stats.get('protein') or 0
    week_fat = week_stats.get('fat') or 0
    week_carbs = week_stats.get('carbs') or 0

    month_calories = month_stats.get('calories') or 0
    month_protein = month_stats.get('protein') or 0
    month_fat = month_stats.get('fat') or 0
    month_carbs = month_stats.get('carbs') or 0

    keyboard = [
    [InlineKeyboardButton("📅 Меню за 7 дней", callback_data="last_7_days")],
    [InlineKeyboardButton("🗑 Удалить данные за сегодня", callback_data="clear_today")]
]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📊 <b>Статистика</b>:\n\n"
        f"<b>Сегодня</b>:\n\n"
        f"Каллорий: {progress_today}\n\n"
        f"🥩Белков: {day_protein} / {protein_norm} г\n"
        f"🥑Жиров: {day_fat} / {fat_norm} г\n"
        f"🍞Углеводов: {day_carbs} / {carbs_norm} г\n\n"
        f"<b>📅Неделя</b>: {week_calories} ккал (Б: {week_protein} г, Ж: {week_fat} г, У: {week_carbs} г)\n"
        f"<b>📅Месяц</b>: {month_calories} ккал (Б: {month_protein} г, Ж: {month_fat} г, У: {month_carbs} г)",
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

async def clear_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    # Удаляем приёмы пищи за сегодня
    deleted = delete_meals_for_day(user_id)

    if deleted:
        await query.message.reply_text(f"✅ История еды за сегодня удалена.", reply_markup=get_main_menu())
    else:
        await query.message.reply_text(f"ℹ️ За сегодня нет добавленных приёмов пищи.", reply_markup=get_main_menu())

async def fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Если пользователь написал что-то не через кнопку
    await update.message.reply_text(
        "Пожалуйста, выберите действие через кнопки ниже, прежде чем отправлять текст."
    )

async def goal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    goal = query.data.replace("goal_", "")  # 'lose' | 'gain' | 'maintain'
    context.user_data['goal'] = goal

    user_id = update.effective_user.id
    name = context.user_data.get('name')
    weight = context.user_data.get('weight')
    height = context.user_data.get('height')
    age = context.user_data.get('age')
    gender = context.user_data.get('gender')
    activity_code = context.user_data.get('activity_code')
    activity_label = ACTIVITY_LABELS.get(activity_code, activity_code)

    # Если цель - поддерживать — завершаем регистрацию сразу (как раньше), с вычислением нормы
    if goal == "maintain":
        try:
            daily_calories = calculate_daily_calories(weight, height, age, gender, activity_code)
            protein_norm, fat_norm, carbs_norm = calculate_macros(weight, daily_calories)
            add_user(user_id, name, weight, height, age, gender, activity_label, daily_calories,
                     goal_type='maintain', target_weight=None, goal_rate=None)

            await query.message.reply_text(
                f"✅ Готово!\n\n"
                f"🎯 Твоя ежедневная норма (поддержание):\n"
                f"<b>{daily_calories} ккал</b>\n"
                f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
                parse_mode="HTML",
                reply_markup=get_main_menu()
            )
            return ConversationHandler.END
        except Exception as e:
            logger.error(e)
            await query.message.reply_text("Ошибка при расчёте. Попробуй /start заново.")
            return ConversationHandler.END

    # Если цель похудеть или набрать — запрашиваем целевой вес
    await query.message.reply_text("Введите целевой вес (в кг, например 70.0):", reply_markup=None)
    return TARGET_WEIGHT

async def target_weight_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    try:
        target = float(text)
        if target <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи корректный вес числом (например, 70.0):")
        return TARGET_WEIGHT

    # Валидация в зависимости от цели
    goal = context.user_data.get('goal')
    current_weight = context.user_data.get('weight')
    if goal == "lose" and not (target < current_weight):
        await update.message.reply_text("Целевой вес должен быть меньше текущего. Введите корректный целевой вес:")
        return TARGET_WEIGHT
    if goal == "gain" and not (target > current_weight):
        await update.message.reply_text("Целевой вес должен быть больше текущего. Введите корректный целевой вес:")
        return TARGET_WEIGHT

    context.user_data['target_weight'] = target

    # Предлагаем варианты скорости (с примерной кг/нед)
    if goal == "lose":
        keyboard = [
            [InlineKeyboardButton("Долго и легко — 0.25 кг/нед", callback_data="rate_lose_slow")],
            [InlineKeyboardButton("Сбалансированно — 0.5 кг/нед", callback_data="rate_lose_medium")],
            [InlineKeyboardButton("Быстро (сложно) — 1.0 кг/нед", callback_data="rate_lose_fast")]
        ]
    else:  # gain
        keyboard = [
            [InlineKeyboardButton("Медленно — 0.25 кг/нед", callback_data="rate_gain_slow")],
            [InlineKeyboardButton("Сбалансированно — 0.5 кг/нед", callback_data="rate_gain_medium")],
            [InlineKeyboardButton("Быстро — 0.75 кг/нед", callback_data="rate_gain_fast")]
        ]

    await update.message.reply_text("Выбери темп достижения цели (примерная скорость):", reply_markup=InlineKeyboardMarkup(keyboard))
    return GOAL_RATE

async def goal_rate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # e.g. rate_lose_medium
    parts = data.split("_")
    # parts[1] == 'lose'|'gain', parts[2] == 'slow'|'medium'|'fast'
    if len(parts) < 3:
        await query.message.reply_text("Неверный выбор. Повтори ещё раз.", reply_markup=get_main_menu())
        return ConversationHandler.END

    goal_type = parts[1]
    rate_key = parts[2]

    # kg/week mapping
    mapping = {
        "lose": {"slow": 0.25, "medium": 0.5, "fast": 1.0},
        "gain": {"slow": 0.25, "medium": 0.5, "fast": 0.75}
    }
    kg_per_week = mapping.get(goal_type, {}).get(rate_key, 0.5)
    rate_label = f"{rate_key}"

    # Получаем данные из контекста
    name = context.user_data.get('name')
    weight = context.user_data.get('weight')
    height = context.user_data.get('height')
    age = context.user_data.get('age')
    gender = context.user_data.get('gender')
    activity_code = context.user_data.get('activity_code')
    activity_label = context.user_data.get('activity_level')
    target_weight = context.user_data.get('target_weight')

    if None in (name, weight, height, age, gender, activity_code):
        await query.message.reply_text("Некорректные данные профиля. Заполни профиль заново /start", reply_markup=get_main_menu())
        return ConversationHandler.END

    # Рассчитываем базовое поддержание и корректируем по цели
    maintenance = calculate_daily_calories(weight, height, age, gender, activity_code)
    daily_adjustment = (kg_per_week * 7700) / 7.0  # 7700 ккал ~ 1 кг
    if goal_type == "lose":
        daily_calories = round(maintenance - daily_adjustment, 1)
    else:  # gain
        daily_calories = round(maintenance + daily_adjustment, 1)

    # Минимум ккал (защита) — можно настроить
    min_cal = 1200 if gender == "female" else 1500
    if daily_calories < min_cal:
        await query.message.reply_text(
            f"Выбранный темп даёт слишком низкую норму ({daily_calories} ккал). Выберите более щадящий темп."
        )
        return GOAL_RATE

    # Факторы для БЖУ в зависимости от цели (упрощённо)
    if goal_type == "lose":
        protein_factor = 2.0  # чуть больше белка при дефиците
        fat_factor = 1.0
    elif goal_type == "gain":
        protein_factor = 1.6
        fat_factor = 1.0
    else:
        protein_factor = 1.8
        fat_factor = 1.0

    protein_norm, fat_norm, carbs_norm = calculate_macros(weight, daily_calories, protein_factor=protein_factor, fat_factor=fat_factor)

    # Сохраняем пользователя с новыми полями goal
    user_id = update.effective_user.id
    add_user(user_id, name, weight, height, age, gender, activity_label, daily_calories,
             goal_type=goal_type, target_weight=target_weight, goal_rate=f"{kg_per_week}кг/нед")

    await query.message.reply_text(
        f"✅ Профиль создан!\n\n"
        f"🎯 Цель: {'Похудеть' if goal_type=='lose' else 'Набрать'} ({kg_per_week} кг/нед)\n"
        f"🎯 Целевой вес: {target_weight} кг\n\n"
        f"🎯 Норма с учётом цели: <b>{daily_calories} ккал</b>\n"
        f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END




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

    # Удаляем старое сообщение с меню выбора поля
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить старое сообщение с меню редактирования: {e}")

    try:
        if field == "name":
            await query.message.chat.send_message("Введите новое имя:")
            return EDIT_NAME
        elif field == "weight":
            await query.message.chat.send_message("Введите новый вес (кг):")
            return EDIT_WEIGHT
        elif field == "height":
            await query.message.chat.send_message("Введите новый рост (см):")
            return EDIT_HEIGHT
        elif field == "age":
            await query.message.chat.send_message("Введите новый возраст:")
            return EDIT_AGE
        elif field == "gender":
            keyboard = [
                [InlineKeyboardButton("Мужской", callback_data="edit_gender_male"),
                 InlineKeyboardButton("Женский", callback_data="edit_gender_female")]
            ]
            await query.message.chat.send_message("Выберите пол:", reply_markup=InlineKeyboardMarkup(keyboard))
            return EDIT_GENDER
        elif field == "activity":
            keyboard = [
                [InlineKeyboardButton("Нет активности", callback_data="edit_act_none")],
                [InlineKeyboardButton("Минимальная", callback_data="edit_act_low")],
                [InlineKeyboardButton("Средняя", callback_data="edit_act_medium")],
                [InlineKeyboardButton("Высокая", callback_data="edit_act_high")]
            ]
            await query.message.chat.send_message("Выберите уровень активности:", reply_markup=InlineKeyboardMarkup(keyboard))
            return EDIT_ACTIVITY
        elif field == "goal":
            # Переходим к редактированию цели
            keyboard = [
                [InlineKeyboardButton("Похудеть", callback_data="edit_goal_lose")],
                [InlineKeyboardButton("Набрать", callback_data="edit_goal_gain")],
                [InlineKeyboardButton("Поддерживать", callback_data="edit_goal_maintain")]
            ]
            await query.message.chat.send_message("Выбери новую цель:", reply_markup=InlineKeyboardMarkup(keyboard))
            return EDIT_GOAL
    except Exception as e:
        logger.error(f"Ошибка в edit_field_handler: {e}")
        await query.message.chat.send_message("Произошла ошибка. Попробуйте снова.", reply_markup=get_main_menu())
        return ConversationHandler.END


edit_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(edit_profile_start, pattern="edit_profile")],
    states={
        "FIELD": [
            CallbackQueryHandler(edit_field_handler, pattern="^edit_field_"),
            CallbackQueryHandler(edit_goal_start, pattern="edit_goal")  # Добавляем эту строку
        ],
        EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_name)],
        EDIT_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_weight)],
        EDIT_HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_height)],
        EDIT_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_age)],
        EDIT_GENDER: [CallbackQueryHandler(edit_gender, pattern="^edit_gender_")],
        EDIT_ACTIVITY: [CallbackQueryHandler(edit_activity, pattern="^edit_act_")],
        EDIT_GOAL: [CallbackQueryHandler(edit_goal_handler, pattern="^edit_goal_")],
        EDIT_TARGET_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_target_weight_handler)],
        EDIT_GOAL_RATE: [CallbackQueryHandler(edit_goal_rate_handler, pattern="^edit_rate_")],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_user=True
)

# edit_goal_conv = ConversationHandler(
#     entry_points=[CallbackQueryHandler(edit_goal_start, pattern="edit_goal")],
#     states={
#         EDIT_GOAL: [CallbackQueryHandler(edit_goal_handler, pattern="^edit_goal_")],
#         EDIT_TARGET_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_target_weight_handler)],
#         EDIT_GOAL_RATE: [CallbackQueryHandler(edit_goal_rate_handler, pattern="^edit_rate_")]
#     },
#     fallbacks=[CommandHandler('cancel', cancel)],
#     per_user=True
# )

conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_handler)],
        WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, weight_handler)],
        HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, height_handler)],
        AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age_handler)],
        GENDER: [CallbackQueryHandler(gender_handler)],
        ACTIVITY: [CallbackQueryHandler(activity_handler)],
        GOAL: [CallbackQueryHandler(goal_handler, pattern="^goal_")],
        TARGET_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, target_weight_handler)],
        GOAL_RATE: [CallbackQueryHandler(goal_rate_handler, pattern="^rate_")]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_user=True
)

# Отдельные обработчики
confirm_handler = CallbackQueryHandler(confirm_meal, pattern="^confirm_meal$")
clear_today_handler = CallbackQueryHandler(clear_today, pattern="^clear_today$")
retry_handler = CallbackQueryHandler(retry_meal, pattern="^retry_meal$")
last_7_days_handler = CallbackQueryHandler(show_last_7_days, pattern="^last_7_days$")
goal_callback_handler = CallbackQueryHandler(goal_handler, pattern="^goal_")
goal_rate_callback_handler = CallbackQueryHandler(goal_rate_handler, pattern="^rate_")
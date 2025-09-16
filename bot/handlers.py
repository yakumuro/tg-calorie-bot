from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters, CallbackContext
)
from bot.database import add_user, get_user, add_meal, get_stats, get_meals_last_7_days, set_notifications, get_notifications_status
from bot.utils import calculate_daily_calories, get_main_menu, render_progress_bar
from bot.database import calculate_macros, delete_meals_for_day
from bot.database import get_user_goal_info, update_goal_start_date, get_goal_start_date
from bot.yandex_gpt import analyze_food_with_gpt
from config.config import YANDEX_GPT_API_KEY, YANDEX_GPT_FOLDER_ID
from datetime import datetime, date
from collections import defaultdict
from bot.charts import create_weekly_chart, create_monthly_chart
from bot.yandex_speechkit import YandexSpeechToText
import os
from logger_config import logger

stt = YandexSpeechToText()

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
    logger.info(f"User {user_id} started /start command")
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
        logger.info(f"User {user_id} already registered, sending main menu")
        await update.message.reply_text(user_text, parse_mode="Markdown", reply_markup=get_main_menu())
        return ConversationHandler.END
    logger.info(f"User {user_id} not registered, sending tutorial")
    await update.message.reply_text(tutorial_text, parse_mode="Markdown", reply_markup=None)
    return NAME


async def name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.message.text
    context.user_data['name'] = update.message.text
    logger.info(f"User {user_id} entered name: {name}")
    await update.message.reply_text("Введи свой вес (в кг, например, 70.5):")
    return WEIGHT


async def weight_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        weight = float(update.message.text)
        if weight <= 0: raise ValueError
        context.user_data['weight'] = weight
        logger.info(f"User {user_id} entered weight: {weight}")
        await update.message.reply_text("Введи свой рост (в см, например, 175):")
        return HEIGHT
    except ValueError:
        logger.warning(f"User {user_id} entered invalid weight: {update.message.text}")
        await update.message.reply_text("Пожалуйста, введи вес числом (например, 70.5):")
        return WEIGHT


async def height_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        height = int(update.message.text)
        if height <= 0: raise ValueError
        context.user_data['height'] = height
        logger.info(f"User {user_id} entered height: {height}")
        await update.message.reply_text("Введи свой возраст:")
        return AGE
    except ValueError:
        logger.warning(f"User {user_id} entered invalid height: {update.message.text}")
        await update.message.reply_text("Пожалуйста, введи рост числом (например, 175):")
        return HEIGHT


async def age_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        age = int(update.message.text)
        if age <= 0: raise ValueError
        context.user_data['age'] = age
        logger.info(f"User {user_id} entered age: {age}")

        keyboard = [
            [InlineKeyboardButton("🚹 Мужской", callback_data='male'),
             InlineKeyboardButton("🚺 Женский", callback_data='female')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выбери свой пол:", reply_markup=reply_markup)
        return GENDER
    except ValueError:
        logger.warning(f"User {user_id} entered invalid age: {update.message.text}")
        await update.message.reply_text("Пожалуйста, введи возраст числом (например, 30):")
        return AGE


async def gender_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query
    await query.answer()
    context.user_data['gender'] = query.data
    logger.info(f"User {user_id} selected gender: {query.data}")

    keyboard = [
        [InlineKeyboardButton("Нет активности (сидячий образ жизни)", callback_data='none')],
        [InlineKeyboardButton("Минимальная (работа на ногах)", callback_data='low')],
        [InlineKeyboardButton("Средняя (1-3 тренировки в неделю)", callback_data='medium')],
        [InlineKeyboardButton("Высокая (3-5 тренировок в неделю)", callback_data='high')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выбери уровень активности:", reply_markup=reply_markup)
    return ACTIVITY

async def activity_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query
    await query.answer()
    activity_code = query.data  # 'none', 'low', 'medium', 'high'
    context.user_data['activity_code'] = activity_code  # код для вычислений
    context.user_data['activity_level'] = ACTIVITY_LABELS[activity_code]  # метка для профиля
    logger.info(f"User {user_id} selected activity: {activity_code}")

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
    user_id = update.effective_user.id
    logger.info(f"User {user_id} canceled registration")
    await update.message.reply_text("Отменено.", reply_markup=get_main_menu())
    return ConversationHandler.END

# --- Профиль ---
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested profile view")
    user = get_user(user_id)
    if not user:
        logger.warning(f"User {user_id} has no profile")
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
    logger.info(f"User {user_id} profile displayed")

# --- Редактирование профиля: начало ---

async def edit_profile_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query
    await query.answer()
    logger.info(f"User {user_id} started editing profile")

    keyboard = [
        [InlineKeyboardButton("👤 Имя", callback_data="edit_name"),
        InlineKeyboardButton("⚖️ Вес", callback_data="edit_weight")],
        [InlineKeyboardButton("📏 Рост", callback_data="edit_height"),
        InlineKeyboardButton("🎂 Возраст", callback_data="edit_age")],
        [InlineKeyboardButton("🚻 Пол", callback_data="edit_gender"),
        InlineKeyboardButton("🏃 Активность", callback_data="edit_activity")],
        [InlineKeyboardButton("🎯 Цель", callback_data="edit_goal")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text("Что хочешь изменить?", reply_markup=reply_markup)
    logger.debug(f"User {user_id} edit profile menu sent")

# Обработчики для каждого поля
async def edit_name_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query
    await query.answer()
    context.user_data['editing_field'] = 'name'
    await query.message.edit_text("Введите новое имя:", reply_markup=None)
    logger.info(f"User {user_id} editing field: name")

async def edit_weight_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query
    await query.answer()
    context.user_data['editing_field'] = 'weight'
    await query.message.edit_text("Введите новый вес (кг):", reply_markup=None)
    logger.info(f"User {user_id} editing field: weight")

async def edit_height_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query
    await query.answer()
    context.user_data['editing_field'] = 'height'
    await query.message.edit_text("Введите новый рост (см):", reply_markup=None)
    logger.info(f"User {user_id} editing field: height")

async def edit_age_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query
    await query.answer()
    context.user_data['editing_field'] = 'age'
    await query.message.edit_text("Введите новый возраст:", reply_markup=None)
    logger.info(f"User {user_id} editing field: age")

async def edit_gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🚹Мужской", callback_data="set_gender_male"),
         InlineKeyboardButton("🚺Женский", callback_data="set_gender_female")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Удаляем старое сообщение и отправляем новое
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"User {user_id} failed to delete old message for gender edit: {e}")
        pass
    
    await query.message.chat.send_message("Выберите пол:", reply_markup=reply_markup)
    logger.info(f"User {user_id} editing field: gender")

async def edit_activity_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("Нет активности", callback_data="set_activity_none")],
        [InlineKeyboardButton("Минимальная", callback_data="set_activity_low")],
        [InlineKeyboardButton("Средняя", callback_data="set_activity_medium")],
        [InlineKeyboardButton("Высокая", callback_data="set_activity_high")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"User {user_id} failed to delete old message for activity edit: {e}")
        pass
    
    await query.message.chat.send_message("Выберите уровень активности:", reply_markup=reply_markup)
    logger.info(f"User {user_id} editing field: activity")

async def edit_goal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("Похудеть", callback_data="set_goal_lose")],
        [InlineKeyboardButton("Набрать", callback_data="set_goal_gain")],
        [InlineKeyboardButton("Поддерживать", callback_data="set_goal_maintain")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"User {user_id} failed to delete old message for goal edit: {e}")
        pass
    
    await query.message.chat.send_message("Выберите цель:", reply_markup=reply_markup)
    logger.info(f"User {user_id} editing field: goal")

# Обработчик текстовых сообщений для редактирования
async def handle_all_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"handle_all_text_input вызван для пользователя {update.effective_user.id}")
    logger.info(f"editing_field: {context.user_data.get('editing_field')}")
    logger.info(f"editing_goal: {context.user_data.get('editing_goal')}")

    # Проверяем, что пользователь в процессе редактирования
    if 'editing_field' not in context.user_data and 'editing_goal' not in context.user_data:
        logger.info("Пользователь не в процессе редактирования, пропускаем")
        return

    text = update.message.text
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user:
        await update.message.reply_text("Ошибка: профиль не найден.", reply_markup=get_main_menu())
        context.user_data.pop('editing_field', None)
        context.user_data.pop('editing_goal', None)
        return

    # Сохраняем текущие поля цели, чтобы не переписывать их при редактировании других полей
    goal_type = user.get("goal_type")
    target_weight = user.get("target_weight")
    goal_rate = user.get("goal_rate")

    # Если редактируем обычное поле
    if 'editing_field' in context.user_data:
        field = context.user_data['editing_field']
        logger.info(f"User {user_id} редактирует поле {field}")

        try:
            if field == 'name':
                new_name = text
                goal_start_date = get_goal_start_date(user_id)
                add_user(
                    user_id,
                    new_name,
                    user["weight"],
                    user["height"],
                    user["age"],
                    user["gender"],
                    user["activity_level"],
                    user["daily_calories"],
                    goal_type=goal_type,
                    target_weight=target_weight,
                    goal_rate=goal_rate,
                    goal_start_date=goal_start_date
                )
                await update.message.reply_text("✅ Имя обновлено!", reply_markup=get_main_menu())
                logger.info(f"User {user_id} обновил имя на {text}")

            elif field == 'weight':
                weight = float(text)
                if weight <= 0:
                    raise ValueError
                activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == user["activity_level"]][0]
                new_calories = calculate_daily_calories(weight, user["height"], user["age"], user["gender"], activity_code)
                protein_norm, fat_norm, carbs_norm = calculate_macros(weight, new_calories)
                goal_start_date = get_goal_start_date(user_id)
                add_user(
                    user_id,
                    user["name"],
                    weight,
                    user["height"],
                    user["age"],
                    user["gender"],
                    user["activity_level"],
                    new_calories,
                    goal_type=goal_type,
                    target_weight=target_weight,
                    goal_rate=goal_rate,
                    goal_start_date=goal_start_date
                )
                await update.message.reply_text(
                    f"✅ Вес обновлён!\n\n🎯 Новая норма калорий: {new_calories} ккал\n\n"
                    f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
                    parse_mode="HTML", reply_markup=get_main_menu()
                )
                logger.info(f"User {user_id} обновил вес на {weight} кг, новая норма: {new_calories} ккал")

            elif field == 'height':
                height = int(text)
                if height <= 0:
                    raise ValueError
                activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == user["activity_level"]][0]
                new_calories = calculate_daily_calories(user["weight"], height, user["age"], user["gender"], activity_code)
                protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], new_calories)
                goal_start_date = get_goal_start_date(user_id)
                add_user(
                    user_id,
                    user["name"],
                    user["weight"],
                    height,
                    user["age"],
                    user["gender"],
                    user["activity_level"],
                    new_calories,
                    goal_type=goal_type,
                    target_weight=target_weight,
                    goal_rate=goal_rate,
                    goal_start_date=goal_start_date
                )
                await update.message.reply_text(
                    f"✅ Рост обновлён!\n\n🎯 Новая норма калорий: {new_calories} ккал\n\n"
                    f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
                    parse_mode="HTML", reply_markup=get_main_menu()
                )

            elif field == 'age':
                age = int(text)
                if age <= 0:
                    raise ValueError
                activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == user["activity_level"]][0]
                new_calories = calculate_daily_calories(user["weight"], user["height"], age, user["gender"], activity_code)
                protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], new_calories)
                goal_start_date = get_goal_start_date(user_id)
                add_user(
                    user_id,
                    user["name"],
                    user["weight"],
                    user["height"],
                    age,
                    user["gender"],
                    user["activity_level"],
                    new_calories,
                    goal_type=goal_type,
                    target_weight=target_weight,
                    goal_rate=goal_rate,
                    goal_start_date=goal_start_date
                )
                await update.message.reply_text(
                    f"✅ Возраст обновлён!\n\n🎯 Новая норма калорий: {new_calories} ккал\n\n"
                    f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
                    parse_mode="HTML", reply_markup=get_main_menu()
                )

        except ValueError:
            logger.warning(f"User {user_id} ввёл некорректное число для поля {field}: {text}")
            await update.message.reply_text("Введите корректное число:")
            return

        # Очищаем состояние редактирования
        context.user_data.pop('editing_field', None)
    
    # Если редактируем цель (вводим целевой вес)
    elif 'editing_goal' in context.user_data:
        goal_type = context.user_data['editing_goal']
        logger.info(f"User {user_id} редактирует цель {goal_type}")
        
        try:
            target_weight = float(text)
            if target_weight <= 0:
                raise ValueError
        except ValueError:
            logger.warning(f"User {user_id} ввёл некорректное число для поля {field}: {text}")
            await update.message.reply_text("Введите корректный вес числом (например, 70.0):")
            return

        current_weight = user["weight"]

        if goal_type == "lose" and not (target_weight < current_weight):
            logger.warning(f"User {user_id} ввёл некорректный целевой вес {target_weight} для цели {goal_type}")
            await update.message.reply_text("Целевой вес должен быть меньше текущего:")
            return
        if goal_type == "gain" and not (target_weight > current_weight):
            logger.warning(f"User {user_id} ввёл некорректный целевой вес {target_weight} для цели {goal_type}")
            await update.message.reply_text("Целевой вес должен быть больше текущего:")
            return

        context.user_data['editing_target_weight'] = target_weight
        logger.info(f"User {user_id} установил целевой вес {target_weight} для цели {goal_type}")

        # Предлагаем темп
        if goal_type == "lose":
            keyboard = [
                [InlineKeyboardButton("Долго и легко — 0.25 кг/нед", callback_data="set_rate_lose_slow")],
                [InlineKeyboardButton("Сбалансированно — 0.5 кг/нед", callback_data="set_rate_lose_medium")],
                [InlineKeyboardButton("Быстро — 1.0 кг/нед", callback_data="set_rate_lose_fast")]
            ]
        else:  # gain
            keyboard = [
                [InlineKeyboardButton("Медленно — 0.25 кг/нед", callback_data="set_rate_gain_slow")],
                [InlineKeyboardButton("Сбалансированно — 0.5 кг/нед", callback_data="set_rate_gain_medium")],
                [InlineKeyboardButton("Быстро — 0.75 кг/нед", callback_data="set_rate_gain_fast")]
            ]

        await update.message.reply_text("Выбери темп достижения цели:", reply_markup=InlineKeyboardMarkup(keyboard))
        logger.info(f"User {user_id} получил варианты темпа достижения цели для {goal_type}")

# Обработчики для кнопок выбора пола
async def set_gender_male(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user = get_user(user_id)
    logger.info(f"User {user_id} clicked 'Male' gender button")
    if not user:
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"User {user_id} profile not found when trying to set gender to Male")
            pass
        await query.message.chat.send_message("Ошибка: профиль не найден.", reply_markup=get_main_menu())
        return
    
    activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == user["activity_level"]][0]
    new_calories = calculate_daily_calories(user["weight"], user["height"], user["age"], "male", activity_code)
    protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], new_calories)
    
    add_user(user_id, user["name"], user["weight"], user["height"], user["age"], "male", 
            user["activity_level"], new_calories,
            goal_type=user.get("goal_type"), target_weight=user.get("target_weight"), 
            goal_rate=user.get("goal_rate"))
    
    logger.info(
    f"User {user_id} updated gender to Male; "
    f"new_calories={new_calories}, protein={protein_norm}, fat={fat_norm}, carbs={carbs_norm}"
    )
    
    try:
        await query.message.delete()
    except Exception:
        pass
    
    await query.message.chat.send_message(
        f"✅ Пол обновлён!\n\n🎯 Новая норма калорий: {new_calories} ккал\n\n"
        f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
        parse_mode="HTML", reply_markup=get_main_menu()
    )

async def set_gender_female(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user = get_user(user_id)
    logger.info(f"User {user_id} clicked 'Female' gender button")
    
    if not user:
        try:
            await query.message.delete()
        except Exception:
            logger.warning(f"User {user_id} profile not found when trying to set gender to Female")
            pass
        await query.message.chat.send_message("Ошибка: профиль не найден.", reply_markup=get_main_menu())
        return
    
    activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == user["activity_level"]][0]
    new_calories = calculate_daily_calories(user["weight"], user["height"], user["age"], "female", activity_code)
    protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], new_calories)
    
    add_user(user_id, user["name"], user["weight"], user["height"], user["age"], "female", 
            user["activity_level"], new_calories,
            goal_type=user.get("goal_type"), target_weight=user.get("target_weight"), 
            goal_rate=user.get("goal_rate"))
    
    logger.info(
    f"User {user_id} updated gender to Female; "
    f"new_calories={new_calories}, protein={protein_norm}, fat={fat_norm}, carbs={carbs_norm}"
    )
    
    try:
        await query.message.delete()
    except Exception:
        pass
    
    await query.message.chat.send_message(
        f"✅ Пол обновлён!\nНовая норма: {new_calories} ккал\n"
        f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
        parse_mode="HTML", reply_markup=get_main_menu()
    )

# Обработчики для кнопок выбора активности
async def set_activity_none(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user = get_user(user_id)
    logger.info(f"User {user_id} clicked activity level 'None'")
    
    if not user:
        try:
            await query.message.delete()
        except Exception:
            logger.warning(f"User {user_id} profile not found when trying to set activity level 'None'")
            pass
        await query.message.chat.send_message("Ошибка: профиль не найден.", reply_markup=get_main_menu())
        return
    
    new_calories = calculate_daily_calories(user["weight"], user["height"], user["age"], user["gender"], "none")
    protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], new_calories)
    
    add_user(user_id, user["name"], user["weight"], user["height"], user["age"], user["gender"], 
            "Нет активности", new_calories,
            goal_type=user.get("goal_type"), target_weight=user.get("target_weight"), 
            goal_rate=user.get("goal_rate"))
    logger.info(
    f"User {user_id} updated activity to 'None'; "
    f"new_calories={new_calories}, protein={protein_norm}, fat={fat_norm}, carbs={carbs_norm}"
    )
    
    try:
        await query.message.delete()
    except Exception:
        pass
    
    await query.message.chat.send_message(
        f"✅ Активность обновлена!\n\n🎯 Новая норма калорий: {new_calories} ккал\n\n"
        f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
        parse_mode="HTML", reply_markup=get_main_menu()
    )

async def set_activity_low(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user = get_user(user_id)
    logger.info(f"User {user_id} clicked activity level 'Low'")
    
    if not user:
        try:
            await query.message.delete()
        except Exception:
            logger.warning(f"User {user_id} profile not found when trying to set activity level 'Low'")
            pass
        await query.message.chat.send_message("Ошибка: профиль не найден.", reply_markup=get_main_menu())
        return
    
    new_calories = calculate_daily_calories(user["weight"], user["height"], user["age"], user["gender"], "low")
    protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], new_calories)
    
    add_user(user_id, user["name"], user["weight"], user["height"], user["age"], user["gender"], 
            "Минимальная", new_calories,
            goal_type=user.get("goal_type"), target_weight=user.get("target_weight"), 
            goal_rate=user.get("goal_rate"))
    logger.info(
    f"User {user_id} updated activity to 'None'; "
    f"new_calories={new_calories}, protein={protein_norm}, fat={fat_norm}, carbs={carbs_norm}"
    )
    
    try:
        await query.message.delete()
    except Exception:
        pass
    
    await query.message.chat.send_message(
        f"✅ Активность обновлена!\nНовая норма: {new_calories} ккал\n"
        f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
        parse_mode="HTML", reply_markup=get_main_menu()
    )

async def set_activity_medium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user = get_user(user_id)
    logger.info(f"User {user_id} clicked activity level 'Medium'")
    
    if not user:
        try:
            await query.message.delete()
        except Exception:
            logger.warning(f"User {user_id} profile not found when trying to set activity level 'Medium'")
            pass
        await query.message.chat.send_message("Ошибка: профиль не найден.", reply_markup=get_main_menu())
        return
    
    new_calories = calculate_daily_calories(user["weight"], user["height"], user["age"], user["gender"], "medium")
    protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], new_calories)
    
    add_user(user_id, user["name"], user["weight"], user["height"], user["age"], user["gender"], 
            "Средняя", new_calories,
            goal_type=user.get("goal_type"), target_weight=user.get("target_weight"), 
            goal_rate=user.get("goal_rate"))
    logger.info(
    f"User {user_id} updated activity to 'None'; "
    f"new_calories={new_calories}, protein={protein_norm}, fat={fat_norm}, carbs={carbs_norm}"
    )
    
    try:
        await query.message.delete()
    except Exception:
        pass
    
    await query.message.chat.send_message(
        f"✅ Активность обновлена!\nНовая норма: {new_calories} ккал\n"
        f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
        parse_mode="HTML", reply_markup=get_main_menu()
    )

async def set_activity_high(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user = get_user(user_id)
    logger.info(f"User {user_id} clicked activity level 'High'")

    if not user:
        try:
            await query.message.delete()
        except Exception:
            logger.warning(f"User {user_id} profile not found when trying to set activity level 'High'")
            pass
        await query.message.chat.send_message("Ошибка: профиль не найден.", reply_markup=get_main_menu())
        return
    
    new_calories = calculate_daily_calories(user["weight"], user["height"], user["age"], user["gender"], "high")
    protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], new_calories)
    
    add_user(user_id, user["name"], user["weight"], user["height"], user["age"], user["gender"], 
            "Высокая", new_calories,
            goal_type=user.get("goal_type"), target_weight=user.get("target_weight"), 
            goal_rate=user.get("goal_rate"))
    
    logger.info(
    f"User {user_id} updated activity to 'None'; "
    f"new_calories={new_calories}, protein={protein_norm}, fat={fat_norm}, carbs={carbs_norm}"
    )
    
    try:
        await query.message.delete()
    except Exception:
        pass
    
    await query.message.chat.send_message(
        f"✅ Активность обновлена!\nНовая норма: {new_calories} ккал\n"
        f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
        parse_mode="HTML", reply_markup=get_main_menu()
    )

# Обработчики для кнопок выбора цели
async def set_goal_maintain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user = get_user(user_id)
    logger.info(f"User {user_id} clicked 'Maintain goal' button")
    
    if not user:
        logger.warning(f"User {user_id} profile not found when selecting 'maintain' goal")
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete message for user {user_id}: {e}")
            pass
        await query.message.chat.send_message("Ошибка: профиль не найден.", reply_markup=get_main_menu())
        return
    
    activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == user["activity_level"]][0]
    daily_calories = calculate_daily_calories(user["weight"], user["height"], user["age"], user["gender"], activity_code)
    protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], daily_calories)
    
    add_user(user_id, user["name"], user["weight"], user["height"], user["age"], user["gender"],
             user["activity_level"], daily_calories, goal_type='maintain', target_weight=None, goal_rate=None)
    logger.info(
        f"User {user_id} set goal to 'maintain'; "
        f"daily_calories={daily_calories}, protein={protein_norm}, fat={fat_norm}, carbs={carbs_norm}"
    )
    
    try:
        await query.message.delete()
    except Exception:
        pass
    
    await query.message.chat.send_message(
        f"✅ Цель обновлена на «Поддерживать»!\n"
        f" Норма: {daily_calories} ккал\n"
        f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )

async def set_goal_lose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    logger.info(f"User {user_id} clicked 'Lose weight' goal button")
    
    context.user_data['editing_goal'] = 'lose'
    logger.info(f"User {user_id} entering target weight input for goal 'lose'")
    
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete message when entering target weight for user {user_id}: {e}")
        pass
    
    await query.message.chat.send_message("Введите целевой вес (в кг):", reply_markup=None)

async def set_goal_gain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    logger.info(f"User {user_id} clicked 'Gain weight' goal button")

    context.user_data['editing_goal'] = 'gain'
    logger.info(f"User {user_id} entering target weight input for goal 'gain'")
    
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete message when entering target weight for user {user_id}: {e}")
        pass
    
    await query.message.chat.send_message("Введите целевой вес (в кг):", reply_markup=None)


# Обработчики для выбора темпа
async def set_rate_lose_slow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"User {update.effective_user.id} clicked rate_lose_slow (0.25 kg/week)")
    await set_goal_with_rate(update, context, "lose", 0.25)

async def set_rate_lose_medium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"User {update.effective_user.id} clicked rate_lose_medium (0.5 kg/week)")
    await set_goal_with_rate(update, context, "lose", 0.5)

async def set_rate_lose_fast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"User {update.effective_user.id} clicked rate_lose_fast (1.0 kg/week)")
    await set_goal_with_rate(update, context, "lose", 1.0)

async def set_rate_gain_slow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"User {update.effective_user.id} clicked rate_gain_slow (0.25 kg/week)")
    await set_goal_with_rate(update, context, "gain", 0.25)

async def set_rate_gain_medium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"User {update.effective_user.id} clicked rate_gain_medium (0.5 kg/week)")
    await set_goal_with_rate(update, context, "gain", 0.5)

async def set_rate_gain_fast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"User {update.effective_user.id} clicked rate_gain_fast (0.75 kg/week)")
    await set_goal_with_rate(update, context, "gain", 0.75)

async def set_goal_with_rate(update: Update, context: ContextTypes.DEFAULT_TYPE, goal_type: str, kg_per_week: float):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user = get_user(user_id)
    logger.info(f"User {user_id} invoked set_goal_with_rate; goal_type={goal_type}, kg_per_week={kg_per_week}")
    target_weight = context.user_data.get('editing_target_weight')
    
    activity_code = [k for k, v in ACTIVITY_LABELS.items() if v == user["activity_level"]][0]
    maintenance = calculate_daily_calories(user["weight"], user["height"], user["age"], user["gender"], activity_code)
    daily_adjustment = (kg_per_week * 7700) / 7.0
    daily_calories = round(maintenance - daily_adjustment, 1) if goal_type == "lose" else round(maintenance + daily_adjustment, 1)
    
    protein_norm, fat_norm, carbs_norm = calculate_macros(user["weight"], daily_calories)
    
    add_user(user_id, user["name"], user["weight"], user["height"], user["age"], user["gender"],
             user["activity_level"], daily_calories, goal_type=goal_type,
             target_weight=target_weight, goal_rate=f"{kg_per_week}кг/нед")
    
    logger.info(
        f"User {user_id} goal updated: goal_type={goal_type}, kg_per_week={kg_per_week}, "
        f"target_weight={target_weight}, daily_calories={daily_calories}, "
        f"protein={protein_norm}, fat={fat_norm}, carbs={carbs_norm}"
    )
    
    # ВАЖНОЕ ДОБАВЛЕНИЕ: обновляем дату начала цели при редактировании
    logger.info(f"Updating goal start date for user {user_id} during profile edit")
    update_goal_start_date(user_id, datetime.now())
    
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete message after setting goal rate for user {user_id}: {e}")
        pass
    
    await query.message.chat.send_message(
        f"✅ Цель обновлена!\n\n"
        f"🎯 {('Похудеть' if goal_type=='lose' else 'Набрать')} ({kg_per_week} кг/нед)\n"
        f"🎯 Целевой вес: {target_weight} кг\n"
        f"🎯 Норма калорий с учётом цели: {daily_calories} ккал\n\n"
        f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )
    
    # Очищаем временные данные
    context.user_data.pop('editing_goal', None)
    context.user_data.pop('editing_target_weight', None)

# --- Добавление еды ---
async def add_meal_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"User {user_id} started adding a meal (text input)")
    await update.message.reply_text("Подробно опиши, что съел. Пиши максимально подробно, указывая вес порций и ингредиенты:", reply_markup=None)
    return ADD_MEAL

async def process_food_text(update, context, food_text: str):
    # 🕒 Сообщение "обрабатываем"
    processing_msg = await update.message.reply_text("⏳ Обрабатываем ваш запрос...")
    user_id = update.effective_user.id
    logger.info(f"User {user_id} submitted food text: {food_text}")

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
        logger.info(
        f"User {user_id} GPT recognized items: {len(items)} items, "
        f"total_calories={totals['calories']}, protein={totals['protein']}, "
        f"fat={totals['fat']}, carbs={totals['carbs']}"
        )

        # Удаляем сообщение "обрабатываем"
        try:
            await processing_msg.delete()
        except Exception as e:
            logger.error(f"User {user_id} GPT processing error: {e}")
            pass

        # Формируем текст с продуктами и прогрессом
        user_id = update.effective_user.id
        stats_data = get_stats(user_id)
        daily_norm = get_user(user_id)["daily_calories"]
        already_eaten = stats_data['day']['calories'] or 0
        projected = already_eaten + totals['calories'] or 0

        progress_after = render_progress_bar(projected, daily_norm)

        warning_text = ""
        if daily_norm > 0 and projected > daily_norm:
            excess = projected - daily_norm
            warning_text = f"\n⚠️ <b>Внимание:</b> После добавления норма будет превышена на <b>{excess:.0f} ккал</b>!\n"

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
{warning_text}

Выбери действие:
        """

        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_meal")],
            [InlineKeyboardButton("🔁 Ввести заново", callback_data="retry_meal")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

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


async def add_food_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    voice = update.message.voice
    user_id = update.effective_user.id
    logger.info(f"User {user_id} sent a voice message for meal input")

    if not voice:
        await update.message.reply_text("Не удалось получить голосовое сообщение 😔")
        return ADD_MEAL

    file = await context.bot.get_file(voice.file_id)
    file_path = f"voice_{user.id}.ogg"
    await file.download_to_drive(file_path)

    try:
        # 🎤 Транскрибируем
        text = stt.recognize(file_path)
        logger.info(f"User {user_id} voice STT result: {text}")

        # 🔄 Используем ту же логику, что и для текста
        return await process_food_text(update, context, text)

    except Exception as e:
        logger.error(f"User {user_id} voice processing error: {e}")
        await update.message.reply_text(f"Ошибка при обработке голосового: {e}")
        return ADD_MEAL

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)



async def handle_food_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    food_text = update.message.text
    return await process_food_text(update, context, food_text)


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

    user_id = update.effective_user.id
    logger.info(
    f"User {user_id} confirmed meal: {pending['calories']} kcal, "
    f"protein={pending['protein']}, fat={pending['fat']}, carbs={pending['carbs']}"
    )

    # Удаляем сообщение с текстом еды + кнопками
    last_message_id = context.user_data.get('last_meal_message_id')
    if last_message_id:
        try:
            await query.message.chat.delete_message(last_message_id)
        except Exception as e:
            logger.warning(f"User {user_id} failed to delete old meal message: {e}")
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
    user_id = update.effective_user.id
    logger.info(f"User {user_id} chose to retry meal input")

    # Удаляем старое сообщение с текстом еды + кнопками
    last_message_id = context.user_data.get('last_meal_message_id')
    if last_message_id:
        try:
            await query.message.chat.delete_message(last_message_id)
        except Exception as e:
            logger.warning(f"User {user_id} failed to delete old meal message: {e}")
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
    logger.info(f"User {user_id} requested stats")

    if not user:
        await update.message.reply_text("Нет профиля. /start", reply_markup=None)
        return

    daily_norm = user["daily_calories"] or 0
    protein_norm = user["protein_norm"] or 0
    fat_norm = user["fat_norm"] or 0
    carbs_norm = user["carbs_norm"] or 0

    stats_data = get_stats(user_id)
    progress_today = render_progress_bar(stats_data['day']['calories'], daily_norm)

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

    warning_text_today = ""
    if daily_norm > 0 and day_calories > daily_norm:
        excess_today = day_calories - daily_norm
        warning_text_today = f"⚠️ <b>Превышение:</b> +{excess_today:.0f} ккал"
        logger.warning(f"User {user_id} exceeded daily calories by {excess_today} kcal")

    # Проверяем есть ли цель
    goal_info = get_user_goal_info(user_id)
    
    keyboard = [
        [InlineKeyboardButton("📊 График за неделю", callback_data="chart_week"),
         InlineKeyboardButton("📊 График за месяц", callback_data="chart_month")],
        [InlineKeyboardButton("📅 История за неделю", callback_data="last_7_days"),
         InlineKeyboardButton("🗑 Очистить еду за сегодня", callback_data="clear_today")]
    ]
    
    # Добавляем кнопки для целей если они есть
    if goal_info:
        keyboard.append([InlineKeyboardButton("🎯 График цели", callback_data="goal_chart"), InlineKeyboardButton("📈 Текущий прогресс", callback_data="current_progress")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📊 <b>Статистика</b>:\n\n"
        f"<b>Сегодня</b>:\n\n"
        f"Каллорий: {progress_today}\n\n"
        f"{warning_text_today}\n\n"
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
    logger.info(f"User {user_id} requested last 7 days menu")

    if not meals:
        logger.info(f"User {user_id} has no meals for last 7 days")
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
    user_id = update.effective_user.id
    await query.answer()

    user_id = update.effective_user.id

    # Удаляем приёмы пищи за сегодня
    deleted = delete_meals_for_day(user_id)

    if deleted:
        logger.info(f"User {user_id} cleared today's meals")
        await query.message.reply_text(f"✅ История еды за сегодня удалена.", reply_markup=get_main_menu())
    else:
        logger.info(f"User {user_id} tried to clear meals but none were added today")
        await query.message.reply_text(f"ℹ️ За сегодня нет добавленных приёмов пищи.", reply_markup=get_main_menu())

async def fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Fallback handler triggered for user {user_id}")
    
    # Если пользователь в процессе редактирования, не показываем fallback
    if 'editing_field' in context.user_data or 'editing_goal' in context.user_data:
        logger.info(f"User {user_id} is editing profile/goal, skipping fallback")
        return
    
    # Если пользователь написал что-то не через кнопку
    await update.message.reply_text(
        "Пожалуйста, выберите действие через кнопки ниже, прежде чем отправлять текст."
    )


# Графики для статистики 

async def show_goal_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested goal chart")
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    goal_info = get_user_goal_info(user_id)
    
    if not goal_info:
        await query.message.reply_text("У вас нет активной цели.", reply_markup=get_main_menu())
        return
    
    try:
        from bot.charts import create_goal_progress_chart
        from bot.database import get_goal_start_date
        
        start_date = get_goal_start_date(user_id)
        img_buffer, goal_date = await create_goal_progress_chart(
            user_id, 
            goal_info['current_weight'], 
            goal_info['target_weight'], 
            goal_info['goal_type'], 
            goal_info['goal_rate'],
            start_date
        )
        
        goal_date_str = goal_date.strftime("%d.%m.%Y")
        
        await query.message.reply_photo(
            photo=img_buffer,
            caption=f"📉 График достижения цели\n\n"
                   f"Цель: {'Похудеть' if goal_info['goal_type']=='lose' else 'Набрать'}\n"
                   f"Текущий вес: {goal_info['current_weight']} кг\n"
                   f"Целевой вес: {goal_info['target_weight']} кг\n"
                   f"Темп: {goal_info['goal_rate']}\n"
                   f"Дата достижения: {goal_date_str}",
            reply_markup=get_main_menu()
        )
        
    except Exception as e:
        logger.error(f"Error generating for user {user_id}: {e}")
        await query.message.reply_text(
            "❌ Ошибка создания графика. Попробуйте позже.",
            reply_markup=get_main_menu()
        )


async def show_current_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested current progress chart")
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    goal_info = get_user_goal_info(user_id)
    
    if not goal_info:
        await query.message.reply_text("У вас нет активной цели.", reply_markup=get_main_menu())
        return
    
    try:
        from bot.charts import create_current_progress_chart
        from bot.database import get_goal_start_date
        
        start_date = get_goal_start_date(user_id)
        img_buffer = await create_current_progress_chart(
            user_id, 
            goal_info['current_weight'], 
            goal_info['target_weight'], 
            goal_info['goal_type'], 
            goal_info['goal_rate'],
            start_date
        )
        
        await query.message.reply_photo(
            photo=img_buffer,
            caption="📈 Текущий прогресс достижения цели",
            reply_markup=get_main_menu()
        )
        
    except Exception as e:
        logger.error(f"Error generating for user {user_id}: {e}")
        await query.message.reply_text(
            "❌ Ошибка создания графика. Попробуйте позже.",
            reply_markup=get_main_menu()
        )

async def show_weekly_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested weekly chart")
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    try:
        # Создаем график
        img_buffer = await create_weekly_chart(user_id)
        
        # Отправляем как фото
        await query.message.reply_photo(
            photo=img_buffer,
            caption="📈 График калорий за неделю",
            reply_markup=get_main_menu()
        )
        
    except Exception as e:
        logger.error(f"Error generating for user {user_id}: {e}")
        await query.message.reply_text(
            "❌ Ошибка создания графика. Попробуйте позже.",
            reply_markup=get_main_menu()
        )

async def show_monthly_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested monthly chart")
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    try:
        # Создаем график
        img_buffer = await create_monthly_chart(user_id)
        
        # Отправляем как фото
        await query.message.reply_photo(
            photo=img_buffer,
            caption="📊 График калорий за месяц",
            reply_markup=get_main_menu()
        )
        
    except Exception as e:
        logger.error(f"Error generating for user {user_id}: {e}")
        await query.message.reply_text(
            "❌ Ошибка создания графика. Попробуйте позже.",
            reply_markup=get_main_menu()
        )

async def goal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    goal = query.data.replace("goal_", "")  # 'lose' | 'gain' | 'maintain'
    context.user_data['goal'] = goal
    user_id = update.effective_user.id
    logger.info(f"User {user_id} selected goal: {goal}")

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
            logger.error(f"Error calculating daily calories for user {user_id}: {e}")
            await query.message.reply_text("Ошибка при расчёте. Попробуй /start заново.")
            return ConversationHandler.END

    # Если цель похудеть или набрать — запрашиваем целевой вес
    await query.message.reply_text("Введите целевой вес (в кг, например 70.0):", reply_markup=None)
    return TARGET_WEIGHT

async def target_weight_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    logger.info(f"User {user_id} entered target weight: {text}")
    try:
        target = float(text)
        if target <= 0:
            raise ValueError
    except ValueError:
        logger.warning(f"User {user_id} entered invalid target weight: {text}")
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
    user_id = update.effective_user.id
    await query.answer()
    data = query.data  # e.g. rate_lose_medium
    parts = data.split("_")
    
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

    logger.info(f"User {user_id} selected goal rate: {kg_per_week} kg/week for goal {goal_type}")

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
    logger.info(f"Calculated daily calories for user {user_id}: {daily_calories} kcal")

    # Минимум ккал (защита) — можно настроить
    min_cal = 1200 if gender == "female" else 1500
    if daily_calories < min_cal:
        await query.message.reply_text(
            f"Выбранный темп даёт слишком низкую норму ({daily_calories} ккал). Выберите более щадящий темп."
        )
        return GOAL_RATE

    # Факторы для БЖУ в зависимости от цели (упрощённо)
    if goal_type == "lose":
        protein_factor = 2.0
        fat_factor = 1.0
    elif goal_type == "gain":
        protein_factor = 1.6
        fat_factor = 1.0
    else:
        protein_factor = 1.8
        fat_factor = 1.0

    protein_norm, fat_norm, carbs_norm = calculate_macros(weight, daily_calories, protein_factor=protein_factor, fat_factor=fat_factor)

    # Сохраняем пользователя с новыми полями goal
    add_user(user_id, name, weight, height, age, gender, activity_label, daily_calories,
             goal_type=goal_type, target_weight=target_weight, goal_rate=f"{kg_per_week}кг/нед")

    # Устанавливаем дату начала цели - ВАЖНОЕ ИЗМЕНЕНИЕ!
    logger.info(f"Setting goal start date for user {user_id}")
    update_goal_start_date(user_id, datetime.now())

    # Создаем график цели
    try:
        from bot.charts import create_goal_progress_chart
        img_buffer, goal_date = await create_goal_progress_chart(
            user_id, weight, target_weight, goal_type, f"{kg_per_week}кг/нед"
        )
        
        goal_date_str = goal_date.strftime("%d.%m.%Y")
        
        await query.message.reply_photo(
            photo=img_buffer,
            caption=f"✅ Профиль создан!\n\n"
                   f"🎯 Цель: {'Похудеть' if goal_type=='lose' else 'Набрать'} ({kg_per_week} кг/нед)\n"
                   f"🎯 Целевой вес: {target_weight} кг\n"
                   f"🎯 Дата достижения: {goal_date_str}\n\n"
                   f"🎯 Норма с учётом цели: <b>{daily_calories} ккал</b>\n"
                   f"🥩Б: {protein_norm} г, 🥑Ж: {fat_norm} г, 🍞У: {carbs_norm} г",
            parse_mode="HTML",
            reply_markup=get_main_menu()
        )
    except Exception as e:
        logger.error(f"Error generating goal chart for user {user_id}: {e}")
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

async def settings_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    status = get_notifications_status(user_id)
    logger.info(f"Open setting menu {user_id}")

    notif_text = "🔔 Уведомления: [Включены]" if status else "🔕 Уведомления: [Выключены]"

    keyboard = [
        [InlineKeyboardButton(notif_text, callback_data="toggle_notifications")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:  # если вызвано из кнопки
        await update.callback_query.edit_message_text(
            "⚙ Настройки:\n\nЗдесь вы можете управлять общими настройками бота. Если остались вопросы, можете написать @yakumuro", reply_markup=reply_markup
        )
    else:  # если вызвано командой /settings
        await update.message.reply_text("⚙ Настройки:\n\n Здесь вы можете управлять общими настройками бота. Если остались вопросы, можете написать @yakumuro", reply_markup=reply_markup)

# Уведомления пользователей раз в 16 часов
async def toggle_notifications(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id

    # Проверяем текущий статус
    current_status = get_notifications_status(user_id)
    new_status = not current_status

    # Обновляем в БД
    set_notifications(user_id, new_status)
    logger.info(f"Edit settings notification {user_id}: {new_status}")

    # Отвечаем пользователю
    status_text = "✅ Уведомления включены" if new_status else "🚫 Уведомления выключены"
    await query.answer()
    await query.edit_message_text(
        text=f"{status_text}\n\nМожно вернуться и поменять в любой момент.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔔 Переключить снова", callback_data="toggle_notifications")]
        ])
    )


# --- Обработчики ---
profile_handler = MessageHandler(filters.Regex("^👤 Профиль$"), profile)
stats_handler = MessageHandler(filters.Regex("^📊 Статистика$"), stats)
settings_handler = MessageHandler(filters.Regex("^⚙️ Настройки"), settings_menu)


meal_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^📝 Добавить приём пищи$"), add_meal_start)],
    states={
        ADD_MEAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_food_input), MessageHandler(filters.VOICE, add_food_voice),],
        AWAIT_CONFIRM: [
            CallbackQueryHandler(confirm_meal, pattern="^confirm_meal$"),
            CallbackQueryHandler(retry_meal, pattern="^retry_meal$")
        ]
    },
    fallbacks=[CommandHandler('cancel', cancel_meal)],
    per_user=True
)

# --- Новые обработчики (заменяют старые ConversationHandler'ы) ---
edit_profile_handler = CallbackQueryHandler(edit_profile_start, pattern="edit_profile")
edit_name_handler = CallbackQueryHandler(edit_name_callback, pattern="edit_name")
edit_weight_handler = CallbackQueryHandler(edit_weight_callback, pattern="edit_weight")
edit_height_handler = CallbackQueryHandler(edit_height_callback, pattern="edit_height")
edit_age_handler = CallbackQueryHandler(edit_age_callback, pattern="edit_age")
edit_gender_handler = CallbackQueryHandler(edit_gender_callback, pattern="edit_gender")
edit_activity_handler = CallbackQueryHandler(edit_activity_callback, pattern="edit_activity")
edit_goal_handler = CallbackQueryHandler(edit_goal_callback, pattern="edit_goal")

# Обработчики для кнопок выбора
set_gender_male_handler = CallbackQueryHandler(set_gender_male, pattern="set_gender_male")
set_gender_female_handler = CallbackQueryHandler(set_gender_female, pattern="set_gender_female")
set_activity_none_handler = CallbackQueryHandler(set_activity_none, pattern="set_activity_none")
set_activity_low_handler = CallbackQueryHandler(set_activity_low, pattern="set_activity_low")
set_activity_medium_handler = CallbackQueryHandler(set_activity_medium, pattern="set_activity_medium")
set_activity_high_handler = CallbackQueryHandler(set_activity_high, pattern="set_activity_high")
set_goal_maintain_handler = CallbackQueryHandler(set_goal_maintain, pattern="set_goal_maintain")
set_goal_lose_handler = CallbackQueryHandler(set_goal_lose, pattern="set_goal_lose")
set_goal_gain_handler = CallbackQueryHandler(set_goal_gain, pattern="set_goal_gain")
set_rate_lose_slow_handler = CallbackQueryHandler(set_rate_lose_slow, pattern="set_rate_lose_slow")
set_rate_lose_medium_handler = CallbackQueryHandler(set_rate_lose_medium, pattern="set_rate_lose_medium")
set_rate_lose_fast_handler = CallbackQueryHandler(set_rate_lose_fast, pattern="set_rate_lose_fast")
set_rate_gain_slow_handler = CallbackQueryHandler(set_rate_gain_slow, pattern="set_rate_gain_slow")
set_rate_gain_medium_handler = CallbackQueryHandler(set_rate_gain_medium, pattern="set_rate_gain_medium")
set_rate_gain_fast_handler = CallbackQueryHandler(set_rate_gain_fast, pattern="set_rate_gain_fast")


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
voice_message_handler = MessageHandler(filters.VOICE, add_food_voice)
toggle_notifications_handler = CallbackQueryHandler(toggle_notifications, pattern="toggle_notifications")

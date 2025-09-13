import aiohttp
import json

def get_main_menu():
    from telegram import ReplyKeyboardMarkup
    keyboard = [
        ["📝 Добавить приём пищи"],
        ["👤 Профиль", "📊 Статистика"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


def calculate_daily_calories(weight, height, age, gender, activity_level):
    if gender == 'male':
        bmr = 88.362 + (13.397 * weight) + (4.799 * height) - (5.677 * age)
    elif gender == 'female':
        bmr = 447.593 + (9.247 * weight) + (3.098 * height) - (4.330 * age)
    else:
        raise ValueError("gender must be 'male' or 'female'")

    factors = {'none': 1.2, 'low': 1.375, 'medium': 1.55, 'high': 1.725}
    factor = factors.get(activity_level)
    if not factor:
        raise ValueError(f"Unknown activity level: {activity_level}")

    return round(bmr * factor, 1)

# --- Утилита для прогресс-бара ---
def render_progress_bar(current, total, length=20):
    if total <= 0:
        return "[Нет данных]"
    ratio = min(current / total, 1)
    filled = int(length * ratio)
    empty = length - filled
    return f"[{'▓' * filled}{'▒' * empty}] {current}/{total} ккал"
import aiohttp
import json
import matplotlib.pyplot as plt
import os
from logger_config import logger

def get_main_menu():
    from telegram import ReplyKeyboardMarkup
    keyboard = [
        ["🍜 Добавить еду", "📝 Создать меню"],
        ["👤 Профиль", "📊 Статистика"],
        ["⚙️ Настройки"]
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
    return f"[{'▓' * filled}{'▒' * empty}] {current}/{total}"

def render_menu_to_image(menu_data: dict, user_id: int) -> str:
    import matplotlib.pyplot as plt, os

    logger.info(f"Start rendering menu image for user_id={user_id}")

    meals = menu_data.get("meals", [])
    rows = []

    for meal in meals:
        meal_name = meal.get("name", "")
        items = meal.get("items", [])
        est_cal = sum(it.get("calories", 0) for it in items)

        item_strs = []
        for it in items:
            product_name = it.get("product") or it.get("name") or "unknown"
            quantity = it.get("quantity") or it.get("amount") or ""
            item_strs.append(f"{product_name} ({quantity})" if quantity else product_name)
        items_str = ", ".join(item_strs) if item_strs else "—"

        row_text = f"{meal_name} (~{est_cal} ккал): {items_str}"
        rows.append(row_text)
        logger.debug(f"Processed meal row: {row_text}")

    totals = menu_data.get("totals", {})
    totals_str = f"Итого: {totals.get('calories',0)} ккал | Б {totals.get('protein',0)} Ж {totals.get('fat',0)} У {totals.get('carbs',0)}"
    rows.append(totals_str)
    logger.debug(f"Processed totals row: {totals_str}")

    try:
        fig_height = max(2, len(rows) * 0.8)
        fig, ax = plt.subplots(figsize=(12, fig_height))
        ax.axis("off")
        table_data = [[r] for r in rows]
        table = ax.table(cellText=table_data, colLabels=["Меню на сегодня"], cellLoc="left", loc="center")
        table.auto_set_font_size(False)
        table.set_fontsize(12)
        table.scale(1, 1.5)

        os.makedirs("generated", exist_ok=True)
        image_path = f"generated/menu_{user_id}.png"
        plt.savefig(image_path, bbox_inches="tight", dpi=200)
        plt.close(fig)
        logger.info(f"Menu image successfully saved at {image_path}")
    except Exception as e:
        logger.error(f"Error while rendering menu image: {e}")
        raise RuntimeError(f"Ошибка при создании изображения меню: {e}")

    return image_path

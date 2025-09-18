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
    from PIL import Image, ImageDraw, ImageFont
    import os, textwrap, logging, math
    logger = logging.getLogger(__name__)

    meals = menu_data.get("meals", []) or []
    totals = menu_data.get("totals", {}) or {}

    # layout
    width = 1000
    padding_x = 32
    padding_y = 28
    table_padding = 12
    line_spacing = 6

    col_ratios = [0.16, 0.52, 0.12, 0.20]
    inner_width = width - 2 * padding_x
    col_widths = [int(inner_width * r) for r in col_ratios]

    # Попробуем надёжно подобрать шрифт (без требовать установки):
    # пробуем несколько часто встречающихся путей/имён; если ничего нет — fallback load_default()
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "DejaVuSans.ttf",
        "NotoSans-Regular.ttf",
        "Arial.ttf",
        "LiberationSans-Regular.ttf",
        "FreeSans.ttf",
    ]
    font = None
    font_bold = None
    for p in font_candidates:
        try:
            font = ImageFont.truetype(p, 16)
            font_bold = ImageFont.truetype(p, 18)
            break
        except Exception:
            font = None
    if font is None:
        font = ImageFont.load_default()
        font_bold = font

    # измерения
    def text_size(txt, fnt):
        bbox = fnt.getbbox(str(txt))
        return (bbox[2] - bbox[0], bbox[3] - bbox[1])

    def text_width(txt, fnt):
        return text_size(txt, fnt)[0]

    def wrap_text_to_width(text, fnt, max_width):
        lines = []
        for paragraph in str(text).split("\n"):
            words = paragraph.split(" ")
            cur = ""
            for w in words:
                if cur == "":
                    test = w
                else:
                    test = cur + " " + w
                if text_width(test, fnt) <= max_width:
                    cur = test
                else:
                    if cur:
                        lines.append(cur)
                    if text_width(w, fnt) > max_width:
                        part = ""
                        for ch in w:
                            if text_width(part + ch, fnt) <= max_width:
                                part += ch
                            else:
                                if part:
                                    lines.append(part)
                                part = ch
                        if part:
                            cur = part
                        else:
                            cur = ""
                    else:
                        cur = w
            if cur:
                lines.append(cur)
        if not lines:
            return [""]
        return lines

    # собираем строки
    rows = []
    computed_totals = {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
    for meal in meals:
        meal_name = meal.get("name", "Приём")
        items = meal.get("items", []) or []
        item_lines = []
        for it in items:
            prod = it.get("product") or it.get("name") or "продукт"
            qty = it.get("quantity") or it.get("amount") or ""
            c = int(float(it.get("calories", 0) or 0))
            s = f"• {prod}"
            if qty:
                s += f" ({qty})"
            s += f" — {c} ккал"
            item_lines.append(s)
        items_text = "\n".join(item_lines) if item_lines else "—"

        meal_cal = meal.get("calories")
        meal_prot = meal.get("protein")
        meal_fat = meal.get("fat")
        meal_carbs = meal.get("carbs")
        if meal_cal is None:
            meal_cal = sum(int(float(it.get("calories", 0) or 0)) for it in items)
        if meal_prot is None:
            meal_prot = sum(float(it.get("protein", 0) or 0) for it in items)
        if meal_fat is None:
            meal_fat = sum(float(it.get("fat", 0) or 0) for it in items)
        if meal_carbs is None:
            meal_carbs = sum(float(it.get("carbs", 0) or 0) for it in items)

        computed_totals["calories"] += float(meal_cal or 0)
        computed_totals["protein"] += float(meal_prot or 0)
        computed_totals["fat"] += float(meal_fat or 0)
        computed_totals["carbs"] += float(meal_carbs or 0)

        macros_text = f"Б {int(round(meal_prot or 0))} г  Ж {int(round(meal_fat or 0))} г  У {int(round(meal_carbs or 0))} г"

        rows.append({
            "meal": str(meal_name),
            "items": items_text,
            "cal": str(int(round(meal_cal or 0))),
            "macros": macros_text
        })

    # totals fallback
    if not totals or int(totals.get("calories", 0)) == 0:
        totals = {
            "calories": int(round(computed_totals["calories"])),
            "protein": round(computed_totals["protein"], 1),
            "fat": round(computed_totals["fat"], 1),
            "carbs": round(computed_totals["carbs"], 1),
        }

    header_font = font_bold
    regular_font = font
    title_font = font_bold

    sample_h = text_size("Ay", regular_font)[1]
    line_h = sample_h + line_spacing
    cell_pad = table_padding

    title_text = "Меню на сегодня"
    title_h = text_size(title_text, title_font)[1] + 12

    # подготовка обёртки
    wrapped_rows = []
    for r in rows:
        w_meal = wrap_text_to_width(r["meal"], header_font, col_widths[0] - 2 * cell_pad)
        w_items = []
        for line in str(r["items"]).split("\n"):
            w_items.extend(wrap_text_to_width(line, regular_font, col_widths[1] - 2 * cell_pad))
        w_cal = wrap_text_to_width(r["cal"], regular_font, col_widths[2] - 2 * cell_pad)
        w_mac = wrap_text_to_width(r["macros"], regular_font, col_widths[3] - 2 * cell_pad)
        max_lines = max(len(w_meal), len(w_items), len(w_cal), len(w_mac), 1)
        row_h = max_lines * line_h + 2 * cell_pad
        wrapped_rows.append({
            "meal_lines": w_meal,
            "items_lines": w_items,
            "cal_lines": w_cal,
            "mac_lines": w_mac,
            "height": row_h
        })

    header_h = line_h + 2 * cell_pad
    totals_h = line_h + 2 * cell_pad

    table_rows_height = sum(r["height"] for r in wrapped_rows)
    footer_space = 16
    height = padding_y + title_h + 8 + header_h + table_rows_height + totals_h + padding_y + footer_space
    min_h = 300
    if height < min_h:
        height = min_h

    # создаём картинку
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # заголовок
    tx = padding_x
    ty = padding_y
    draw.text((tx, ty), title_text, font=title_font, fill=(24, 24, 24))
    table_y = ty + title_h + 8

    # координаты колонок
    x0 = padding_x
    x1 = x0 + col_widths[0]
    x2 = x1 + col_widths[1]
    x3 = x2 + col_widths[2]
    x4 = x3 + col_widths[3]
    table_x1 = x0
    table_x2 = x4

    border_color = (200, 200, 200)
    draw.rectangle([table_x1 - 2, table_y - 2, table_x2 + 2, table_y + header_h + table_rows_height + totals_h + 4],
                   outline=border_color, width=1)

    header_bg = (245, 245, 245)
    draw.rectangle([table_x1, table_y, table_x2, table_y + header_h], fill=header_bg, outline=None)

    col_xs = [x0, x1, x2, x3]
    headers = ["Приём", "Блюда", "Ккал", "Б/Ж/У"]
    for i, h in enumerate(headers):
        cx = col_xs[i] + table_padding
        cy = table_y + cell_pad
        draw.text((cx, cy), h, font=header_font, fill=(30, 30, 30))

    draw.line([table_x1, table_y + header_h, table_x2, table_y + header_h], fill=border_color, width=1)

    # строки
    y = table_y + header_h
    alt_bg = (255, 255, 255)
    alt_bg2 = (250, 250, 250)
    for idx, wr in enumerate(wrapped_rows):
        row_h = wr["height"]
        bg = alt_bg if idx % 2 == 0 else alt_bg2
        draw.rectangle([table_x1, y, table_x2, y + row_h], fill=bg)

        draw.line([x1, y, x1, y + row_h], fill=border_color, width=1)
        draw.line([x2, y, x2, y + row_h], fill=border_color, width=1)
        draw.line([x3, y, x3, y + row_h], fill=border_color, width=1)

        cell_x = x0 + table_padding
        cell_y = y + cell_pad
        for i_line, tline in enumerate(wr["meal_lines"]):
            draw.text((cell_x, cell_y + i_line * line_h), tline, font=header_font, fill=(35, 35, 35))

        cell_x = x1 + table_padding
        cell_y = y + cell_pad
        for i_line, tline in enumerate(wr["items_lines"]):
            draw.text((cell_x, cell_y + i_line * line_h), tline, font=regular_font, fill=(60, 60, 60))

        cell_x = x2 + table_padding
        cell_y = y + cell_pad
        for i_line, tline in enumerate(wr["cal_lines"]):
            draw.text((cell_x, cell_y + i_line * line_h), tline, font=regular_font, fill=(40, 40, 40))

        cell_x = x3 + table_padding
        cell_y = y + cell_pad
        for i_line, tline in enumerate(wr["mac_lines"]):
            draw.text((cell_x, cell_y + i_line * line_h), tline, font=regular_font, fill=(40, 40, 40))

        y += row_h
        draw.line([table_x1, y, table_x2, y], fill=border_color, width=1)

    # итоги
    totals_bg = (240, 240, 245)
    draw.rectangle([table_x1, y, table_x2, y + totals_h], fill=totals_bg)
    draw.line([x1, y, x1, y + totals_h], fill=border_color, width=1)
    draw.line([x2, y, x2, y + totals_h], fill=border_color, width=1)
    draw.line([x3, y, x3, y + totals_h], fill=border_color, width=1)

    draw.text((x0 + table_padding, y + cell_pad), "ИТОГО", font=header_font, fill=(20, 20, 20))
    draw.text((x2 + table_padding, y + cell_pad), f"{int(totals.get('calories',0))} ккал", font=header_font, fill=(20, 20, 20))
    macros_tot = f"Б {int(round(totals.get('protein',0)))} г  Ж {int(round(totals.get('fat',0)))} г  У {int(round(totals.get('carbs',0)))} г"
    draw.text((x3 + table_padding, y + cell_pad), macros_tot, font=header_font, fill=(20, 20, 20))

    # сохранить
    os.makedirs("generated", exist_ok=True)
    image_path = f"generated/menu_{user_id}.png"
    try:
        img.save(image_path, format="PNG")
        logger.info(f"Menu image saved to {image_path}")
    except Exception as e:
        logger.exception("Failed to save menu image")
        raise

    return image_path

import aiohttp
import json
from logger_config import logger
import math
import re

async def analyze_food_with_gpt(food_text: str, api_key: str, folder_id: str) -> dict:
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json"
    }

    prompt = f"""
Ты — эксперт по питанию и подсчёту калорий. Проанализируй, что человек съел.

### Правила:
1. Разбей блюдо на **основные ингредиенты** (например: "омлет" → яйца, молоко, масло).
2. Если указан **вес или объём** (граммы, мл, штуки) — используй его для точного расчёта.
3. Если вес не указан — оцени как **стандартную порцию** (например, 1 яйцо = 50 г, 1 ломтик хлеба = 30 г).
4. Учитывай калории **всех компонентов**, включая масло, майонез, соусы.
5. Калории указывай в **ккал**.
6. Отдельно возвращай количество белков, жиров и углеводов для каждого ингредиента и для блюда в целом.
7. Верни **ТОЛЬКО валидный JSON**, без ```json, без пояснений, без комментариев.

### Формат ответа:
{{
  "items": [
    {{"product": "название", "quantity": "100 г", "calories": число, "protein": число, "fat": число, "carbs": число}}
  ],
  "total": {{
    "calories": число,
    "protein": число,
    "fat": число,
    "carbs": число
  }}
}}

Теперь проанализируй:
"{food_text}"
"""

    payload = {
        "modelUri": f"gpt://{folder_id}/yandexgpt-lite/latest",
        "completionOptions": {"temperature": 0.3, "maxTokens": "500"},
        "messages": [{"role": "user", "text": prompt}]
    }

    logger.info(f"Send YandexGPT: {food_text}")
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            logger.info(f"Response status YandexGPT: {resp.status}")
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Error GPT: {text}")
                raise Exception(f"GPT error {resp.status}: {text}")

            result = await resp.json()
            logger.info(f"Response YandexGPT: {result}")

    try:
        text = result['result']['alternatives'][0]['message']['text'].strip()
        print(f"📝 Исходный текст от GPT: {repr(text)}")

        # 🔧 Удаляем Markdown-обёртку ``` и языки
        if text.startswith('```'):
            text = text.split('\n', 1)[1]  # Пропускаем первую строку с ```
            text = text.rsplit('```', 1)[0]  # Удаляем последнюю строку с ```
            text = text.strip()

        if text.startswith('```json'):
            text = text[7:].strip()
            if text.endswith('```'):
                text = text[:-3].strip()

        print(f"📝 Очищенный текст: {text}")

        # Парсим JSON
        data = json.loads(text)

        # Проверяем структуру
        if not isinstance(data, dict):
            raise ValueError("JSON должен быть объектом")

        if "total" not in data:
            raise ValueError("Нет блока total с БЖУ")

        totals = data["total"]
        if not isinstance(totals, dict):
            raise ValueError("total должен быть объектом")

        # Вытаскиваем значения
        calories = totals.get("calories", 0)
        protein = totals.get("protein", 0)
        fat = totals.get("fat", 0)
        carbs = totals.get("carbs", 0)

        # items всегда должен быть списком
        if not isinstance(data.get("items"), list):
            data["items"] = []

        print(f"✅ Успешно распарсили: {data}")
        return data

    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        print(f"Текст, который не удалось распарсить: {text}")
        raise Exception("GPT вернул не-JSON")
    except Exception as e:
        print(f"❌ Ошибка обработки ответа: {e}")
        raise

# --- GPT запрос и анализ меню (пересобранная версия) ---
async def analyze_menu_with_gpt(
    user_goal: str,
    daily_calories: float,
    protein_norm: float,
    fat_norm: float,
    carbs_norm: float,
    meals_per_day: int,
    prefs_and_restrictions: str,
    api_key: str,
    folder_id: str
) -> dict:
    import aiohttp, json, re, logging
    logger = logging.getLogger(__name__)

    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json"}

    # Распределение калорий
    percents_map = {
        1: [100],
        2: [45, 55],
        3: [25, 45, 30],
        4: [25, 10, 40, 25],
        5: [20, 8, 40, 8, 24]
    }
    percents = percents_map.get(meals_per_day, percents_map[3])

    # Названия приёмов
    names_map = {
        1: ["Приём 1"],
        2: ["Приём 1", "Приём 2"],
        3: ["Завтрак", "Обед", "Ужин"],
        4: ["Завтрак", "Перекус 1", "Обед", "Ужин"],
        5: ["Завтрак", "Перекус 1", "Обед", "Перекус 2", "Ужин"]
    }
    meal_names = names_map.get(meals_per_day, names_map[3])

    # Целевые калории по каждому приёму
    meal_targets = [
        {"name": n, "target_calories": int(round(daily_calories * p / 100))}
        for n, p in zip(meal_names, percents)
    ]

    # Базовый JSON-скелет для промпта
    meal_names_json = ", ".join([f'{{"name": "{n}", "items": []}}' for n in meal_names])

    # 🔥 Новый строгий промпт
    prompt = f"""
Составь меню на один день ({meals_per_day} приёмов пищи) для цели: "{user_goal}".
Дневная цель (КБЖУ):
- Калории: {daily_calories}
- Белки: {protein_norm} г
- Жиры: {fat_norm} г
- Углеводы: {carbs_norm} г
Ограничения и предпочтения: {prefs_and_restrictions}

ОЧЕНЬ ВАЖНО — ПРАВИЛА:
1) Верни строго **JSON** (никакого текста вне JSON).
2) Поле "meals" = массив ровно из {meals_per_day} объектов:
   {{
     "name": "название приёма",
     "items": [{{"product": "название", "quantity": "150 г", "calories": 200, "protein": 15, "fat": 5, "carbs": 20}}, ...],
     "calories": число,
     "protein": число,
     "fat": число,
     "carbs": число
   }}
3) Калории приёма ≈ его целевой доли:
   {json.dumps(meal_targets, ensure_ascii=False)} (допуск ±10%).
4) "calories" каждого приёма = сумма калорий его items.
5) "totals" = сумма всех приёмов (calories/protein/fat/carbs). Не копируй норму.
6) totals.calories должен быть в пределах {int(daily_calories*0.95)}–{int(daily_calories)} ккал.
7) Используй реалистичные продукты и порции.
8) Ответ — только JSON. Пример:
{{
  "meals": [
    {meal_names_json}
  ],
  "totals": {{"calories": 0, "protein": 0, "fat": 0, "carbs": 0}}
}}
"""

    payload = {
        "modelUri": f"gpt://{folder_id}/yandexgpt/rc",
        "completionOptions": {"temperature": 0.7, "maxTokens": 1400},
        "messages": [{"role": "user", "text": prompt}]
    }

    # --- Вспомогательные функции ---
    async def send_request(pl):
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=pl, headers=headers, timeout=60) as resp:
                txt = await resp.text()
                if resp.status != 200:
                    raise RuntimeError(f"GPT error {resp.status}: {txt}")
                js = await resp.json()
                try:
                    return js["result"]["alternatives"][0]["message"]["text"]
                except Exception:
                    return txt

    def extract_json_substring(text: str):
        text = re.sub(r"^```[\w]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
        match = re.search(r'(\{.*\}|\[.*\])', text, flags=re.S)
        if not match:
            raise ValueError("JSON not found")
        return match.group(0)

    def parse_num(v):
        if isinstance(v, (int, float)):
            return float(v)
        m = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(v))
        return float(m.group(0).replace(",", ".")) if m else 0.0

    def recompute(md: dict):
        totals = {"calories": 0, "protein": 0, "fat": 0, "carbs": 0}
        for meal in md.get("meals", []):
            cal = prot = fat = ch = 0
            for it in meal.get("items", []):
                cal += parse_num(it.get("calories"))
                prot += parse_num(it.get("protein"))
                fat += parse_num(it.get("fat"))
                ch += parse_num(it.get("carbs"))
            meal["calories"] = int(round(cal))
            meal["protein"] = round(prot, 1)
            meal["fat"] = round(fat, 1)
            meal["carbs"] = round(ch, 1)
            totals["calories"] += cal
            totals["protein"] += prot
            totals["fat"] += fat
            totals["carbs"] += ch
        md["totals"] = {
            "calories": int(round(totals["calories"])),
            "protein": round(totals["protein"], 1),
            "fat": round(totals["fat"], 1),
            "carbs": round(totals["carbs"], 1),
        }
        return md

    # --- Первый запрос ---
    raw = await send_request(payload)
    menu = json.loads(extract_json_substring(raw))
    menu = recompute(menu)

    # --- Финальная нормализация ---
    total_cal = menu["totals"]["calories"]
    if total_cal > daily_calories:
        # Скейлим вниз
        scale = daily_calories / total_cal
        for meal in menu["meals"]:
            for it in meal["items"]:
                for k in ("calories", "protein", "fat", "carbs"):
                    it[k] = int(it[k]*scale) if k=="calories" else round(it[k]*scale, 1)
        menu = recompute(menu)

    elif total_cal < daily_calories*0.95:
        # Один ретрай: просим увеличить
        retry_prompt = prompt + f"\n\nВ предыдущем варианте было {total_cal} ккал. Увеличь порции/блюда так, чтобы получилось {int(daily_calories*0.95)}–{int(daily_calories)} ккал."
        payload["messages"] = [{"role": "user", "text": retry_prompt}]
        raw2 = await send_request(payload)
        menu2 = recompute(json.loads(extract_json_substring(raw2)))
        if abs(daily_calories - menu2["totals"]["calories"]) < abs(daily_calories - total_cal):
            menu = menu2

    return menu

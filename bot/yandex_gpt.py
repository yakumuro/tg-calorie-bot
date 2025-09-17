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

import aiohttp
import json
import re
from logger_config import logger

# --- GPT запрос и анализ меню ---
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

    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json"
    }

    # Формируем список названий приёмов пищи для промта
    if meals_per_day == 1:
        meal_names = ["Приём 1"]
    elif meals_per_day == 2:
        meal_names = ["Приём 1", "Приём 2"]
    elif meals_per_day == 3:
        meal_names = ["Завтрак", "Обед", "Ужин"]
    elif meals_per_day == 4:
        meal_names = ["Завтрак", "Перекус 1", "Обед", "Ужин"]
    else:  # 5
        meal_names = ["Завтрак", "Перекус 1", "Обед", "Перекус 2", "Ужин"]

    # Преобразуем в JSON-строку для примера GPT
    meal_names_json = ", ".join([f'{{"name": "{name}", "items": []}}' for name in meal_names])

    # Подготовка запроса с четким указанием количества приемов пищи
    prompt = f"""
Сгенерируй меню на один день с {meals_per_day} приёмами пищи для цели пользователя "{user_goal}" и КБЖУ:
- Калории: {daily_calories}
- Белки: {protein_norm} г
- Жиры: {fat_norm} г
- Углеводы: {carbs_norm} г
Пользовательские пожелания/ограничения: {prefs_and_restrictions}

Важные правила:
1. Каждый приём пищи должен содержать реальные продукты с количеством и КБЖУ (калории, белки, жиры, углеводы).
2. Общее поле "totals" должно быть суммой всех блюд, которые ты сгенерировал. **Не копируй значения из нормы пользователя**.
3. Норму КБЖУ нужно максимально близко достичь, но не превышать её.
4. Если блюд меньше, чем заданное количество приёмов, добавь недостающие приёмы с подходящими блюдами.

Названия приёмов пищи для {meals_per_day} приёмов: {meal_names_json}

Строго верни валидный JSON с таким форматом:
{{
  "meals": [
    {meal_names_json}
  ][:{meals_per_day}],
  "totals": {{"calories": 0, "protein": 0, "fat": 0, "carbs": 0}}
}}
Ответ только JSON, без объяснений.
"""


    payload = {
        "modelUri": f"gpt://{folder_id}/yandexgpt/rc",
        "completionOptions": {"temperature": 0.7, "maxTokens": 1200},
        "messages": [{"role": "user", "text": prompt}]
    }

    logger.info(f"GPT request start: goal={user_goal}, meals_per_day={meals_per_day}")
    logger.debug(f"GPT prompt prepared: {prompt[:300]}...")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers, timeout=60) as resp:
                logger.info(f"Response status YandexGPT: {resp.status}")
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Error GPT response: {text}")
                    raise RuntimeError(f"GPT error {resp.status}: {text}")
                result = await resp.json()
                logger.debug(f"Raw GPT response: {json.dumps(result)[:500]}...")
        except Exception as e:
            logger.error(f"Network error while connecting to GPT: {e}")
            raise RuntimeError(f"Ошибка сети при запросе к GPT: {e}")

    try:
        result_text = result['result']['alternatives'][0]['message']['text'].strip()
        logger.info(f"Raw GPT text received (first 300 chars): {result_text[:300]}")
    except Exception as e:
        logger.error(f"Error extracting GPT text: {e}")
        raise RuntimeError(f"Ошибка разбора ответа GPT: {e}")

    try:
        clean_text = re.sub(r"^```[\w]*\n?|```$", "", result_text).strip()
        menu_data = json.loads(clean_text)
        logger.info("GPT response successfully parsed as JSON")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}\nResponse text: {clean_text[:500]}")
        raise RuntimeError(f"Ошибка декодирования JSON от GPT: {e}")

    # Коррекция количества приемов пищи
    if len(menu_data.get("meals", [])) != meals_per_day:
        menu_data["meals"] = menu_data.get("meals", [])[:meals_per_day]
        logger.warning(f"Adjusted meals count to {meals_per_day}")

    return menu_data
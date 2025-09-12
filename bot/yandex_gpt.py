import aiohttp
import json

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

    print(f"📨 Отправляю в GPT: {food_text}")
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            print(f"📡 Статус ответа GPT: {resp.status}")
            if resp.status != 200:
                text = await resp.text()
                print(f"❌ Ошибка GPT: {text}")
                raise Exception(f"GPT error {resp.status}: {text}")

            result = await resp.json()
            print(f"🟢 Ответ GPT: {result}")

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

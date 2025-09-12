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
6. Верни **ТОЛЬКО валидный JSON**, без ```json, без пояснений, без комментариев.

### Формат ответа:
{{
  "items": [
    {{"product": "название продукта", "quantity": "количество с единицами", "calories": число}}
  ],
  "total_calories": число
}}

### Примеры:
Ввод: "200 г творога 9%"
Выход:
{{"items": [{{"product": "творог", "quantity": "200 г", "calories": 180}}], "total_calories": 180}}

Ввод: "Гречка с тушенкой"
Выход:
{{
  "items": [
    {{"product": "гречка", "quantity": "150 г", "calories": 150}},
    {{"product": "тушенка", "quantity": "100 г", "calories": 280}}
  ],
  "total_calories": 430
}}

Ввод: "Кофе с молоком"
Выход:
{{
  "items": [
    {{"product": "кофе", "quantity": "200 мл", "calories": 5}},
    {{"product": "молоко", "quantity": "50 мл", "calories": 65}}
  ],
  "total_calories": 70
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

        # Также удаляем, если есть ```json
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
        if 'total_calories' not in data:
            raise ValueError("Нет поля total_calories")
        if not isinstance(data.get('items'), list):
            data['items'] = []

        print(f"✅ Успешно распарсили: {data}")
        return data

    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        print(f"Текст, который не удалось распарсить: {text}")
        raise Exception("GPT вернул не-JSON")
    except Exception as e:
        print(f"❌ Ошибка обработки ответа: {e}")
        raise
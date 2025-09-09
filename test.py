import os
from dotenv import load_dotenv

load_dotenv()

YANDEX_GPT_API_KEY = os.getenv("YANDEX_GPT_API_KEY")
YANDEX_GPT_FOLDER_ID = os.getenv("YANDEX_GPT_FOLDER_ID")

print(YANDEX_GPT_API_KEY)
print(YANDEX_GPT_FOLDER_ID)
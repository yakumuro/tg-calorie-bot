# voice_recognition.py
import os
import requests
from config.config import YANDEX_SPEECH_API_KEY

SPEECHKIT_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"


class YandexSpeechToText:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or YANDEX_SPEECH_API_KEY
        if not self.api_key:
            raise ValueError("YANDEX_SPEECH_API_KEY is not set in environment")

    def recognize(self, audio_path: str, lang: str = "ru-RU") -> str:
        """
        Отправляет голосовое сообщение в Yandex SpeechKit и возвращает текст.
        :param audio_path: путь к файлу (ogg, mp3, wav)
        :param lang: язык распознавания
        :return: транскрибированный текст
        """
        headers = {
            "Authorization": f"Api-Key {self.api_key}"
        }

        with open(audio_path, "rb") as f:
            audio_data = f.read()

        params = {"lang": lang}

        response = requests.post(
            SPEECHKIT_URL,
            params=params,
            headers=headers,
            data=audio_data
        )

        if response.status_code != 200:
            raise RuntimeError(f"Yandex STT error: {response.status_code}, {response.text}")

        result = response.json()
        if "result" in result:
            return result["result"]
        else:
            raise RuntimeError(f"Unexpected response: {result}")

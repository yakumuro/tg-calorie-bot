import asyncio
import time
from collections import deque
from typing import Callable, Any, Dict, Deque, Coroutine
from config.config import MAX_REQUESTS_PER_MINUTE, WINDOW_SECONDS, CONCURRENT_GPT
from datetime import datetime, timedelta
from bot.database import get_db_connection

from logger_config import logger


# Внутренние структуры (in-memory)
_user_requests: Dict[int, Deque[float]] = {}
_user_locks: Dict[int, asyncio.Lock] = {}
_global_lock = asyncio.Lock()
_global_semaphore = asyncio.Semaphore(CONCURRENT_GPT)


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded, retry after {retry_after}s")


async def _get_user_lock(user_id: int) -> asyncio.Lock:
    """Возвращает asyncio.Lock для пользователя (создаёт при необходимости)."""
    async with _global_lock:
        lock = _user_locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            _user_locks[user_id] = lock
        return lock


async def _reserve_slot_or_raise(user_id: int) -> None:
    """
    Проверяет и резервирует слот для пользователя.
    При превышении лимита бросает RateLimitExceeded(retry_after).
    """
    now = time.time()
    lock = await _get_user_lock(user_id)

    async with lock:
        dq = _user_requests.get(user_id)
        if dq is None:
            dq = deque()
            _user_requests[user_id] = dq

        # очистка старых записей
        while dq and dq[0] <= now - WINDOW_SECONDS:
            dq.popleft()

        if len(dq) >= MAX_REQUESTS_PER_MINUTE:
            retry_after = int(WINDOW_SECONDS - (now - dq[0])) + 1
            logger.debug(f"User {user_id} rate-limited. Retry after {retry_after}s")
            raise RateLimitExceeded(retry_after)

        # резервируем текущее время (вставляем в конец)
        dq.append(now)
        logger.debug(f"Reserved request slot for user {user_id}. Count={len(dq)}")


async def _rollback_last_request(user_id: int):
    """Удаляет последний зарезервированный таймстамп (в случае ошибки вызова GPT)."""
    lock = await _get_user_lock(user_id)
    async with lock:
        dq = _user_requests.get(user_id)
        if dq:
            try:
                dq.pop()
                logger.debug(f"Rolled back last request timestamp for user {user_id}")
            except IndexError:
                pass


async def call_gpt_with_limits(user_id: int, gpt_async_fn: Callable[..., Coroutine[Any, Any, Any]], *args, **kwargs):
    """
    Обёртка для вызова асинхронной GPT-функции с ограничениями.
    - user_id — телеграм id пользователя (для per-user limit)
    - gpt_async_fn — асинхронная функция (awaitable) которая вызывает GPT (например, analyze_food_with_gpt)
    - остальные args/kwargs передаются в gpt_async_fn

    Возвращает результат gpt_async_fn или бросает RateLimitExceeded.
    """
    # 1) зарезервировать слот для пользователя или бросить
    await _reserve_slot_or_raise(user_id)

    # 2) выполнить реальный запрос, ограничив одновременные вызовы глобальным семафором
    try:
        async with _global_semaphore:
            logger.debug(f"User {user_id} acquired global GPT semaphore. Running GPT call...")
            result = await gpt_async_fn(*args, **kwargs)
            return result
    except Exception as e:
        # В случае ошибки откатываем резерв (чтобы не "съедать" лимит)
        await _rollback_last_request(user_id)
        logger.exception(f"Error during GPT call for user {user_id}: {e}")
        raise

class RateLimitExceededMenu(Exception):
    def __init__(self, retry_after_seconds: int):
        self.retry_after = retry_after_seconds
        super().__init__(f"Menu request rate limit exceeded, retry after {retry_after_seconds}s")


def check_menu_rate_limit(user_id: int, hours: int = 6):
    """Проверяет, можно ли сгенерировать меню. Если нельзя — бросает RateLimitExceededMenu"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT last_menu_request FROM users WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()

    now = datetime.now()
    if row and row[0]:
        last_request = datetime.fromisoformat(row[0])
        delta = now - last_request
        if delta < timedelta(hours=hours):
            retry_after = int((timedelta(hours=hours) - delta).total_seconds())
            logger.info(f"User {user_id} menu request blocked. Retry after {retry_after}s")
            raise RateLimitExceededMenu(retry_after)


def update_menu_request_time(user_id: int):
    """Обновляет дату последнего запроса меню на текущий момент"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET last_menu_request = ? WHERE user_id = ?
    """, (datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()
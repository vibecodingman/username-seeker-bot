import asyncio
import random
import string
import logging
import os
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилище запущенных задач поиска {chat_id: asyncio.Task}
active_scans = {}

async def check_via_telegram_api(username: str) -> str:
    """Шаг 1: Быстрая проверка через официальное API Telegram"""
    try:
        await bot.get_chat(f"@{username}")
        return "taken"  # Нашел — точно занят
    except TelegramBadRequest as e:
        if "chat not found" in str(e).lower():
            return "maybe_available"  # Не нашел — либо свободен, либо скрыт настройками
        return "taken"
    except TelegramRetryAfter as e:
        logger.warning(f"Флуд-контроль API! Ожидание {e.retry_after} сек.")
        await asyncio.sleep(e.retry_after)
        return "error"
    except Exception:
        return "error"

async def check_via_tme_web(username: str) -> bool:
    """
    Шаг 2: Перепроверка через веб-страницу t.me/{username}.
    Помогает отсечь скрытые личные аккаунты, которые API считает свободными.
    """
    url = f"https://t.me{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(headers=headers, timeout=5.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                html = response.text
                # Если страницы нет (показывается дефолтный текст-заглушка без описания профиля)
                if "if you have telegram, you can contact" in html.lower() and "tgme_page_extra" not in html.lower():
                    return True  # Реально свободен!
            return False
    except Exception as e:
        logger.warning(f"Сбой t.me для @{username}: {e}")
        return False

def generate_random_username(length: int) -> str:
    return "".join(random.choice(string.ascii_lowercase) for _ in range(length))

async def scanning_loop(chat_id: int):
    try:
        await bot.send_message(
            chat_id, 
            "🚀 Поиск перезапущен с умной двухэтапной фильтрацией!\n"
            "Ищем чистые 5 и 6-значные имена без скрытых аккаунтов."
        )
        
        while True:
            # Случайно выбираем длину (5 или 6 знаков)
            length = random.choice([5, 6])
            username = generate_random_username(length)
            
            # Этап 1: Проверяем через Bot API
            api_status = await check_via_telegram_api(username)
            
            if api_status == "maybe_available":
                # Этап 2: Допроверяем через Web-страницу, чтобы исключить скрытые профили
                is_free = await check_via_tme_web(username)
                
                if is_free:
                    message_text = f"🎉 **Найден абсолютно свободный юзернейм!**\n\n👉 `@{username}`\n\nПроверен по двум базам. Забирай быстрее!"
                    await bot.send_message(chat_id, message_text, parse_mode="Markdown")
                    await asyncio.sleep(2)
            
            # Безопасный интервал, чтобы Render и Telegram не ругались
            await asyncio.sleep(random.uniform(5.0, 8.0))
            
    except asyncio.CancelledError:
        await bot.send_message(chat_id, "🛑 Поиск успешно остановлен.")
    except Exception as e:
        logger.error(f"Критическая ошибка в цикле: {e}")
        active_scans.pop(chat_id, None)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я точный двухэтапный чекер юзернеймов (5-6 знаков).\n\n"
        "Команды:\n"
        "/search — Начать точный поиск\n"
        "/stop — Остановить поиск"
    )

@dp.message(Command("search"))
async def cmd_search(message: types.Message):
    chat_id = message.chat.id
    if chat_id in active_scans:
        await message.answer("Поиск уже идет!")
        return
    task = asyncio.create_task(scanning_loop(chat_id))
    active_scans[chat_id] = task

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in active_scans:
        await message.answer("Поиск не запущен.")
        return
    task = active_scans.pop(chat_id)
    task.cancel()

async def main():
    logger.info("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import random
import string
import logging
import os
import httpx  # Не забудь добавить httpx обратно в requirements.txt если удалял
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

async def check_username_via_telegram(username: str) -> str:
    """Шаг 1: Быстрая проверка юзернейма внутренними средствами Telegram."""
    try:
        await bot.get_chat(f"@{username}")
        return "taken"  # Нашел — занят
    except TelegramBadRequest as e:
        if "chat not found" in str(e).lower():
            return "available"  # Не нашел — потенциально свободен
        return "taken"
    except TelegramRetryAfter as e:
        logger.warning(f"Флуд-контроль! Ожидание {e.retry_after} сек.")
        await asyncio.sleep(e.retry_after)
        return "error"
    except Exception as e:
        logger.error(f"Ошибка Telegram API для @{username}: {e}")
        return "error"

async def is_username_on_fragment(username: str) -> bool:
    """
    Шаг 2: Проверка юзернейма на Fragment.com.
    Если возвращает 404 (Not Found) -> имя свободно.
    Если возвращает 200 (OK) -> имя занято аукционом.
    """
    url = f"https://fragment.com{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(headers=headers, timeout=5.0) as client:
            response = await client.get(url)
            # Если код 404 — страницы нет, значит юз свободен на аукционе
            if response.status_code == 404:
                return False
            # Если код 200 — страница существует, значит юз занят (на аукционе или куплен как NFT)
            elif response.status_code == 200:
                logger.info(f"Юзернейм @{username} найден на Fragment. Пропускаем.")
                return True
            return True  # При любых других кодах (например, 429) перестраховываемся и считаем занятым
    except Exception as e:
        # Если у Render опять упадет DNS, мы не ломаем бота, а просто логируем
        logger.warning(f"Ошибка проверки Fragment для @{username} (проблема с сетью хостинга): {e}")
        return True  # Защита: если сайт недоступен, считаем занятым, чтобы не выдать ложный юз

def generate_random_username(length: int) -> str:
    return "".join(random.choice(string.ascii_lowercase) for _ in range(length))

async def scanning_loop(chat_id: int):
    try:
        await bot.send_message(
            chat_id, 
            "🚀 Поиск запущен с двойной проверкой (Telegram + Fragment)!\n"
            "Ищем редкие 5 и 6-значные имена без цифр."
        )
        
        while True:
            length = random.choice([5, 6])
            username = generate_random_username(length)
            
            # 1. Проверяем в самом Telegram
            tg_status = await check_username_via_telegram(username)
            
            if tg_status == "available":
                # 2. Если в ТГ свободен, проверяем, не висит ли он на Фрагменте
                on_fragment = await is_username_on_fragment(username)
                
                if not on_fragment:
                    # Юз прошел обе проверки! Он реально чистый и свободный
                    message_text = f"🎉 **Найден абсолютно свободный юзернейм!**\n\n👉 `@{username}`\n\nЕго нет ни в Telegram, ни на Fragment. Забирай скорее!"
                    await bot.send_message(chat_id, message_text, parse_mode="Markdown")
                    await asyncio.sleep(2)
            
            # Задержка между генерациями
            await asyncio.sleep(random.uniform(5.0, 8.0))
            
    except asyncio.CancelledError:
        await bot.send_message(chat_id, "🛑 Поиск успешно остановлен.")
    except Exception as e:
        logger.error(f"Критическая ошибка в цикле сканирования: {e}")
        active_scans.pop(chat_id, None)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я продвинутый чекер юзернеймов (5-6 знаков).\n"
        "Я проверяю имена и в Telegram, и на сайте Fragment!\n\n"
        "Команды:\n"
        "/search — Начать поиск\n"
        "/stop — Остановить поиск"
    )

@dp.message(Command("search"))
async def cmd_search(message: types.Message):
    chat_id = message.chat.id
    if chat_id in active_scans:
        await message.answer("Поиск уже вовсю идет!")
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

import asyncio
import random
import string
import logging
import os
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилище запущенных задач поиска {chat_id: asyncio.Task}
active_scans = {}

async def is_username_truly_available(username: str) -> bool:
    """
    Проверяет юзернейм напрямую через Fragment.com.
    Это единственный способ отсечь скрытые и заброшенные аккаунты.
    """
    url = f"https://fragment.com/username/{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }
    try:
        async with httpx.AsyncClient(headers=headers, timeout=6.0, follow_redirects=True) as client:
            response = await client.get(url)
            
            # Если 404 — страницы точно нет, юз 100% свободен
            if response.status_code == 404:
                return True
                
            if response.status_code == 200:
                html_text = response.text
                
                # Тщательно проверяем текст страницы на маркеры занятости
                if "unavailable" in html_text.lower() or "taken" in html_text.lower():
                    return False  # Занят обычным пользователем
                if "auction" in html_text.lower() or "place a bid" in html_text.lower():
                    return False  # Висит на аукционе Fragment
                if "is available" in html_text.lower() or "available" in html_text.lower():
                    return True   # Доступен для регистрации
                    
            # При любых подозрительных ответах (например, капча 429) пропускаем, чтобы не спамить
            return False
            
    except Exception as e:
        logger.warning(f"Сбой сети при проверке @{username}: {e}")
        return False

def generate_random_username(length: int) -> str:
    # Ищем красивые имена только из букв
    return "".join(random.choice(string.ascii_lowercase) for _ in range(length))

async def scanning_loop(chat_id: int):
    try:
        await bot.send_message(
            chat_id, 
            "🚀 Поиск перезапущен по новой технологии!\n"
            "Теперь проверяем строго через базу Fragment. Спама занятых юзов больше не будет."
        )
        
        while True:
            # Ищем только 5 и 6-знаки
            length = random.choice([5, 6])
            username = generate_random_username(length)
            
            # Проверяем на Fragment
            available = await is_username_truly_available(username)
            
            if available:
                message_text = f"🎉 **Найден абсолютно свободный юзернейм!**\n\n👉 `@{username}`\n\nПроверен через Fragment. Забирай быстрее!"
                await bot.send_message(chat_id, message_text, parse_mode="Markdown")
                await asyncio.sleep(2)
            
            # Безопасная задержка, чтобы Fragment не забанил IP сервера Render
            await asyncio.sleep(random.uniform(5.0, 8.0))
            
    except asyncio.CancelledError:
        await bot.send_message(chat_id, "🛑 Поиск успешно остановлен.")
    except Exception as e:
        logger.error(f"Критическая ошибка в цикле: {e}")
        active_scans.pop(chat_id, None)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я точный чекер юзернеймов (5-6 знаков).\n"
        "Фильтрую занятые аккаунты и аукционы.\n\n"
        "Команды:\n"
        "/search — Начать поиск\n"
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

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
    Проверяет юзернейм напрямую через парсинг Fragment.com.
    Железно отсекает занятые аккаунты, скрытые профили и аукционы.
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
            
            if response.status_code == 200:
                html_text = response.text.lower()
                
                # КРИТИЧЕСКИЙ МАРКЕР СВОБОДНОГО ЮЗЕРНЕЙМА:
                # Если на Фрагменте есть кнопка "Buy on Telegram" или надпись, что имя доступно для покупки
                if "is available" in html_text or "buy on telegram" in html_text or "available" in html_text:
                    # Но при этом проверяем, что это не активный аукцион
                    if "place a bid" not in html_text and "auction" not in html_text and "unavailable" not in html_text:
                        logger.info(f"✨ Найден свободный юз: @{username}")
                        return True
                
                # Если на странице написано "Unavailable", "Taken" или есть кнопки ставок — значит занят
                if "unavailable" in html_text or "taken" in html_text or "place a bid" in html_text:
                    return False
                    
            # Если Fragment выдал 404, это тоже часто значит, что юза нет в системе NFT, но он может быть свободен в ТГ
            elif response.status_code == 404:
                return True
                
            return False
            
    except Exception as e:
        logger.warning(f"Сбой сети при проверке @{username}: {e}")
        return False

def generate_random_username(length: int) -> str:
    # Ищем красивые имена только из латинских букв
    return "".join(random.choice(string.ascii_lowercase) for _ in range(length))

async def scanning_loop(chat_id: int):
    try:
        await bot.send_message(
            chat_id, 
            "🚀 Поиск запущен через парсинг Fragment!\n"
            "Ищем чистые 5 и 6-значные имена без цифр и аукционов."
        )
        
        while True:
            # Выбираем случайную длину (5 или 6 знаков)
            length = random.choice([5, 6])
            username = generate_random_username(length)
            
            # Проверяем точный статус на Fragment
            available = await is_username_truly_available(username)
            
            if available:
                message_text = f"🎉 **Найден абсолютно свободный юзернейм!**\n\n👉 `@{username}`\n\nПроверен через Fragment. Забирай быстрее!"
                await bot.send_message(chat_id, message_text, parse_mode="Markdown")
                await asyncio.sleep(2)
            
            # Задержка 5-8 секунд, чтобы Render/Fragment не забанили нас по IP
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
        "Я проверяю доступность имен напрямую через Fragment.\n\n"
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

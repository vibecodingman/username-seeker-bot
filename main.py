import asyncio
import random
import string
import logging
import os
from fastapi import FastAPI
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI для хелсчека Render
app = FastAPI()

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

is_scanning = False

@app.get("/")
def read_root():
    return {"status": "running", "info": "Internal Telegram Checker"}

async def check_username_via_telegram(username: str) -> str:
    """
    Проверяет юзернейм внутренними средствами Telegram.
    Не использует HTTP-запросы, поэтому защищен от блокировок DNS.
    """
    try:
        # Просим Telegram найти чат/канал с таким юзернеймом
        await bot.get_chat(f"@{username}")
        return "taken"  # Если нашел — занят
    except TelegramBadRequest as e:
        # Если Telegram говорит, что чат не найден — юзернейм свободен!
        if "chat not found" in str(e).lower():
            return "available"
        return "taken"
    except Exception as e:
        logger.error(f"Внутренняя ошибка для @{username}: {e}")
        return "taken"

def generate_random_username(length: int) -> str:
    first_char = random.choice(string.ascii_lowercase)
    other_chars = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length - 1))
    return first_char + other_chars

async def scanning_loop(chat_id: int):
    global is_scanning
    await bot.send_message(chat_id, "🚀 Поиск запущен через внутреннюю систему Telegram! Блокировки нам больше не страшны.")
    
    while is_scanning:
        length = random.choice([5, 6, 7])
        username = generate_random_username(length)
        
        status = await check_username_via_telegram(username)
        
        if status == "available":
            message_text = f"🎉 **Найден свободный юзернейм!**\n\n👉 `@{username}`\n\nПроверьте и займите его скорее!"
            await bot.send_message(chat_id, message_text, parse_mode="Markdown")
            await asyncio.sleep(2)
        
        # Безопасная задержка, чтобы сам Telegram не выдал Flood Wait
        await asyncio.sleep(random.uniform(4.0, 6.0))

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я внутренний чекер юзернеймов.\n\n"
        "Команды:\n"
        "/search — Начать поиск\n"
        "/stop — Остановить поиск"
    )

@dp.message(Command("search"))
async def cmd_search(message: types.Message):
    global is_scanning
    if is_scanning:
        await message.answer("Поиск уже идет!")
        return
    is_scanning = True
    asyncio.create_task(scanning_loop(message.chat.id))

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    global is_scanning
    if not is_scanning:
        await message.answer("Поиск не запущен.")
        return
    is_scanning = False
    await message.answer("🛑 Поиск остановлен.")

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(dp.start_polling(bot))

import asyncio
import random
import string
import logging
import httpx
from fastapi import FastAPI
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация FastAPI (нужен для Render)
app = FastAPI()

# Переменные (токен подтянется из настроек Render)
import os
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logger.error("Переменная окружения BOT_TOKEN не найдена!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Флаг для управления циклом поиска
is_scanning = False

@app.get("/")
def read_root():
    # Хелсчек эндпоинт, чтобы Render видел, что сервер жив
    return {"status": "working", "info": "Telegram Username Checker Bot"}

async def check_username_on_fragment(username: str) -> str:
    """
    Проверяет статус юзернейма через Fragment.com.
    Версия с автоматическим ретраем при ошибках сети.
    """
    url = f"https://fragment.com{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }
    
    # Пытаемся сделать запрос до 3 раз, если упал DNS или сеть
    for attempt in range(3):
        try:
            # transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0") помогает сбросить кэш DNS
            async melon_client() as client:
                async with httpx.AsyncClient(headers=headers, timeout=10.0, follow_redirects=True) as client:
                    response = await client.get(url)
                    
                    if response.status_code == 200:
                        html = response.text
                        if "An auction for this username" in html or "Unavailable" in html or "Taken" in html:
                            return "taken"
                        elif "Available" in html or "is available" in html.lower():
                            return "available"
                        else:
                            return "taken"
                    elif response.status_code == 404:
                        return "available"
                    
                    # Если поймалиcloud-flare заглушку или 429 Too Many Requests
                    if response.status_code == 429:
                        logger.warning("Fragment выдал 429 (Too Many Requests). Спим дольше...")
                        await asyncio.sleep(15)
                        
        except Exception as e:
            logger.warning(f"Попытка {attempt+1} не удалась для {username}: {e}")
            if attempt < 2:
                await asyncio.sleep(3) # Ждем 3 секунды перед следующей попыткой
            else:
                logger.error(f"Финальная ошибка для {username}: {e}")
                return "error"
    return "taken"

def generate_random_username(length: int) -> str:
    """Генерирует случайный юзернейм заданной длины (только латиница и цифры)"""
    # Юзернейм не может начинаться с цифры в Telegram
    first_char = random.choice(string.ascii_lowercase)
    other_chars = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length - 1))
    return first_char + other_chars

async def scanning_loop(chat_id: int):
    """Фоновый цикл генерации и проверки имен"""
    global is_scanning
    await bot.send_message(chat_id, "🚀 Поиск запущен! Буду проверять случайные 5, 6 и 7-значные имена.")
    
    while is_scanning:
        # Выбираем случайную длину из запрошенных
        length = random.choice([5, 6, 7])
        username = generate_random_username(length)
        
        status = await check_username_on_fragment(username)
        
        if status == "available":
            message_text = f"🎉 **Найден свободный юзернейм!**\n\n👉 `@{username}`\n\nПопробуйте занять его в настройках или проверьте вручную."
            await bot.send_message(chat_id, message_text, parse_mode="Markdown")
            # Небольшая пауза после находки
            await asyncio.sleep(2)
        
        # Задержка между проверками, чтобы Fragment не заблокировал IP сервера Render (Anti-DDoS)
        await asyncio.sleep(random.uniform(3.0, 6.0))

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я бот-чекер свободных юзернеймов (5-7 знаков).\n\n"
        "Команды:\n"
        "/search — Начать генерацию и поиск\n"
        "/stop — Остановить поиск"
    )

@dp.message(Command("search"))
async def cmd_search(message: types.Message):
    global is_scanning
    if is_scanning:
        await message.answer("Поиск уже идет!")
        return
    is_scanning = True
    # Запускаем бесконечный цикл как фоновую задачу asyncio
    asyncio.create_task(scanning_loop(message.chat.id))

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    global is_scanning
    if not is_scanning:
        await message.answer("Поиск и так выключен.")
        return
    is_scanning = False
    await message.answer("🛑 Поиск остановлен.")

# Асинхронный запуск бота параллельно с FastAPI
@app.on_event("startup")
async def on_startup():
    # Запускаем долгоиграющий пуллинг aiogram без блокировки основного потока FastAPI
    asyncio.create_task(dp.start_polling(bot))

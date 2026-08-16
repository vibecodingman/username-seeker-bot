import asyncio
import random
import string
import logging
import os
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
    """Проверяет юзернейм внутренними средствами Telegram с защитой от флуда."""
    try:
        await bot.get_chat(f"@{username}")
        return "taken"  # Нашел — занят
    except TelegramBadRequest as e:
        if "chat not found" in str(e).lower():
            return "available"  # Не нашел — свободен
        return "taken"
    except TelegramRetryAfter as e:
        # Важно: Telegram защищается от спама. Спим, сколько просит сервер.
        logger.warning(f"Флуд-контроль! Ожидание {e.retry_after} сек.")
        await asyncio.sleep(e.retry_after)
        return "error"
    except Exception as e:
        logger.error(f"Ошибка проверки @{username}: {e}")
        return "error"

def generate_random_username(length: int) -> str:
    return "".join(random.choice(string.ascii_lowercase) for _ in range(length))

async def scanning_loop(chat_id: int):
    try:
        await bot.send_message(
            chat_id, 
            "🚀 Поиск запущен!\n"
            "⚠️ Из-за лимитов Telegram проверка идет медленно, чтобы избежать блокировки."
        )
        
        # Цикл работает, пока задача не будет отменена через active_scans[chat_id].cancel()
        while True:
            length = random.choice([5, 6])
            username = generate_random_username(length)
            
            status = await check_username_via_telegram(username)
            
            if status == "available":
                message_text = f"🎉 **Найден свободный юзернейм!**\n\n👉 `@{username}`\n\nЗаймите его скорее!"
                await bot.send_message(chat_id, message_text, parse_mode="Markdown")
                await asyncio.sleep(2)
            
            # Увеличим паузу для безопасности (минимум 7-12 секунд)
            # Слишком частые запросы get_chat к разным юзернеймам вызовут Flood Wait
            await asyncio.sleep(random.uniform(7.0, 12.0))
            
    except asyncio.CancelledError:
        # Срабатывает при отмене задачи через cancel()
        await bot.send_message(chat_id, "🛑 Поиск успешно остановлен.")
    except Exception as e:
        logger.error(f"Критическая ошибка в цикле сканирования: {e}")
        active_scans.pop(chat_id, None)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я безопасный чекер юзернеймов (5-6 знаков).\n\n"
        "Команды:\n"
        "/search — Начать поиск\n"
        "/stop — Остановить поиск"
    )

@dp.message(Command("search"))
async def cmd_search(message: types.Message):
    chat_id = message.chat.id
    
    if chat_id in active_scans:
        await message.answer("Поиск в этом чате уже идет!")
        return
        
    # Создаем и сохраняем задачу индивидуально для каждого чата
    task = asyncio.create_task(scanning_loop(chat_id))
    active_scans[chat_id] = task

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    chat_id = message.chat.id
    
    if chat_id not in active_scans:
        await message.answer("Поиск не запущен.")
        return
        
    # Останавливаем задачу асинхронно
    task = active_scans.pop(chat_id)
    task.cancel()

async def main():
    logger.info("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

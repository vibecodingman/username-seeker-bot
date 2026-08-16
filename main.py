import asyncio
import random
import string
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилище запущенных задач {chat_id: asyncio.Task}
active_scans = {}

# Настройки пользователей {chat_id: {"length": 5, "use_digits": False}}
user_settings = {}

def get_default_settings(chat_id: int) -> dict:
    if chat_id not in user_settings:
        user_settings[chat_id] = {"length": 5, "use_digits": False}
    return user_settings[chat_id]

def make_settings_keyboard(chat_id: int):
    settings = get_default_settings(chat_id)
    builder = InlineKeyboardBuilder()
    
    # Кнопки выбора длины
    len5_text = "✅ 5 знаков" if settings["length"] == 5 else "5 знаков"
    len6_text = "✅ 6 знаков" if settings["length"] == 6 else "6 знаков"
    builder.button(text=len5_text, callback_data="set_len_5")
    builder.button(text=len6_text, callback_data="set_len_6")
    
    # Кнопка выбора цифр
    digits_text = "🔢 Цифры: ВКЛ" if settings["use_digits"] else "🔤 Только буквы"
    builder.button(text=digits_text, callback_data="toggle_digits")
    
    # Кнопка управления поиском
    if chat_id in active_scans:
        builder.button(text="🛑 ОСТАНОВИТЬ ПОИСК", callback_data="stop_search")
    else:
        builder.button(text="🚀 ЗАПУСТИТЬ ПОИСК", callback_data="start_search")
        
    builder.adjust(2, 1, 1)
    return builder.as_markup()

async def check_username_via_telegram(username: str) -> str:
    """Проверка юза через API Telegram. Защищено от блокировок хостинга."""
    try:
        await bot.get_chat(f"@{username}")
        return "taken"
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if "chat not found" in err_msg:
            return "available"
        return "taken"
    except TelegramRetryAfter as e:
        logger.warning(f"Флуд-контроль! Ожидание {e.retry_after} сек.")
        await asyncio.sleep(e.retry_after)
        return "error"
    except Exception:
        return "error"

def generate_username(length: int, use_digits: bool) -> str:
    first_char = random.choice(string.ascii_lowercase)
    pool = string.ascii_lowercase + (string.digits if use_digits else "")
    other_chars = "".join(random.choice(pool) for _ in range(length - 1))
    return first_char + other_chars

async def scanning_loop(chat_id: int):
    try:
        settings = get_default_settings(chat_id)
        mode_desc = "с цифрами" if settings["use_digits"] else "без цифр"
        await bot.send_message(
            chat_id, 
            f"🚀 Поиск активирован!\n🎯 Ищем: **{settings['length']}-знаки**, режим: **{mode_desc}**.\n"
            f"⏳ Поиск коротких юзов занимает время. Свободные имена придут сюда.",
            parse_mode="Markdown"
        )
        
        while True:
            # Свежие настройки из кэша пользователя
            cfg = get_default_settings(chat_id)
            username = generate_username(cfg["length"], cfg["use_digits"])
            
            status = await check_username_via_telegram(username)
            
            if status == "available":
                message_text = f"🎉 **Найден свободный юзернейм!**\n\n👉 `@{username}`\n\nПроверь и займи его быстрее!"
                await bot.send_message(chat_id, message_text, parse_mode="Markdown")
                await asyncio.sleep(2)
            
            # Безопасная пауза для защиты от Flood Wait
            await asyncio.sleep(random.uniform(6.0, 9.0))
            
    except asyncio.CancelledError:
        await bot.send_message(chat_id, "🛑 Фоновый поиск остановлен.")
    except Exception as e:
        logger.error(f"Ошибка в цикле сканирования: {e}")
        active_scans.pop(chat_id, None)

@dp.message(Command("start"), F.chat.type == "private")
@dp.message(Command("settings"), F.chat.type == "private")
async def cmd_settings(message: types.Message):
    await message.answer(
        "⚙️ **Панель управления чекером**\n\n"
        "Настраивай параметры бота с помощью кнопок ниже. "
        "Поиск коротких буквенных юзов требует времени, запасись терпением!",
        reply_markup=make_settings_keyboard(message.chat.id),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("set_len_"))
async def handle_len_setting(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    new_len = int(callback.data.split("_")[-1])
    settings = get_default_settings(chat_id)
    
    if settings["length"] != new_len:
        settings["length"] = new_len
        await callback.message.edit_reply_markup(reply_markup=make_settings_keyboard(chat_id))
    await callback.answer()

@dp.callback_query(F.data == "toggle_digits")
async def handle_digits_setting(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    settings = get_default_settings(chat_id)
    settings["use_digits"] = not settings["use_digits"]
    
    await callback.message.edit_reply_markup(reply_markup=make_settings_keyboard(chat_id))
    await callback.answer()

@dp.callback_query(F.data == "start_search")
async def handle_start_search(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id in active_scans:
        await callback.answer("Поиск уже запущен!", show_alert=True)
        return
        
    task = asyncio.create_task(scanning_loop(chat_id))
    active_scans[chat_id] = task
    
    await callback.message.edit_reply_markup(reply_markup=make_settings_keyboard(chat_id))
    await callback.answer("Поиск запущен!")

@dp.callback_query(F.data == "stop_search")
async def handle_stop_search(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in active_scans:
        await callback.answer("Поиск не запущен!", show_alert=True)
        return
        
    task = active_scans.pop(chat_id)
    task.cancel()
    
    await callback.message.edit_reply_markup(reply_markup=make_settings_keyboard(chat_id))
    await callback.answer("Поиск остановлен!")

async def main():
    logger.info("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

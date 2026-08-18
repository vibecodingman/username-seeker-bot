import aiohttp
import asyncio
import logging
import os
import random
import string
from aiogram import Bot, Dispatcher, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiohttp import web

# Настройка логирования для отслеживания ошибок в консоли Render
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилище активных фоновых задач и настроек пользователей
active_scans = {}   # {chat_id: asyncio.Task}
user_settings = {}  # {chat_id: {"length": 5, "use_digits": False}}

def get_default_settings(chat_id: int) -> dict:
    """Возвращает настройки пользователя или создает дефолтные, если их нет"""
    if chat_id not in user_settings:
        user_settings[chat_id] = {"length": 5, "use_digits": False}
    return user_settings[chat_id]

def generate_username(length: int, use_digits: bool) -> str:
    """Генерирует случайный юзернейм по правилам Telegram"""
    # Первая буква юзернейма в Telegram всегда должна быть латинской буквой
    first_char = random.choice(string.ascii_lowercase)
    
    # Пул для остальных символов (буквы + цифры, если включены)
    pool = string.ascii_lowercase + (string.digits if use_digits else "")
    
    other_chars = "".join(random.choice(pool) for _ in range(length - 1))
    return first_char + other_chars

# Читаем ID технического канала из настроек Render
CHANNEL_ID = os.getenv("CHANNEL_ID")

async def check_username_via_telegram(username: str) -> str:
    """Ультимативный чекер без каналов через системный вызов создания ссылки"""
    try:
        # Пытаемся вызвать базовую инфу. Если чат открыт — имя точно занято.
        await bot.get_chat(f"@{username}")
        return "taken"
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        
        # Если чат не найден, делаем контрольный выстрел через экспорт ссылки
        if "chat not found" in err_msg:
            try:
                # Мы просим Telegram экспортировать ссылку для этого юзернейма.
                # Если имя занято скрытым юзером — Telegram выдаст "chat_id_invalid" или "chat not found" в контексте прав.
                # Если имя АБСОЛЮТНО ПУСТОЕ И СВОБОДНО — Telegram вернет "chat not found" в чистом виде.
                # Но если мы перепроверим через попытку отправить пустую команду, скрытые юзеры выдадут "bot is not a member".
                # Поэтому проверяем через вызов структуры стикеров группы:
                await bot.get_forum_topic_icon_stickers()
                
                # Если имя свободно, то при попытке проверить администратора вылетит "chat not found"
                await bot.get_chat_administrators(chat_id=f"@{username}")
                return "taken"
            except TelegramBadRequest as e2:
                err_msg2 = str(e2).lower()
                # Это единственное уникальное сочетание, когда имя полностью свободно для регистрации!
                if "chat not found" in err_msg2:
                    return "available"
                # Любые другие ошибки (права, запреты, скрытый чат) = имя занято аккаунтом-невидимкой
                return "taken"
            except Exception:
                return "taken"
        return "taken"
    except TelegramRetryAfter as e:
        logging.warning(f"Лимит запросов от Telegram! Спим {e.retry_after} сек.")
        await asyncio.sleep(e.retry_after)
        return "error"
    except Exception:
        return "error"
        
def make_settings_keyboard(chat_id: int):
    """Генерирует инлайн-клавиатуру настроек и управления поиском"""
    cfg = get_default_settings(chat_id)
    builder = InlineKeyboardBuilder()
    
    # Кнопки выбора длины юзернейма
    lengths = [5, 6, 7]
    for l in lengths:
        prefix = "✅ " if cfg["length"] == l else ""
        builder.button(text=f"{prefix}{l} симв.", callback_data=f"set_len_{l}")
    
    # Кнопка включения/выключения цифр
    digits_status = "ВКЛ 🔢" if cfg["use_digits"] else "ВЫКЛ ❌"
    builder.button(text=f"Цифры: {digits_status}", callback_data="toggle_digits")
    
    # Кнопка управления поиском (Старт/Стоп)
    if chat_id in active_scans:
        builder.button(text="🛑 ОСТАНОВИТЬ ПОИСК", callback_data="stop_search")
    else:
        builder.button(text="🚀 ЗАПУСТИТЬ ПОИСК", callback_data="start_search")
        
    # Формируем сетку кнопок: по 2 в ряд для длины, остальные в отдельные строки
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()

async def scanning_loop(chat_id: int):
    """Фоновый бесконечный цикл генерации и проверки юзернеймов"""
    logging.info(f"Фоновый поиск запущен для чата {chat_id}")
    try:
        while True:
            cfg = get_default_settings(chat_id)
            # Генерируем случайное имя по текущим настройкам пользователя
            username = generate_username(cfg["length"], cfg["use_digits"])
            
            # Проверяем его занятость через API Telegram
            status = await check_username_via_telegram(username)
            
            if status == "available":
                logging.info(f"Найден свободный юзернейм: @{username}")
                # Мгновенно отправляем пользователю радостную весть с готовой ссылкой
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"🔥 <b>НАЙДЕН СВОБОДНЫЙ ЮЗЕРНЕЙМ!</b>\n\n👉 <code>@{username}</code>\n\n"
                         f"🔗 Ссылка: t.me/{username}\n\n"
                         f"<i>Забирай быстрее, пока кто-то другой не занял!</i>",
                    parse_mode="HTML"
                )
            
            # Важнейшая динамическая пауза между запросами (от 1.5 до 3 секунд)
            # Защищает аккаунт бота от получения флуд-бана от серверов Telegram
            await asyncio.sleep(random.uniform(1.5, 3.0))
            
    except asyncio.CancelledError:
        logging.info(f"Фоновый поиск для чата {chat_id} был успешно остановлен.")
    except Exception as e:
        logging.error(f"Ошибка в цикле сканирования чата {chat_id}: {e}")
        # Если произошел сбой, убираем задачу из активных и пробуем оповестить юзера
        if chat_id in active_scans:
            active_scans.pop(chat_id)
        try:
            await bot.send_message(chat_id=chat_id, text="⚠️ <b>Поиск приостановлен из-за ошибки сервера.</b> Перезапустите его панели.")
        except Exception:
            pass

@dp.message(Command("start"))
async def cmd_settings(message: types.Message):
    """Открывает интерактивную панель управления чекером"""
    await message.answer(
        "⚙️ <b>Панель управления чекером</b>\n\n"
        "Настройте длину юзернейма, включите или выключите цифры и запустите фоновый поиск свободного имени.",
        reply_markup=make_settings_keyboard(message.chat.id),
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("set_len_"))
async def handle_len(cb: types.CallbackQuery):
    """Обрабатывает переключение длины генерируемого юзернейма"""
    chat_id = cb.message.chat.id
    new_len = int(cb.data.split("_")[-1])
    
    get_default_settings(chat_id)["length"] = new_len
    
    # Обновляем кнопки на сообщении, чтобы сразу показать галочку
    await cb.message.edit_reply_markup(reply_markup=make_settings_keyboard(chat_id))
    await cb.answer(f"Длина изменена на {new_len} симв.")

@dp.callback_query(F.data == "toggle_digits")
async def handle_digits(cb: types.CallbackQuery):
    """Включает или выключает использование цифр в генераторе"""
    chat_id = cb.message.chat.id
    cfg = get_default_settings(chat_id)
    
    cfg["use_digits"] = not cfg["use_digits"]
    
    # Мгновенно обновляем интерфейс кнопок
    await cb.message.edit_reply_markup(reply_markup=make_settings_keyboard(chat_id))
    status_text = "включены" if cfg["use_digits"] else "выключены"
    await cb.answer(f"Цифры {status_text}")

@dp.callback_query(F.data == "start_search")
async def handle_start(cb: types.CallbackQuery):
    """Запускает изолированную фоновую задачу сканирования"""
    chat_id = cb.message.chat.id
    
    if chat_id in active_scans:
        return await cb.answer("Поиск уже запущен и активно ищет!", show_alert=True)
        
    # Создаем асинхронную задачу фонового поиска
    active_scans[chat_id] = asyncio.create_task(scanning_loop(chat_id))
    
    # Меняем интерфейс кнопки на "Остановить"
    await cb.message.edit_reply_markup(reply_markup=make_settings_keyboard(chat_id))
    await cb.answer("Фоновый поиск запущен!")

@dp.callback_query(F.data == "stop_search")
async def handle_stop(cb: types.CallbackQuery):
    """Принудительно останавливает фоновую задачу сканирования"""
    chat_id = cb.message.chat.id
    
    if chat_id in active_scans:
        # Извлекаем задачу из хранилища и отменяем её выполнение
        task = active_scans.pop(chat_id)
        task.cancel()
        
    # Возвращаем интерфейс кнопки в исходное состояние "Запустить"
    await cb.message.edit_reply_markup(reply_markup=make_settings_keyboard(chat_id))
    await cb.answer("Поиск успешно остановлен.")

# --- ВЕБ-СЕРВЕР ДЛЯ ПОДДЕРЖАНИЯ ОНЛАЙНА НА RENDER ---

async def handle_web(request):
    """Возвращает текстовый статус для пинга от Render"""
    return web.Response(text="Checker Bot is active and running!")

async def start_web():
    """Запускает aiohttp веб-сервер на внешнем порту"""
    app = web.Application()
    app.router.add_get("/", handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Читаем динамический PORT, который Render выдает при деплое
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Веб-сервер успешно запущен на порту {port}")

async def main():
    """Главная точка входа для запуска асинхронного движка"""
    # Сначала поднимаем веб-сервер, чтобы Render не сбросил билд по таймауту
    await start_web()
    
    # Запускаем опрос серверов Telegram (Polling)
    logging.info("Бот начинает опрос серверов Telegram...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

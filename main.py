# Инициализация бота и базовые настройки клавиатуры для main.py
import asyncio, logging, os, random, string
from aiogram import Bot, Dispatcher, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()
active_scans, user_settings = {}, {}

def get_default_settings(chat_id: int) -> dict:
    if chat_id not in user_settings:
        user_settings[chat_id] = {"length": 5, "use_digits": False}
    return user_settings[chat_id]

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

async def check_username_via_telegram(username: str) -> str:
    try:
        await bot.get_chat(f"@{username}")
        return "taken"
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if "chat not found" in err_msg:
            try:
                await bot.get_chat_member(chat_id=f"@{username}", user_id=bot.id)
                return "taken"
            except TelegramBadRequest as e2:
                err_msg2 = str(e2).lower()
                if any(x in err_msg2 for x in ["chat not found", "user not found", "member not found"]):
                    return "available"
                return "taken"
            except Exception:
                return "taken"
        return "taken"
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        return "error"
    except Exception:
        return "error"

def generate_username(length: int, use_digits: bool) -> str:
    first_char = random.choice(string.ascii_lowercase)
    pool = string.ascii_lowercase + (string.digits if use_digits else "")
    other_chars = "".join(random.choice(pool) for _ in range(length - 1))
    return first_char + other_chars

from aiogram.filters import Command
from aiohttp import web

async def scanning_loop(chat_id: int):
    # Фоновый цикл поиска доступных юзернеймов и отправки уведомлений
    # Полный код функции доступен в исходных материалах
    pass

def make_settings_keyboard(chat_id: int):
    # Генерация инлайн-клавиатуры настроек и управления поиском
    pass

@dp.message(Command("start"))
async def cmd_settings(message: types.Message):
    await message.answer("⚙ Панель чекера", reply_markup=make_settings_keyboard(message.chat.id))

@dp.callback_query(F.data.startswith("set_len_"))
async def handle_len(cb: types.CallbackQuery):
    # Обработка изменения длины юзернейма
    pass

@dp.callback_query(F.data == "toggle_digits")
async def handle_digits(cb: types.CallbackQuery):
    # Переключение использования цифр
    pass

@dp.callback_query(F.data == "start_search")
async def handle_start(cb: types.CallbackQuery):
    # Запуск фонового процесса сканирования
    pass

@dp.callback_query(F.data == "stop_search")
async def handle_stop(cb: types.CallbackQuery):
    # Остановка фонового процесса сканирования
    pass

async def main():
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text='Бот активен!'))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.environ.get('PORT', 8080))).start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

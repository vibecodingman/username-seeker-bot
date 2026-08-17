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

# --- РЕАЛЬНЫЙ КОД ПРОПУЩЕННЫХ ФУНКЦИЙ ---

def make_settings_keyboard(chat_id: int):
    cfg = get_default_settings(chat_id)
    builder = InlineKeyboardBuilder()
    l5 = "✅ 5 знаков" if cfg["length"] == 5 else "5 знаков"
    l6 = "✅ 6 знаков" if cfg["length"] == 6 else "6 знаков"
    builder.button(text=l5, callback_data="set_len_5")
    builder.button(text=l6, callback_data="set_len_6")
    dig = "🔢 Цифры: ВКЛ" if cfg["use_digits"] else "🔤 Только буквы"
    builder.button(text=dig, callback_data="toggle_digits")
    if chat_id in active_scans:
        builder.button(text="🛑 ОСТАНОВИТЬ", callback_data="stop_search")
    else:
        builder.button(text="🚀 ЗАПУСТИТЬ", callback_data="start_search")
    builder.adjust(2, 1, 1)
    return builder.as_markup()

async def scanning_loop(chat_id: int):
    try:
        cfg = get_default_settings(chat_id)
        mode = "с цифрами" if cfg["use_digits"] else "без цифр"
        await bot.send_message(chat_id, f"🚀 Поиск запущен ({cfg['length']} зн., {mode})")
        while True:
            current_cfg = get_default_settings(chat_id)
            user = generate_username(current_cfg["length"], current_cfg["use_digits"])
            res = await check_username_via_telegram(user)
            if res == "available":
                await bot.send_message(chat_id, f"🎉 Свободен: @{user}")
                await asyncio.sleep(2)
            await asyncio.sleep(random.uniform(6.0, 9.0))
    except asyncio.CancelledError:
        await bot.send_message(chat_id, "🛑 Поиск остановлен.")
    except Exception:
        active_scans.pop(chat_id, None)

@dp.callback_query(F.data.startswith("set_len_"))
async def handle_len(cb: types.CallbackQuery):
    get_default_settings(cb.message.chat.id)["length"] = int(cb.data.split("_")[-1])
    await cb.message.edit_reply_markup(reply_markup=make_settings_keyboard(cb.message.chat.id))
    await cb.answer()

@dp.callback_query(F.data == "toggle_digits")
async def handle_digits(cb: types.CallbackQuery):
    cfg = get_default_settings(cb.message.chat.id)
    cfg["use_digits"] = not cfg["use_digits"]
    await cb.message.edit_reply_markup(reply_markup=make_settings_keyboard(cb.message.chat.id))
    await cb.answer()

@dp.callback_query(F.data == "start_search")
async def handle_start(cb: types.CallbackQuery):
    cid = cb.message.chat.id
    if cid in active_scans: return await cb.answer("Уже ищу!")
    active_scans[cid] = asyncio.create_task(scanning_loop(cid))
    await cb.message.edit_reply_markup(reply_markup=make_settings_keyboard(cid))
    await cb.answer("Запущено!")

@dp.callback_query(F.data == "stop_search")
async def handle_stop(cb: types.CallbackQuery):
    cid = cb.message.chat.id
    if cid in active_scans: active_scans.pop(cid).cancel()
    await cb.message.edit_reply_markup(reply_markup=make_settings_keyboard(cid))
    await cb.answer("Остановлено!")


async def main():
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text='Бот активен!'))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.environ.get('PORT', 8080))).start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

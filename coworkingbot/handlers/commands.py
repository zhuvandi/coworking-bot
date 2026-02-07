
from aiogram import types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from coworkingbot.config import ADMIN_IDS
from coworkingbot.utils.gas import call_google_script

from coworkingbot.utils.helpers import (
    is_admin,
    is_past_booking
)

from coworkingbot.keyboards.main import main_menu_keyboard
from coworkingbot.bot import bot


async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Добро пожаловать в бот бронирования коворкинга!\n"
        "Минимальное время аренды - 1 час. Слоты по 2 часа.\n\n"
        "Выберите действие:",
        reply_markup=main_menu_keyboard()
    )


async def cmd_help(message: types.Message):
    await message.answer(
        "🤖 <b>Бот для бронирования коворкинга</b>\n\n"
        "• /start — начало работы\n"
        "• /my_bookings — мои брони\n"
        "• /today — брони на сегодня\n"
        "• /reviews — отзывы\n",
        parse_mode="HTML"
    )


async def cmd_myid(message: types.Message):
    await message.answer(
        f"👤 Ваш ID: <code>{message.from_user.id}</code>",
        parse_mode="HTML"
    )


from aiogram import types
from aiogram.fsm.context import FSMContext

from coworkingbot.keyboards.main import main_menu_keyboard


async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Добро пожаловать в бот бронирования коворкинга!\n"
        "Слоты по 2 часа.\n\n"
        "Выберите действие:",
        reply_markup=main_menu_keyboard(),
    )


async def cmd_help(message: types.Message):
    await message.answer(
        "🤖 <b>Бот для бронирования коворкинга</b>\n\n"
        "• /start — главное меню\n"
        "• /my_bookings — мои брони\n"
        "• /help — справка\n",
        parse_mode="HTML",
    )


async def cmd_myid(message: types.Message):
    await message.answer(f"👤 Ваш ID: <code>{message.from_user.id}</code>", parse_mode="HTML")

from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from coworkingbot.keyboards.main import main_menu_keyboard

router = Router()


async def send_main_menu(message: types.Message, state: FSMContext | None = None) -> None:
    if state is not None:
        await state.clear()
    await message.answer(
        "👋 Добро пожаловать в бот бронирования коворкинга!\n"
        "Слоты по 2 часа.\n\n"
        "Выберите действие:",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext) -> None:
    await send_main_menu(message, state)


@router.callback_query(F.data == "main_menu")
async def handle_main_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    await send_main_menu(callback.message, state)
    await callback.answer()


@router.message(F.text == "🏠 В меню")
async def handle_menu_button(message: types.Message, state: FSMContext) -> None:
    await send_main_menu(message, state)

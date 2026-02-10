from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from coworkingbot.app.context import AppContext
from coworkingbot.keyboards.main import main_menu_keyboard
from coworkingbot.services.content_store import get_client_content

router = Router()


async def send_main_menu(
    message: types.Message, ctx: AppContext, state: FSMContext | None = None
) -> None:
    if state is not None:
        await state.clear()
    content = await get_client_content(ctx)
    text = content.welcome
    if content.announcement.strip():
        text = f"{text}\n\n📢 {content.announcement.strip()}"

    await message.answer(
        text,
        reply_markup=main_menu_keyboard(content.booking_button_label),
    )


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext, ctx: AppContext) -> None:
    await send_main_menu(message, ctx, state)


@router.callback_query(F.data == "main_menu")
async def handle_main_menu(
    callback: types.CallbackQuery, state: FSMContext, ctx: AppContext
) -> None:
    await send_main_menu(callback.message, ctx, state)
    await callback.answer()


@router.message(F.text == "🏠 В меню")
async def handle_menu_button(message: types.Message, state: FSMContext, ctx: AppContext) -> None:
    await send_main_menu(message, ctx, state)

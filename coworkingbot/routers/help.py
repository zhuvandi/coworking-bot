from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from coworkingbot.app.context import AppContext
from coworkingbot.services.content_store import get_client_content
from coworkingbot.services.texts import user_help_text

router = Router()


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    await message.answer(user_help_text(), parse_mode="HTML")


@router.message(F.text == "❓ Помощь и инструкции")
async def handle_help_button(message: types.Message) -> None:
    await cmd_help(message)


@router.message(F.text == "📄 Условия")
async def handle_rules(message: types.Message, ctx: AppContext) -> None:
    content = await get_client_content(ctx)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛟 Поддержка")],
            [KeyboardButton(text="🏠 В меню")],
        ],
        resize_keyboard=True,
        selective=True,
    )
    await message.answer(content.rules, parse_mode="HTML", reply_markup=keyboard)


@router.message(F.text == "🛟 Поддержка")
async def handle_support(message: types.Message, ctx: AppContext) -> None:
    content = await get_client_content(ctx)
    await message.answer(content.support, parse_mode="HTML")

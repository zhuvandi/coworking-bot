from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command

from coworkingbot.services.texts import rules_text, support_text, user_help_text

router = Router()


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    await message.answer(user_help_text(), parse_mode="HTML")


@router.message(F.text == "❓ Помощь и инструкции")
async def handle_help_button(message: types.Message) -> None:
    await cmd_help(message)


@router.message(F.text == "ℹ️ Правила")
async def handle_rules(message: types.Message) -> None:
    await message.answer(rules_text(), parse_mode="HTML")


@router.message(F.text == "🛟 Поддержка")
async def handle_support(message: types.Message) -> None:
    await message.answer(support_text(), parse_mode="HTML")

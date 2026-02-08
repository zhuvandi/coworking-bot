from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from coworkingbot.app.context import AppContext
from coworkingbot.services.errors import send_user_error

logger = logging.getLogger(__name__)

router = Router()


@router.message()
async def unknown_message(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state:
        await message.answer(
            "Пожалуйста, завершите текущее действие или нажмите «🏠 В меню»."
        )
    else:
        await message.answer(
            "Я не понимаю эту команду. Используйте /start для начала работы.\n"
            "Или /help для получения справки."
        )


@router.errors()
async def handle_errors(event: types.ErrorEvent, ctx: AppContext) -> bool:
    logger.exception("Unhandled error in update", exc_info=event.exception)
    message = None
    if event.update:
        if event.update.message:
            message = event.update.message
        elif event.update.callback_query and event.update.callback_query.message:
            message = event.update.callback_query.message

    if message:
        await send_user_error(
            message,
            ctx,
            "⚠️ Произошла ошибка. Мы уже разбираемся.",
            str(event.exception),
            "Unhandled update error",
        )
    return True

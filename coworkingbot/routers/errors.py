from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from coworkingbot.app.context import AppContext
from coworkingbot.services.notifications import notify_admin_about_error

logger = logging.getLogger(__name__)

router = Router()


@router.message()
async def unknown_message(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state:
        await message.answer(
            "Пожалуйста, завершите текущее действие или используйте команду /start"
        )
    else:
        await message.answer(
            "Я не понимаю эту команду. Используйте /start для начала работы.\n"
            "Или /help для получения справки."
        )


@router.errors()
async def handle_errors(event: types.ErrorEvent, ctx: AppContext) -> bool:
    logger.exception("Unhandled error in update", exc_info=event.exception)
    await notify_admin_about_error(ctx, str(event.exception), "Unhandled update error")
    return True

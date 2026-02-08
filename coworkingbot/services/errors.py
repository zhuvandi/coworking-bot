from __future__ import annotations

import logging

from aiogram import types

from coworkingbot.app.context import AppContext
from coworkingbot.services.common import is_admin
from coworkingbot.services.notifications import notify_admin_about_error

logger = logging.getLogger(__name__)


async def send_user_error(
    message: types.Message,
    ctx: AppContext,
    short_text: str,
    detail: str,
    context: str = "",
) -> None:
    if is_admin(ctx, message.from_user.id):
        await message.answer(f"{short_text}\n\n{detail}", parse_mode="HTML")
        return

    await message.answer(short_text, parse_mode="HTML")
    try:
        await notify_admin_about_error(ctx, detail, context or "user_error")
    except Exception as exc:
        logger.error("Failed to notify admin about error: %s", exc)

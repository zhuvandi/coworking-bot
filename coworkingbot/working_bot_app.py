from __future__ import annotations

import asyncio
import logging
import sys

import pytz
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from coworkingbot.app.context import (
    AppContext,
    load_settings,
    log_missing_settings,
    validate_settings,
)
from coworkingbot.app.middleware import ContextMiddleware
from coworkingbot.routers import admin, booking, errors, help, start
from coworkingbot.services.gas import GasClient

logger = logging.getLogger(__name__)


def create_app() -> tuple[Bot, Dispatcher, AppContext]:
    settings = load_settings()
    missing = validate_settings(settings)
    if missing:
        log_missing_settings(missing)
        raise RuntimeError("Missing required settings")

    bot = Bot(token=settings.bot_token)
    tz = pytz.timezone(settings.tz_name)
    gas_client = GasClient(settings.gas_webapp_url, settings.api_token)
    ctx = AppContext(settings=settings, bot=bot, tz=tz, gas=gas_client)

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.update.middleware(ContextMiddleware(ctx))

    dp.include_router(start.router)
    dp.include_router(help.router)
    dp.include_router(booking.router)
    dp.include_router(admin.router)
    dp.include_router(errors.router)

    return bot, dp, ctx


async def run_polling(bot: Bot, dp: Dispatcher) -> None:
    logger.info("Запуск бота...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def run() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    try:
        bot, dp, _ctx = create_app()
    except RuntimeError:
        sys.exit(1)

    try:
        asyncio.run(run_polling(bot, dp))
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    finally:
        pass

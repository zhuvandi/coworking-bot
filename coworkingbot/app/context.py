from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytz
from aiogram import Bot

if TYPE_CHECKING:
    from coworkingbot.services.gas import GasClient


ENV_FILE_HINT = "/etc/default/coworking-bot"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    gas_webapp_url: str
    api_token: str
    admin_ids: tuple[int, ...]
    tz_name: str


@dataclass(frozen=True)
class AppContext:
    settings: Settings
    bot: Bot
    tz: pytz.tzinfo.BaseTzInfo
    gas: GasClient


def _parse_admin_ids(raw: str | None) -> tuple[int, ...]:
    if not raw:
        return ()
    ids: list[int] = []
    for chunk in raw.replace(";", ",").split(","):
        value = chunk.strip()
        if not value:
            continue
        try:
            ids.append(int(value))
        except ValueError:
            logger.warning("Invalid admin id %s (skipped)", value)
    return tuple(ids)


def load_settings() -> Settings:
    return Settings(
        bot_token=os.environ.get("BOT_TOKEN", "").strip(),
        gas_webapp_url=os.environ.get("GAS_WEBAPP_URL", "").strip(),
        api_token=os.environ.get("API_TOKEN", "").strip(),
        admin_ids=_parse_admin_ids(os.environ.get("ADMIN_IDS")),
        tz_name=os.environ.get("TZ", "Europe/Moscow").strip(),
    )


def validate_settings(settings: Settings) -> Sequence[str]:
    missing: list[str] = []
    if not settings.bot_token:
        missing.append("BOT_TOKEN")
    elif ":" not in settings.bot_token or len(settings.bot_token) <= 10:
        missing.append("BOT_TOKEN (invalid)")
    if not settings.gas_webapp_url:
        missing.append("GAS_WEBAPP_URL")
    if not settings.api_token:
        missing.append("API_TOKEN")
    if not settings.admin_ids:
        missing.append("ADMIN_IDS")
    return missing


def log_missing_settings(missing: Sequence[str]) -> None:
    missing_list = ", ".join(missing)
    logger.error(
        "Missing required settings: %s. Set them in %s (systemd EnvironmentFile).",
        missing_list,
        ENV_FILE_HINT,
    )

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from coworkingbot.app.context import AppContext
from coworkingbot.services.texts import default_welcome_text, rules_text, support_text

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60
DEFAULT_CONTENT_PATH = "/var/lib/coworkingbot/content.json"
ALLOWED_FIELDS = {
    "welcome",
    "rules",
    "support",
    "announcement",
    "booking_button_label",
    "booking_success",
    "booking_cancel_reschedule",
}


@dataclass(frozen=True)
class ClientContent:
    welcome: str
    rules: str
    support: str
    announcement: str = ""
    booking_button_label: str = "📅 Забронировать"
    booking_success: str = (
        "Готово ✅\nБронь создана.\n\n"
        "📅 {date}\n🕐 {time}\n👤 {name}\n📞 {phone}\n\n"
        "📋 ID брони: <code>{record_id}</code>\n\n"
        "Дальше вы можете посмотреть детали в «Мои брони»."
    )
    booking_cancel_reschedule: str = (
        "✅ Бронь отменена.\nВы можете выбрать новую дату или остаться в меню."
    )


_cache: dict[str, tuple[float, ClientContent]] = {}


def _default_content() -> ClientContent:
    return ClientContent(
        welcome=default_welcome_text(),
        rules=rules_text(),
        support=support_text(),
        announcement="",
    )


def _content_path(ctx: AppContext) -> Path:
    configured = os.environ.get("CONTENT_STORE_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path(DEFAULT_CONTENT_PATH)


def _read_raw(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
            if isinstance(payload, dict):
                return payload
    except Exception as exc:
        logger.error("Failed to read content store %s: %s", path, exc)
    return {}


def _write_raw(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def _build_content(raw: dict) -> ClientContent:
    defaults = _default_content()
    # UX note: we keep non-empty fallbacks in code, so accidental admin cleanup
    # never leaves clients with blank buttons/system texts.
    return ClientContent(
        welcome=str(raw.get("welcome") or defaults.welcome),
        rules=str(raw.get("rules") or defaults.rules),
        support=str(raw.get("support") or defaults.support),
        announcement=str(raw.get("announcement") or ""),
        booking_button_label=str(raw.get("booking_button_label") or defaults.booking_button_label),
        booking_success=str(raw.get("booking_success") or defaults.booking_success),
        booking_cancel_reschedule=str(
            raw.get("booking_cancel_reschedule") or defaults.booking_cancel_reschedule
        ),
    )


def _cache_get(path: Path) -> ClientContent | None:
    cached = _cache.get(str(path))
    if not cached:
        return None
    ts, content = cached
    if (time.monotonic() - ts) > CACHE_TTL_SECONDS:
        _cache.pop(str(path), None)
        return None
    return content


def _cache_put(path: Path, content: ClientContent) -> None:
    _cache[str(path)] = (time.monotonic(), content)


async def get_client_content(ctx: AppContext) -> ClientContent:
    path = _content_path(ctx)
    cached = _cache_get(path)
    if cached is not None:
        return cached

    raw = _read_raw(path)
    content = _build_content(raw)
    _cache_put(path, content)
    return content


async def set_client_content_field(ctx: AppContext, field: str, value: str) -> ClientContent:
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"Unsupported content field: {field}")

    path = _content_path(ctx)
    raw = _read_raw(path)
    raw[field] = value
    _write_raw(path, raw)
    content = _build_content(raw)
    _cache_put(path, content)
    return content


async def reset_client_content(ctx: AppContext) -> ClientContent:
    path = _content_path(ctx)
    _write_raw(path, asdict(_default_content()))
    content = _default_content()
    _cache_put(path, content)
    return content

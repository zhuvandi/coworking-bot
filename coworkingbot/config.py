# Auto-generated config.py (safe defaults).
import logging
import os

from dotenv import load_dotenv

ENV_FILE_HINT = "/etc/default/coworking-bot"
FALLBACK_ENV_PATH = "/home/coworkingbot/.env"

logger = logging.getLogger(__name__)

load_dotenv()


def _get(name: str, default: str = ""):
    v = os.getenv(name)
    return v if v is not None else default


def _get_int_list(name: str):
    raw = _get(name, "")
    if not raw.strip():
        return []
    out = []
    for x in raw.replace(";", ",").split(","):
        x = x.strip()
        if not x:
            continue
        try:
            out.append(int(x))
        except ValueError:
            pass
    return out


BOT_TOKEN = _get("BOT_TOKEN")
GAS_WEBAPP_URL = _get("GAS_WEBAPP_URL")
API_TOKEN = _get("API_TOKEN")
ADMIN_IDS = _get_int_list("ADMIN_IDS")
TZ = _get("TZ", "Europe/Moscow")

if (not BOT_TOKEN or not API_TOKEN) and os.path.exists(FALLBACK_ENV_PATH):
    if load_dotenv(FALLBACK_ENV_PATH, override=False):
        logger.warning(
            "Loaded fallback env from %s because required settings were missing. "
            "Prefer systemd EnvironmentFile at %s.",
            FALLBACK_ENV_PATH,
            ENV_FILE_HINT,
        )
        BOT_TOKEN = _get("BOT_TOKEN")
        GAS_WEBAPP_URL = _get("GAS_WEBAPP_URL")
        API_TOKEN = _get("API_TOKEN")
        ADMIN_IDS = _get_int_list("ADMIN_IDS")
        TZ = _get("TZ", "Europe/Moscow")

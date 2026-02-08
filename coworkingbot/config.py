import os

ENV_FILE_HINT = "/etc/default/coworking-bot"


def _get(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return value if value is not None else default


def _get_int_list(name: str) -> list[int]:
    raw = _get(name, "")
    if not raw.strip():
        return []
    output: list[int] = []
    for item in raw.replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            output.append(int(item))
        except ValueError:
            continue
    return output


BOT_TOKEN = _get("BOT_TOKEN")
GAS_WEBAPP_URL = _get("GAS_WEBAPP_URL")
API_TOKEN = _get("API_TOKEN")
ADMIN_IDS = _get_int_list("ADMIN_IDS")
TZ = _get("TZ", "Europe/Moscow")

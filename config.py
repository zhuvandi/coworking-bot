# Auto-generated config.py (safe defaults).
import os

def _get(name: str, default: str = ""):
    v = os.getenv(name)
    return v if v is not None else default

def _get_int_list(name: str):
    raw = _get(name, "")
    if not raw.strip():
        return []
    out = []
    for x in raw.replace(';', ',').split(','):
        x = x.strip()
        if not x:
            continue
        try:
            out.append(int(x))
        except ValueError:
            pass
    return out

BOT_TOKEN = _get('BOT_TOKEN')
GAS_WEBAPP_URL = _get('GAS_WEBAPP_URL')
ADMIN_IDS = _get_int_list('ADMIN_IDS')

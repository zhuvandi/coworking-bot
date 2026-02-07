from __future__ import annotations

from datetime import date, datetime

from coworkingbot.config import ADMIN_IDS


def _parse_admin_ids(value) -> set[int]:
    """
    ADMIN_IDS может быть:
      - list[int]
      - str "1,2,3"
      - int
    """
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        out = set()
        for x in value:
            try:
                out.add(int(str(x).strip()))
            except Exception:
                pass
        return out
    if isinstance(value, int):
        return {value}
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",")]
        out = set()
        for p in parts:
            if not p:
                continue
            try:
                out.add(int(p))
            except Exception:
                pass
        return out
    return set()


def is_admin(user_id: int) -> bool:
    admins = _parse_admin_ids(ADMIN_IDS)
    return int(user_id) in admins


def is_past_booking(date_str: str) -> bool:
    """
    Сравниваем только дату (без времени).
    Поддерживаем форматы: YYYY-MM-DD, DD.MM.YYYY, DD/MM/YYYY
    """
    s = (date_str or "").strip()
    if not s:
        return False

    fmts = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y")
    d: date | None = None
    for fmt in fmts:
        try:
            d = datetime.strptime(s, fmt).date()
            break
        except Exception:
            continue

    if d is None:
        # если пришло что-то неожиданное — не валим импорт/бота
        return False

    return d < date.today()

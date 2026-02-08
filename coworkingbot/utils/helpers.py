from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime


def _parse_admin_ids(value: Iterable[int] | str | int | None) -> set[int]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        out: set[int] = set()
        for item in value:
            try:
                out.add(int(str(item).strip()))
            except Exception:
                pass
        return out
    if isinstance(value, int):
        return {value}
    if isinstance(value, str):
        out: set[int] = set()
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                out.add(int(part))
            except Exception:
                pass
        return out
    return set()


def is_admin(user_id: int, admin_ids: Iterable[int] | str | int | None) -> bool:
    admins = _parse_admin_ids(admin_ids)
    return int(user_id) in admins


def is_past_booking(date_str: str) -> bool:
    s = (date_str or "").strip()
    if not s:
        return False

    fmts = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y")
    parsed_date = None
    for fmt in fmts:
        try:
            parsed_date = datetime.strptime(s, fmt).date()
            break
        except Exception:
            continue

    if parsed_date is None:
        return False

    return parsed_date < date.today()

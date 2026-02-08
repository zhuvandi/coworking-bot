from __future__ import annotations

from datetime import datetime

from coworkingbot.app.context import AppContext


def is_admin(ctx: AppContext, user_id: int) -> bool:
    return int(user_id) in ctx.settings.admin_ids


def now(ctx: AppContext) -> datetime:
    return datetime.now(ctx.tz)


def is_past_booking(ctx: AppContext, date_str: str) -> bool:
    s = (date_str or "").strip()
    if not s:
        return False

    fmts = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y")
    parsed_date = None
    for fmt in fmts:
        try:
            parsed_date = datetime.strptime(s, fmt).date()
            break
        except ValueError:
            continue

    if parsed_date is None:
        return False

    return parsed_date < now(ctx).date()

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from coworkingbot.app.context import AppContext
from coworkingbot.services.common import now

logger = logging.getLogger(__name__)


@dataclass
class _ErrorAggregate:
    count: int
    first_seen: float
    last_sent: float


_ERROR_BUCKETS: dict[str, _ErrorAggregate] = {}
_ERROR_AGGREGATION_WINDOW_SECONDS = 600
_ERROR_SEND_EVERY = 5


async def _send_message(ctx: AppContext, chat_id: int, text: str) -> None:
    try:
        await ctx.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    except Exception as exc:
        logger.error("Failed to notify chat %s: %s", chat_id, exc)


async def send_admin_alert(ctx: AppContext, text: str) -> None:
    """Send informational alerts to service chat, fallback to admin DMs."""
    if ctx.settings.admin_alerts_chat_id is not None:
        await _send_message(ctx, ctx.settings.admin_alerts_chat_id, text)
        return
    for admin_id in ctx.settings.admin_ids:
        await _send_message(ctx, int(admin_id), text)


async def send_admin_action_required(ctx: AppContext, text: str) -> None:
    """DM admins only for events where explicit human action is needed."""
    if not ctx.settings.admin_ids:
        logger.warning("No admin IDs configured for action-required message.")
        return
    for admin_id in ctx.settings.admin_ids:
        await _send_message(ctx, int(admin_id), text)


async def send_admin_notification(ctx: AppContext, text: str) -> None:
    await send_admin_alert(ctx, text)


async def notify_admin_about_error(ctx: AppContext, error_message: str, context: str = "") -> None:
    """Aggregate repeated backend errors to reduce spam in admin channels."""
    key = f"{context}:{error_message[:120]}"
    current_time = time.monotonic()
    bucket = _ERROR_BUCKETS.get(key)
    if bucket is None:
        bucket = _ErrorAggregate(count=0, first_seen=current_time, last_sent=0)
        _ERROR_BUCKETS[key] = bucket

    bucket.count += 1
    should_send = bucket.count == 1 or bucket.count % _ERROR_SEND_EVERY == 0
    if current_time - bucket.last_sent >= _ERROR_AGGREGATION_WINDOW_SECONDS:
        should_send = True

    if not should_send:
        return

    bucket.last_sent = current_time
    duration = int(current_time - bucket.first_seen)
    message_text = (
        "🚨 <b>ОШИБКА В СИСТЕМЕ</b>\n\n"
        f"🕐 Время: {now(ctx).strftime('%H:%M %d.%m.%Y')}\n"
        f"📝 Контекст: {context}\n"
        f"📈 Повторений: {bucket.count}\n"
        f"⏱ Накопление: {duration} сек\n"
        f"💥 Ошибка: {error_message[:500]}"
    )
    await send_admin_alert(ctx, message_text)


async def notify_admin_about_cancellation(
    ctx: AppContext, record_id: str, booking_data: dict, user_id: int, reason: str = "пользователем"
) -> None:
    message_text = (
        f"❌ <b>БРОНЬ ОТМЕНЕНА {reason.upper()}</b>\n\n"
        f"📅 Дата: {booking_data.get('date', 'Неизвестно')}\n"
        f"🕐 Время: {booking_data.get('time', 'Неизвестно')}\n"
        f"👤 Клиент: {booking_data.get('name', 'Неизвестно')}\n"
        f"📞 Телефон: {booking_data.get('phone', 'Неизвестно')}\n"
        f"👤 ID клиента: {user_id}\n"
        f"📋 ID записи: <code>{record_id}</code>\n"
        f"💰 Стоимость: {booking_data.get('price', 0)} руб."
    )
    await send_admin_alert(ctx, message_text)


async def notify_admin_about_payment_confirmation(
    ctx: AppContext, record_id: str, client_name: str, admin_id: int
) -> None:
    message_text = (
        "💰 <b>ОПЛАТА ПОДТВЕРЖДЕНА</b>\n\n"
        f"📋 ID записи: <code>{record_id}</code>\n"
        f"👤 Клиент: {client_name}\n"
        f"👑 Подтвердил: Администратор ID: {admin_id}\n"
        f"⏰ Время: {now(ctx).strftime('%H:%M %d.%m.%Y')}"
    )

    if ctx.settings.admin_alerts_chat_id is not None:
        await _send_message(ctx, ctx.settings.admin_alerts_chat_id, message_text)
        return

    for admin in ctx.settings.admin_ids:
        if int(admin) == admin_id:
            continue
        await _send_message(ctx, int(admin), message_text)


async def notify_admin_about_new_booking(
    ctx: AppContext, booking_data: dict, record_id: str, user_id: int
) -> None:
    message_text = (
        "🆕 <b>НОВАЯ БРОНЬ!</b>\n\n"
        f"📅 Дата: {booking_data['date']}\n"
        f"🕐 Время: {booking_data['time']}\n"
        f"👤 Клиент: {booking_data['name']}\n"
        f"📞 Телефон: {booking_data['phone']}\n"
        f"👤 ID клиента: {user_id}\n"
        f"📋 ID записи: <code>{record_id}</code>"
    )

    await send_admin_alert(ctx, message_text)
    await send_admin_action_required(
        ctx,
        "⚠️ <b>ТРЕБУЕТСЯ ДЕЙСТВИЕ</b>\n\n"
        f"Новая бронь <code>{record_id}</code> ожидает подтверждения оплаты.\n"
        "Проверьте оплату и выполните /confirm ID_записи.",
    )


async def notify_admin_about_conflict(ctx: AppContext, details: str) -> None:
    """Conflicts need direct admin action, so they go to personal DMs."""
    await send_admin_action_required(
        ctx,
        "⚠️ <b>КОНФЛИКТ БРОНИРОВАНИЯ</b>\n\n"
        f"🕐 Время: {now(ctx).strftime('%H:%M %d.%m.%Y')}\n"
        f"📝 Детали: {details[:700]}",
    )


async def notify_admin_about_new_review(
    ctx: AppContext, record_id: str, review_text: str, user_id: int, rating: int = 0
) -> None:
    stars = "⭐" * rating if rating else ""
    message_text = (
        f"⭐ <b>НОВЫЙ ОТЗЫВ {stars}</b>\n\n"
        f"📋 ID брони: <code>{record_id}</code>\n"
        f"👤 ID клиента: {user_id}\n"
        f"⭐ Оценка: {rating}/5\n"
        f"💬 Отзыв: {review_text[:200] if review_text else 'Без текста'}..."
    )
    await send_admin_alert(ctx, message_text)

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from coworkingbot import __version__
from coworkingbot.app.context import AppContext
from coworkingbot.services.common import is_admin, now
from coworkingbot.services.notifications import (
    notify_admin_about_payment_confirmation,
    send_admin_notification,
)
from coworkingbot.services.texts import admin_help_text

logger = logging.getLogger(__name__)

router = Router()


class AdminStates(StatesGroup):
    waiting_exception_date = State()
    waiting_exception_slot = State()
    waiting_exception_remove = State()
    waiting_setting_rules = State()
    waiting_setting_limit = State()
    waiting_setting_window = State()
    waiting_user_ban = State()
    waiting_user_unban = State()
    confirming_action = State()


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Сводка", callback_data="admin_summary"),
                InlineKeyboardButton(text="⛔️ Исключения", callback_data="admin_exceptions"),
            ],
            [
                InlineKeyboardButton(text="🧩 Настройки", callback_data="admin_settings"),
                InlineKeyboardButton(text="👤 Пользователи", callback_data="admin_users"),
            ],
            [
                InlineKeyboardButton(text="🧪 Диагностика", callback_data="admin_diagnostics"),
                InlineKeyboardButton(text="❓ Помощь", callback_data="admin_help"),
            ],
            [InlineKeyboardButton(text="🚪 Выйти", callback_data="main_menu")],
        ]
    )


async def get_stats_from_gas(ctx: AppContext) -> dict:
    result = await ctx.gas.request("get_stats", {})

    if result.get("status") == "success":
        return {
            "success": True,
            "stats": result.get("stats", {}),
            "formatted_text": result.get("formatted_telegram", "Статистика не доступна"),
        }
    return {"success": False, "error": result.get("message", "Неизвестная ошибка")}


async def get_report_from_gas(ctx: AppContext, report_type: str, period: str = "current") -> dict:
    result = await ctx.gas.request("get_report", {"report_type": report_type, "period": period})

    if result.get("status") == "success":
        return {
            "success": True,
            "data": result.get("data", {}),
            "formatted_text": result.get("formatted_telegram", "Отчет сформирован"),
        }
    return {"success": False, "error": result.get("message", "Неизвестная ошибка")}


async def get_reviews_gas(
    ctx: AppContext, public_only: bool = True, limit: int = 10, mask_names: bool = True
) -> dict:
    return await ctx.gas.request(
        "get_reviews", {"public_only": public_only, "limit": limit, "mask_names": mask_names}
    )


@router.message(Command("admin"))
async def cmd_admin(message: types.Message, ctx: AppContext) -> None:
    if not is_admin(ctx, message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return

    await message.answer(
        "👑 <b>Админ-панель</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard(),
    )


async def _run_self_check(ctx: AppContext) -> tuple[str, bool]:
    from coworkingbot.app.context import validate_settings

    missing = validate_settings(ctx.settings)
    env_ok = "✅ OK" if not missing else f"❌ Отсутствуют: {', '.join(missing)}"

    try:
        import aiogram  # noqa: F401

        import_ok = "✅ OK"
    except Exception as exc:  # pragma: no cover - defensive
        import_ok = f"❌ Ошибка импорта: {exc}"

    gas_ok = "⚠️ Не проверено"
    gas_detail = ""
    try:
        result = await ctx.gas.request("test_connection", {})
        if result.get("status") == "success":
            gas_ok = "✅ OK"
            gas_detail = result.get("message", "")
        else:
            gas_ok = "❌ Ошибка"
            gas_detail = result.get("message", "")
    except Exception as exc:
        gas_ok = "❌ Ошибка"
        gas_detail = str(exc)

    report = (
        "🧪 <b>Диагностика</b>\n\n"
        f"• Env: {env_ok}\n"
        f"• Импорт: {import_ok}\n"
        f"• GAS: {gas_ok} {gas_detail}\n"
        f"• Версия: {__version__}\n"
        f"• Время: {now(ctx).strftime('%H:%M %d.%m.%Y')}\n"
    )
    ok = not missing and gas_ok.startswith("✅") and import_ok.startswith("✅")
    return report, ok


@router.message(Command("self_check"))
async def cmd_self_check(message: types.Message, ctx: AppContext) -> None:
    if not is_admin(ctx, message.from_user.id):
        await message.answer("⛔ Только для администраторов.")
        return

    report, _ = await _run_self_check(ctx)
    await message.answer(report, parse_mode="HTML")


@router.message(Command("confirm"))
async def cmd_confirm(message: types.Message, ctx: AppContext) -> None:
    if not is_admin(ctx, message.from_user.id):
        await message.answer("⛔ Только для администраторов")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "Использование: /confirm [ID_записи]\n\n"
            "Например: /confirm ID_12345678\n\n"
            "ID можно получить из списка броней в админ-панели."
        )
        return

    record_id = args[1]

    result = await ctx.gas.request(
        "confirm_payment", {"record_id": record_id, "admin_id": str(message.from_user.id)}
    )

    if result.get("status") == "success":
        if result.get("already_confirmed"):
            await message.answer("✅ Оплата уже была подтверждена ранее")
        else:
            await message.answer(
                "✅ <b>Оплата подтверждена!</b>\n\n"
                f"📋 ID: <code>{record_id}</code>\n"
                f"👤 Клиент: {result.get('client_name', 'Неизвестно')}\n"
                f"📅 Дата: {result.get('booking_date', 'Неизвестно')}\n"
                f"🕐 Время: {result.get('booking_time', 'Неизвестно')}",
                parse_mode="HTML",
            )
    else:
        await message.answer(f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}")


@router.message(Command("stats"))
async def cmd_stats(message: types.Message, ctx: AppContext) -> None:
    if not is_admin(ctx, message.from_user.id):
        await message.answer(
            "📊 <b>Статистика</b>\n\n"
            "Статистика доступна только администраторам.\n\n"
            "Для просмотра своих броней используйте:\n"
            "• <code>/my_bookings</code>\n"
            "• Или кнопку 'Мои брони' в меню",
            parse_mode="HTML",
        )
        return

    loading_msg = await message.answer("📊 Запрашиваю статистику...")

    result = await get_stats_from_gas(ctx)

    try:
        await ctx.bot.delete_message(message.chat.id, loading_msg.message_id)
    except Exception:
        pass

    if result["success"]:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📊 Подробный отчет", callback_data="report_detailed_current"
                    )
                ],
                [InlineKeyboardButton(text="↩️ В админ-панель", callback_data="admin_back")],
            ]
        )

        await message.answer(result["formatted_text"], parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(
            f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}", parse_mode="HTML"
        )


@router.message(Command("test"))
async def cmd_test(message: types.Message, ctx: AppContext) -> None:
    if not is_admin(ctx, message.from_user.id):
        await message.answer("⛔ Только для админов")
        return

    await message.answer("🔗 Тестирую подключение к GAS...")

    try:
        result = await ctx.gas.request("test_connection", {})

        if result.get("status") == "success":
            await message.answer(
                "✅ <b>Подключение работает!</b>\n\n"
                f"Сервер: <code>{ctx.settings.gas_webapp_url}</code>\n"
                f"Статус: {result.get('message', 'OK')}\n"
                f"Время: {result.get('timestamp', 'N/A')}",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                f"❌ <b>Ошибка подключения</b>\n\n{result.get('message', 'Нет ответа от сервера')}",
                parse_mode="HTML",
            )
    except Exception as exc:
        await message.answer(
            f"🔥 <b>Критическая ошибка:</b>\n\n<code>{exc}</code>", parse_mode="HTML"
        )


@router.message(Command("test_notify"))
async def cmd_test_notify(message: types.Message, ctx: AppContext) -> None:
    if not is_admin(ctx, message.from_user.id):
        await message.answer("⛔ Только для админов")
        return

    test_messages = [
        "🆕 Тест: Новая бронь",
        "❌ Тест: Отмена брони",
        "💰 Тест: Подтверждение оплаты",
        "⭐ Тест: Новый отзыв",
        "🚨 Тест: Ошибка системы",
    ]

    for msg in test_messages:
        await send_admin_notification(ctx, f"🔔 {msg}\n⏰ {now(ctx).strftime('%H:%M')}")
        await asyncio.sleep(1)

    await message.answer("✅ Тестовые уведомления отправлены!")


@router.callback_query(F.data == "admin_back")
async def action_admin_back(
    callback: types.CallbackQuery, state: FSMContext, ctx: AppContext
) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "👑 <b>Админ-панель</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard(),
    )
    await callback.answer()


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="admin_action_confirm"),
                InlineKeyboardButton(text="↩️ Отмена", callback_data="admin_action_cancel"),
            ]
        ]
    )


async def _request_confirmation(
    message: types.Message, state: FSMContext, prompt: str, action: str, payload: dict
) -> None:
    await state.update_data(pending_action=action, pending_payload=payload)
    await state.set_state(AdminStates.confirming_action)
    await message.answer(prompt, parse_mode="HTML", reply_markup=_confirm_keyboard())


@router.callback_query(F.data == "admin_action_cancel")
async def action_admin_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "Действие отменено.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="↩️ В админ-панель", callback_data="admin_back")]
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_action_confirm")
async def action_admin_confirm(
    callback: types.CallbackQuery, state: FSMContext, ctx: AppContext
) -> None:
    data = await state.get_data()
    action = data.get("pending_action")
    payload = data.get("pending_payload", {})

    await state.clear()

    if action == "add_exception_date":
        result = await ctx.gas.request("add_exception", {"type": "date", **payload})
    elif action == "add_exception_slot":
        result = await ctx.gas.request("add_exception", {"type": "slot", **payload})
    elif action == "remove_exception":
        result = await ctx.gas.request("remove_exception", payload)
    elif action == "update_setting":
        result = await ctx.gas.request("update_settings", payload)
    elif action == "ban_user":
        result = await ctx.gas.request("ban_user", payload)
    elif action == "unban_user":
        result = await ctx.gas.request("unban_user", payload)
    else:
        await callback.message.edit_text(
            "❌ Неизвестное действие.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ В админ-панель", callback_data="admin_back")]]
            ),
        )
        await callback.answer()
        return

    if result.get("status") == "success":
        await callback.message.edit_text(
            "✅ Готово.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ В админ-панель", callback_data="admin_back")]]
            ),
        )
    else:
        await callback.message.edit_text(
            f"⚠️ Ошибка: {result.get('message', 'Неизвестная ошибка')}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ В админ-панель", callback_data="admin_back")]]
            ),
        )

    await callback.answer()


@router.callback_query(F.data == "admin_summary")
async def action_admin_summary(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сегодня", callback_data="admin_summary_today"),
                InlineKeyboardButton(text="Неделя", callback_data="admin_summary_week"),
            ],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")],
        ]
    )
    await callback.message.edit_text(
        "📊 <b>Сводка</b>\n\nВыберите период:", parse_mode="HTML", reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "admin_summary_today")
async def action_admin_summary_today(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    result = await get_report_from_gas(ctx, "daily")
    text = result["formatted_text"] if result.get("success") else f"❌ Ошибка: {result.get('error')}"
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_summary")]]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_summary_week")
async def action_admin_summary_week(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    result = await get_report_from_gas(ctx, "weekly")
    text = result["formatted_text"] if result.get("success") else f"❌ Ошибка: {result.get('error')}"
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_summary")]]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_exceptions")
async def action_admin_exceptions(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список", callback_data="admin_exceptions_list")],
            [InlineKeyboardButton(text="➕ Закрыть дату", callback_data="admin_exceptions_add_date")],
            [InlineKeyboardButton(text="➕ Закрыть слот", callback_data="admin_exceptions_add_slot")],
            [InlineKeyboardButton(text="➖ Удалить", callback_data="admin_exceptions_remove")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")],
        ]
    )
    await callback.message.edit_text(
        "⛔️ <b>Исключения</b>\n\nЗакрытые даты и слоты:", parse_mode="HTML", reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "admin_exceptions_list")
async def action_admin_exceptions_list(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    result = await ctx.gas.request("get_exceptions", {})
    if result.get("status") == "success":
        exceptions = result.get("exceptions", [])
        if not exceptions:
            text = "📭 Исключений нет."
        else:
            text = "⛔️ <b>Исключения</b>\n\n"
            for item in exceptions:
                text += (
                    f"• <code>{item.get('id', 'N/A')}</code> "
                    f"{item.get('date', '')} {item.get('slot', '')}\n"
                )
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_exceptions")]]
            ),
        )
    else:
        await callback.message.edit_text(
            f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_exceptions")]]
            ),
        )
    await callback.answer()


@router.callback_query(F.data == "admin_exceptions_add_date")
async def action_admin_exceptions_add_date(
    callback: types.CallbackQuery, state: FSMContext, ctx: AppContext
) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_exception_date)
    await callback.message.answer(
        "Введите дату в формате ДД.ММ.ГГГГ, которую нужно закрыть."
    )
    await callback.answer()


@router.callback_query(F.data == "admin_exceptions_add_slot")
async def action_admin_exceptions_add_slot(
    callback: types.CallbackQuery, state: FSMContext, ctx: AppContext
) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_exception_slot)
    await callback.message.answer(
        "Введите слот в формате ДД.ММ.ГГГГ 10:00-12:00, который нужно закрыть."
    )
    await callback.answer()


@router.callback_query(F.data == "admin_exceptions_remove")
async def action_admin_exceptions_remove(
    callback: types.CallbackQuery, state: FSMContext, ctx: AppContext
) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_exception_remove)
    await callback.message.answer("Введите ID исключения для удаления.")
    await callback.answer()


@router.message(AdminStates.waiting_exception_date)
async def handle_exception_date(message: types.Message, state: FSMContext, ctx: AppContext) -> None:
    date_str = message.text.strip()
    try:
        from datetime import datetime

        datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ.")
        return

    await _request_confirmation(
        message,
        state,
        f"Закрыть дату <b>{date_str}</b>?",
        "add_exception_date",
        {"date": date_str},
    )


@router.message(AdminStates.waiting_exception_slot)
async def handle_exception_slot(message: types.Message, state: FSMContext, ctx: AppContext) -> None:
    text = message.text.strip()
    parts = text.split()
    if len(parts) != 2:
        await message.answer("❌ Используйте формат ДД.ММ.ГГГГ 10:00-12:00.")
        return

    date_str, slot = parts
    try:
        from datetime import datetime

        datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ.")
        return

    await _request_confirmation(
        message,
        state,
        f"Закрыть слот <b>{date_str} {slot}</b>?",
        "add_exception_slot",
        {"date": date_str, "slot": slot},
    )


@router.message(AdminStates.waiting_exception_remove)
async def handle_exception_remove(
    message: types.Message, state: FSMContext, ctx: AppContext
) -> None:
    record_id = message.text.strip()
    if not record_id:
        await message.answer("❌ Введите ID исключения.")
        return

    await _request_confirmation(
        message,
        state,
        f"Удалить исключение <code>{record_id}</code>?",
        "remove_exception",
        {"id": record_id},
    )


@router.callback_query(F.data == "admin_settings")
async def action_admin_settings(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    result = await ctx.gas.request("get_settings", {})
    if result.get("status") == "success":
        settings = result.get("settings", {})
        text = (
            "🧩 <b>Настройки</b>\n\n"
            f"• Правила: {settings.get('rules_text', 'не задано')}\n"
            f"• Лимит бронирований: {settings.get('booking_limit', 'не задано')}\n"
            f"• Окна времени: {settings.get('time_windows', 'не задано')}\n"
        )
    else:
        text = "🧩 <b>Настройки</b>\n\n⚠️ Не удалось загрузить настройки."

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Правила", callback_data="admin_settings_rules")],
            [InlineKeyboardButton(text="🔢 Лимит бронирований", callback_data="admin_settings_limit")],
            [InlineKeyboardButton(text="⏰ Окна времени", callback_data="admin_settings_window")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")],
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_settings_rules")
async def action_admin_settings_rules(
    callback: types.CallbackQuery, state: FSMContext, ctx: AppContext
) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_setting_rules)
    await callback.message.answer("Введите новый текст правил.")
    await callback.answer()


@router.callback_query(F.data == "admin_settings_limit")
async def action_admin_settings_limit(
    callback: types.CallbackQuery, state: FSMContext, ctx: AppContext
) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_setting_limit)
    await callback.message.answer("Введите новый лимит бронирований (число).")
    await callback.answer()


@router.callback_query(F.data == "admin_settings_window")
async def action_admin_settings_window(
    callback: types.CallbackQuery, state: FSMContext, ctx: AppContext
) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_setting_window)
    await callback.message.answer("Введите новые окна времени (например: 10:00-22:00).")
    await callback.answer()


@router.message(AdminStates.waiting_setting_rules)
async def handle_settings_rules(message: types.Message, state: FSMContext) -> None:
    rules = message.text.strip()
    if not rules:
        await message.answer("❌ Текст правил не может быть пустым.")
        return
    await _request_confirmation(
        message,
        state,
        "Сохранить новый текст правил?",
        "update_setting",
        {"rules_text": rules},
    )


@router.message(AdminStates.waiting_setting_limit)
async def handle_settings_limit(message: types.Message, state: FSMContext) -> None:
    value = message.text.strip()
    if not value.isdigit():
        await message.answer("❌ Введите число.")
        return
    await _request_confirmation(
        message,
        state,
        f"Сохранить лимит {value}?",
        "update_setting",
        {"booking_limit": int(value)},
    )


@router.message(AdminStates.waiting_setting_window)
async def handle_settings_window(message: types.Message, state: FSMContext) -> None:
    value = message.text.strip()
    if not value:
        await message.answer("❌ Окна времени не могут быть пустыми.")
        return
    await _request_confirmation(
        message,
        state,
        f"Сохранить окна времени <b>{value}</b>?",
        "update_setting",
        {"time_windows": value},
    )


@router.callback_query(F.data == "admin_users")
async def action_admin_users(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список банов", callback_data="admin_users_list")],
            [InlineKeyboardButton(text="🚫 Забанить", callback_data="admin_users_ban")],
            [InlineKeyboardButton(text="♻️ Разбанить", callback_data="admin_users_unban")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")],
        ]
    )
    await callback.message.edit_text(
        "👤 <b>Пользователи</b>", parse_mode="HTML", reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "admin_users_list")
async def action_admin_users_list(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    result = await ctx.gas.request("list_banned_users", {})
    if result.get("status") == "success":
        users = result.get("users", [])
        if not users:
            text = "✅ Забаненных пользователей нет."
        else:
            text = "🚫 <b>Забаненные пользователи</b>\n\n"
            for user in users:
                text += f"• <code>{user}</code>\n"
    else:
        text = f"⚠️ Ошибка: {result.get('message', 'Неизвестная ошибка')}"

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_users")]]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_users_ban")
async def action_admin_users_ban(
    callback: types.CallbackQuery, state: FSMContext, ctx: AppContext
) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_user_ban)
    await callback.message.answer("Введите ID пользователя для бана.")
    await callback.answer()


@router.callback_query(F.data == "admin_users_unban")
async def action_admin_users_unban(
    callback: types.CallbackQuery, state: FSMContext, ctx: AppContext
) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_user_unban)
    await callback.message.answer("Введите ID пользователя для разбана.")
    await callback.answer()


@router.message(AdminStates.waiting_user_ban)
async def handle_users_ban(message: types.Message, state: FSMContext) -> None:
    value = message.text.strip()
    if not value.isdigit():
        await message.answer("❌ Введите числовой ID пользователя.")
        return
    await _request_confirmation(
        message,
        state,
        f"Забанить пользователя <code>{value}</code>?",
        "ban_user",
        {"user_id": int(value)},
    )


@router.message(AdminStates.waiting_user_unban)
async def handle_users_unban(message: types.Message, state: FSMContext) -> None:
    value = message.text.strip()
    if not value.isdigit():
        await message.answer("❌ Введите числовой ID пользователя.")
        return
    await _request_confirmation(
        message,
        state,
        f"Разбанить пользователя <code>{value}</code>?",
        "unban_user",
        {"user_id": int(value)},
    )


@router.callback_query(F.data == "admin_diagnostics")
async def action_admin_diagnostics(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    report, _ = await _run_self_check(ctx)
    await callback.message.edit_text(
        report,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_view_today")
async def action_admin_view_today(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        result = await ctx.gas.request("get_today_bookings", {})

        if result.get("status") == "success":
            bookings = result.get("bookings", [])

            if not bookings:
                await callback.message.edit_text(
                    "📭 <b>Брони на сегодня</b>\n\nНа сегодня броней нет.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
                        ]
                    ),
                )
                return

            response = "📋 <b>Брони на сегодня</b>\n\n"

            for i, booking in enumerate(bookings, 1):
                status_emoji = "✅" if booking.get("status") == "Оплачено" else "⏳"
                response += f"{i}. {status_emoji} <b>{booking.get('time')}</b>\n"
                response += f"   👤 {booking.get('name')}\n"
                response += f"   📞 {booking.get('phone')}\n"
                response += f"   💰 {booking.get('price')} ₽\n"
                response += f"   🆔 {booking.get('id')}\n\n"

            await callback.message.edit_text(
                response,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
                    ]
                ),
            )
        else:
            await callback.message.edit_text(
                f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
                    ]
                ),
            )

    except Exception as exc:
        logger.error("Ошибка в action_admin_view_today: %s", exc)
        await callback.message.edit_text(
            "❌ Произошла ошибка при получении данных",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]]
            ),
        )

    await callback.answer()


@router.callback_query(F.data == "admin_view_tomorrow")
async def action_admin_view_tomorrow(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        tomorrow = (now(ctx) + timedelta(days=1)).strftime("%d.%m.%Y")

        result = await ctx.gas.request("get_busy_slots", {"date": tomorrow})

        if result.get("status") == "success":
            bookings = result.get("busy_slots", [])

            if not bookings:
                await callback.message.edit_text(
                    f"📭 <b>Брони на завтра ({tomorrow})</b>\n\nНа завтра броней нет.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
                        ]
                    ),
                )
                return

            response = f"📋 <b>Брони на завтра ({tomorrow})</b>\n\n"

            for i, booking in enumerate(bookings, 1):
                status_emoji = "✅" if booking.get("status") == "YES" else "⏳"
                response += f"{i}. {status_emoji} <b>{booking.get('time')}</b>\n"
                response += f"   👤 {booking.get('name')}\n"
                response += (
                    "   Статус: "
                    f"{'Оплачено' if booking.get('status') == 'YES' else 'Не оплачено'}\n\n"
                )

            await callback.message.edit_text(
                response,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
                    ]
                ),
            )
        else:
            await callback.message.edit_text(
                f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
                    ]
                ),
            )

    except Exception as exc:
        logger.error("Ошибка в action_admin_view_tomorrow: %s", exc)
        await callback.message.edit_text(
            "❌ Произошла ошибка при получении данных",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]]
            ),
        )

    await callback.answer()


@router.callback_query(F.data == "admin_stats")
async def handle_admin_stats(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer("📊 Получаю статистику...")

    result = await get_stats_from_gas(ctx)

    if result["success"]:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📊 Подробный отчет", callback_data="report_detailed_current"
                    )
                ],
                [InlineKeyboardButton(text="↩️ В админ-панель", callback_data="admin_back")],
            ]
        )

        await callback.message.edit_text(
            result["formatted_text"], parse_mode="HTML", reply_markup=keyboard
        )
    else:
        await callback.message.edit_text(
            f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]]
            ),
        )


@router.callback_query(F.data == "report_menu")
async def action_report_menu(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Ежедневный", callback_data="report_daily"),
                InlineKeyboardButton(text="📈 Еженедельный", callback_data="report_weekly"),
            ],
            [
                InlineKeyboardButton(text="📅 Ежемесячный", callback_data="report_monthly"),
                InlineKeyboardButton(text="📋 Детальный", callback_data="report_detailed"),
            ],
            [
                InlineKeyboardButton(
                    text="🚀 Быстрая статистика", callback_data="report_quick_stats"
                ),
                InlineKeyboardButton(
                    text="⚙️ Настроить автоотчеты", callback_data="report_setup_triggers"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🧪 Тест подключения", callback_data="report_test_connection"
                )
            ],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")],
        ]
    )

    await callback.message.edit_text(
        "📈 <b>Система отчетности</b>\n\nВыберите тип отчета или действие:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "report_daily")
async def action_report_daily(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        result = await get_report_from_gas(ctx, "daily")

        if result["success"]:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Назад к отчетам", callback_data="report_menu")]
                ]
            )

            await callback.message.edit_text(
                result["formatted_text"], parse_mode="HTML", reply_markup=keyboard
            )
        else:
            await callback.message.edit_text(
                f"❌ Ошибка: {result['error']}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="↩️ Назад", callback_data="report_menu")]
                    ]
                ),
            )

    except Exception as exc:
        logger.error("Ошибка в action_report_daily: %s", exc)
        await callback.answer("Произошла ошибка", show_alert=True)

    await callback.answer()


@router.callback_query(F.data == "report_weekly")
async def action_report_weekly(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        result = await get_report_from_gas(ctx, "weekly")

        if result["success"]:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Назад к отчетам", callback_data="report_menu")]
                ]
            )

            await callback.message.edit_text(
                result["formatted_text"], parse_mode="HTML", reply_markup=keyboard
            )
        else:
            await callback.message.edit_text(
                f"❌ Ошибка: {result['error']}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="↩️ Назад", callback_data="report_menu")]
                    ]
                ),
            )

    except Exception as exc:
        logger.error("Ошибка в action_report_weekly: %s", exc)
        await callback.answer("Произошла ошибка", show_alert=True)

    await callback.answer()


@router.callback_query(F.data == "report_monthly")
async def action_report_monthly(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        result = await get_report_from_gas(ctx, "monthly")

        if result["success"]:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Назад к отчетам", callback_data="report_menu")]
                ]
            )

            await callback.message.edit_text(
                result["formatted_text"], parse_mode="HTML", reply_markup=keyboard
            )
        else:
            await callback.message.edit_text(
                f"❌ Ошибка: {result['error']}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="↩️ Назад", callback_data="report_menu")]
                    ]
                ),
            )

    except Exception as exc:
        logger.error("Ошибка в action_report_monthly: %s", exc)
        await callback.answer("Произошла ошибка", show_alert=True)

    await callback.answer()


@router.callback_query(F.data == "report_detailed")
async def action_report_detailed(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📅 Текущий месяц", callback_data="report_detailed_current"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📅 Предыдущий месяц", callback_data="report_detailed_last"
                    )
                ],
                [InlineKeyboardButton(text="📅 За всё время", callback_data="report_detailed_all")],
                [InlineKeyboardButton(text="↩️ Назад", callback_data="report_menu")],
            ]
        )

        await callback.message.edit_text(
            "📊 <b>Детальный отчет</b>\n\nВыберите период:",
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    except Exception as exc:
        logger.error("Ошибка в action_report_detailed: %s", exc)
        await callback.answer("Произошла ошибка", show_alert=True)

    await callback.answer()


@router.callback_query(F.data.startswith("report_detailed_"))
async def action_report_detailed_period(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        period = callback.data.replace("report_detailed_", "")

        result = await get_report_from_gas(ctx, "detailed", period)

        if result["success"]:
            data = result.get("data", {})

            response = "📊 <b>Детальный отчет</b>\n\n"

            if period == "current":
                response += "📅 <b>Период:</b> Текущий месяц\n"
            elif period == "last":
                response += "📅 <b>Период:</b> Предыдущий месяц\n"
            else:
                response += "📅 <b>Период:</b> За всё время\n"

            if data.get("summary"):
                summary = data["summary"]
                response += "\n📈 <b>Сводка:</b>\n"
                response += f"• Всего броней: {summary.get('totalBookings', 0)}\n"
                response += f"• Оплачено: {summary.get('paidBookings', 0)}\n"
                response += f"• Не оплачено: {summary.get('unpaidBookings', 0)}\n"
                response += f"• Общий доход: {summary.get('totalIncome', 0)} ₽\n"
                response += f"• Конверсия: {summary.get('conversionRate', 0)}%\n"
                response += f"• Средний чек: {summary.get('avgCheck', 0)} ₽\n"

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Назад к отчетам", callback_data="report_menu")]
                ]
            )

            await callback.message.edit_text(response, parse_mode="HTML", reply_markup=keyboard)
        else:
            await callback.message.edit_text(
                f"❌ Ошибка генерации отчета: {result.get('error', 'Неизвестная ошибка')}",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="↩️ Назад", callback_data="report_menu")]
                    ]
                ),
            )

    except Exception as exc:
        logger.error("Ошибка в action_report_detailed_period: %s", exc)
        await callback.answer("Произошла ошибка", show_alert=True)

    await callback.answer()


@router.callback_query(F.data == "report_quick_stats")
async def action_report_quick_stats(callback: types.CallbackQuery, ctx: AppContext) -> None:
    await handle_admin_stats(callback, ctx)


@router.callback_query(F.data == "report_setup_triggers")
async def action_report_setup_triggers(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer("🔄 Настраиваю автоотчеты...")

    result = await ctx.gas.request("setup_triggers", {})

    if result.get("status") == "success":
        await callback.message.answer(
            "✅ <b>Автоотчеты настроены!</b>\n\n"
            "📅 Расписание:\n"
            "• Еженедельный отчет: воскресенье 20:00\n"
            "• Ежемесячный отчет: 1 число 10:00\n\n"
            "Отчеты будут приходить автоматически в этот чат.",
            parse_mode="HTML",
        )
    else:
        await callback.message.answer(
            f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}", parse_mode="HTML"
        )

    await callback.answer()


@router.callback_query(F.data == "report_test_connection")
async def action_report_test_connection(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer("🔗 Тестирую подключение...")

    try:
        result = await ctx.gas.request("test_connection", {})

        if result.get("status") == "success":
            await callback.message.answer(
                "✅ <b>Подключение работает!</b>\n\n"
                f"Сервер: <code>{ctx.settings.gas_webapp_url}</code>\n"
                f"Статус: {result.get('message', 'OK')}\n"
                f"Время: {result.get('timestamp', 'N/A')}",
                parse_mode="HTML",
            )
        else:
            await callback.message.answer(
                f"❌ <b>Ошибка подключения</b>\n\n{result.get('message', 'Нет ответа от сервера')}",
                parse_mode="HTML",
            )
    except Exception as exc:
        await callback.message.answer(
            f"🔥 <b>Критическая ошибка:</b>\n\n<code>{exc}</code>", parse_mode="HTML"
        )


@router.callback_query(F.data == "admin_auto_cancel")
async def action_auto_cancel(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.message.edit_text("🔄 Запускаю автоотмену...")

    result = await ctx.gas.request("auto_cancel", {})

    if result.get("status") == "success":
        message = f"✅ Автоотмена выполнена\nУдалено: {result.get('cancelled_count', 0)}"
    else:
        message = f"❌ Ошибка: {result.get('message')}"

    await callback.message.edit_text(
        message,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_send_reminders")
async def action_send_reminders(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.message.edit_text("🔔 Отправляю напоминания...")

    result = await ctx.gas.request("send_reminders", {})

    if result.get("status") == "success":
        stats = result.get("stats", {})
        message = (
            "✅ Напоминания отправлены\n\n"
            f"За 24 часа: {stats.get('day_before', 0)}\n"
            f"За 2 часа: {stats.get('two_hours_before', 0)}\n"
            f"Ошибки: {stats.get('errors', 0)}"
        )
    else:
        message = f"❌ Ошибка: {result.get('message')}"

    await callback.message.edit_text(
        message,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_all_reviews")
async def handle_admin_all_reviews(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer("📝 Загружаю отзывы...")

    result = await get_reviews_gas(ctx, public_only=False, limit=20, mask_names=False)

    if result.get("status") == "success":
        reviews = result.get("reviews", [])

        if not reviews:
            await callback.message.edit_text(
                "📭 Пока нет отзывов для модерации.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
                    ]
                ),
            )
            return

        message_text = "⭐ <b>Все отзывы (админ)</b>\n\n"

        for i, review in enumerate(reviews[:10], 1):
            rating = review.get("rating", 0)
            stars = "⭐" * int(rating)
            status = "✅ Опубликован" if review.get("is_public") else "⏳ На модерации"

            message_text += f"<b>{i}. {review.get('client_name', 'Клиент')}</b>\n"
            message_text += f"   Оценка: {stars} ({rating}/5)\n"
            message_text += f"   Статус: {status}\n"

            if review.get("review_text"):
                text = review["review_text"]
                if len(text) > 50:
                    text = text[:50] + "..."
                message_text += f"   Отзыв: {text}\n"

            if review.get("review_date"):
                message_text += f"   Дата: {review['review_date']}\n"

            message_text += f"   ID: <code>{review.get('id', 'N/A')}</code>\n\n"

        keyboard_buttons: list[list[InlineKeyboardButton]] = []

        unpublished_reviews = [r for r in reviews if not r.get("is_public")]
        if unpublished_reviews:
            keyboard_buttons.append(
                [InlineKeyboardButton(text="📈 Статистика", callback_data="admin_review_stats")]
            )

        keyboard_buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(message_text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await callback.message.edit_text(
            f"❌ Ошибка загрузки отзывов: {result.get('message', 'Неизвестная ошибка')}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]]
            ),
        )


@router.callback_query(F.data == "admin_review_stats")
async def handle_admin_review_stats(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer("📈 Загружаю статистику...")

    result = await get_reviews_gas(ctx, public_only=False, limit=100, mask_names=False)

    if result.get("status") == "success":
        reviews = result.get("reviews", [])
        average = result.get("average_rating", 0)

        rating_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for review in reviews:
            rating = int(review.get("rating", 0))
            if rating in rating_counts:
                rating_counts[rating] += 1

        total = len(reviews)
        public_count = sum(1 for review in reviews if review.get("is_public"))

        message_text = (
            "📊 <b>Статистика отзывов</b>\n\n"
            f"📈 Всего отзывов: <b>{total}</b>\n"
            f"✅ Опубликовано: <b>{public_count}</b>\n"
            f"⏳ На модерации: <b>{total - public_count}</b>\n"
            f"⭐ Средняя оценка: <b>{float(average):.1f}/5</b>\n\n"
            "<b>Распределение оценок:</b>\n"
        )

        for rating in range(5, 0, -1):
            count = rating_counts[rating]
            percentage = (count / total * 100) if total > 0 else 0
            bar = "█" * int(percentage / 5)
            message_text += f"{'⭐' * rating}: {bar} {count} ({percentage:.1f}%)\n"

        await callback.message.edit_text(
            message_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📋 Все отзывы", callback_data="admin_all_reviews")],
                    [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")],
                ]
            ),
        )
    else:
        await callback.message.edit_text(
            f"❌ Ошибка загрузки статистики: {result.get('message', 'Неизвестная ошибка')}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]]
            ),
        )


@router.callback_query(F.data == "admin_help")
async def action_admin_help(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]]
    )

    await callback.message.edit_text(admin_help_text(), parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_"))
async def handle_confirm_payment(callback: types.CallbackQuery, ctx: AppContext) -> None:
    if not is_admin(ctx, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    record_id = callback.data.replace("confirm_", "")

    await callback.answer(f"Подтверждаем оплату {record_id}...")

    result = await ctx.gas.request(
        "confirm_payment", {"record_id": record_id, "admin_id": str(callback.from_user.id)}
    )

    if result.get("status") == "success":
        if result.get("already_confirmed"):
            await callback.answer("✅ Оплата уже была подтверждена ранее", show_alert=True)
        else:
            await callback.answer("✅ Оплата подтверждена!", show_alert=True)

        client_name = result.get("client_name", "")
        booking_date = result.get("booking_date", "")
        booking_time = result.get("booking_time", "")

        await notify_admin_about_payment_confirmation(
            ctx, record_id, client_name, callback.from_user.id
        )

        await callback.message.edit_text(
            "✅ <b>Оплата подтверждена!</b>\n\n"
            f"📋 ID: <code>{record_id}</code>\n"
            f"👤 Клиент: {client_name}\n"
            f"📅 Дата: {booking_date}\n"
            f"🕐 Время: {booking_time}\n"
            "👑 Подтвердил: Администратор",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="↩️ Назад в админ-панель", callback_data="admin_back"
                        )
                    ]
                ]
            ),
        )

        try:
            client_chat_id = result.get("client_chat_id")
            if client_chat_id:
                await ctx.bot.send_message(
                    chat_id=int(client_chat_id),
                    text=(
                        "🎉 <b>Ваша оплата подтверждена!</b>\n\n"
                        f"📅 Дата: {booking_date}\n"
                        f"🕐 Время: {booking_time}\n"
                        f"👤 Имя: {client_name}\n\n"
                        "✅ Бронирование активное. Ждем вас!"
                    ),
                    parse_mode="HTML",
                )
        except Exception as exc:
            logger.error("Ошибка отправки уведомления клиенту: %s", exc)

    else:
        error_msg = result.get("message", "Неизвестная ошибка")
        await callback.answer(f"❌ Ошибка: {error_msg}", show_alert=True)

        await callback.message.edit_text(
            "❌ <b>Ошибка подтверждения оплаты</b>\n\n"
            f"ID: <code>{record_id}</code>\n"
            f"Ошибка: {error_msg}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="↩️ Назад в админ-панель", callback_data="admin_back"
                        )
                    ]
                ]
            ),
        )

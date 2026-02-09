from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from coworkingbot.app.context import AppContext
from coworkingbot.keyboards.main import main_menu_keyboard, menu_only_keyboard
from coworkingbot.services.common import is_admin, is_past_booking, now
from coworkingbot.services.errors import send_user_error
from coworkingbot.services.notifications import (
    notify_admin_about_cancellation,
    notify_admin_about_new_booking,
)

logger = logging.getLogger(__name__)

router = Router()


class BookingStates(StatesGroup):
    choosing_date = State()
    choosing_time = State()
    getting_name = State()
    confirming_booking = State()


def get_tomorrow_date(ctx: AppContext) -> str:
    tomorrow = now(ctx) + timedelta(days=1)
    return tomorrow.strftime("%d.%m.%Y")


def parse_date(ctx: AppContext, date_str: str) -> tuple[datetime | None, str | None]:
    try:
        parsed_date = datetime.strptime(date_str, "%d.%m.%Y")
        parsed_date = ctx.tz.localize(parsed_date)

        today = now(ctx).replace(hour=0, minute=0, second=0, microsecond=0)
        parsed_date_only = parsed_date.replace(hour=0, minute=0, second=0, microsecond=0)

        if parsed_date_only < today:
            return None, "❌ Нельзя выбрать прошедшую дату."

        return parsed_date, None
    except ValueError:
        return None, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ"


def validate_phone(phone: str) -> bool:
    phone_clean = re.sub(r"[\s\(\)\-+]", "", phone)
    patterns = [
        r"^7\d{10}$",
        r"^8\d{10}$",
        r"^\+7\d{10}$",
        r"^9\d{9}$",
    ]
    return any(re.match(pattern, phone_clean) for pattern in patterns)


def format_phone(phone: str) -> str:
    phone_clean = re.sub(r"[\s\(\)\-+]", "", phone)

    if phone_clean.startswith("8"):
        return "7" + phone_clean[1:]
    if phone_clean.startswith("+7"):
        return phone_clean[1:]
    if phone_clean.startswith("9") and len(phone_clean) == 10:
        return "7" + phone_clean
    return phone_clean


async def get_free_slots_for_date(ctx: AppContext, date_str: str) -> list[str]:
    result = await ctx.gas.request("get_free_slots", {"date": date_str})

    if result.get("status") == "success":
        return result.get("free_slots", [])

    logger.error("GAS error when requesting slots: %s", result.get("message"))
    return []


async def get_reviews_gas(
    ctx: AppContext, public_only: bool = True, limit: int = 10, mask_names: bool = True
) -> dict:
    return await ctx.gas.request(
        "get_reviews", {"public_only": public_only, "limit": limit, "mask_names": mask_names}
    )


async def save_review_gas(
    ctx: AppContext, record_id: str, rating: int, review_text: str = ""
) -> dict:
    return await ctx.gas.request(
        "save_review", {"record_id": record_id, "rating": rating, "review_text": review_text}
    )


def format_reviews_for_telegram(result: dict) -> str:
    if result.get("status") != "success":
        return "❌ Не удалось загрузить отзывы. Попробуйте позже."

    reviews = result.get("reviews", [])
    count = result.get("count", 0)
    avg_rating = result.get("average_rating", 0)

    if count == 0:
        return "⭐️ <b>Отзывы</b>\n\nНа данный момент отзывов еще нет."

    text = "⭐️ <b>Отзывы клиентов</b>\n\n"
    text += "📊 <b>Статистика:</b>\n"
    try:
        avg_rating_num = float(avg_rating) if avg_rating else 0
        text += f"• Всего отзывов: {count}\n"
        text += f"• Средняя оценка: {avg_rating_num:.1f}/5\n\n"
    except (ValueError, TypeError):
        text += f"• Всего отзывов: {count}\n"
        text += f"• Средняя оценка: {avg_rating}/5\n\n"

    for i, review in enumerate(reviews[:5], 1):
        rating = review.get("rating", 0)
        stars = "⭐" * int(rating)
        client = review.get("client_name", "Аноним")
        comment = review.get("review_text", "")
        date = (
            review.get("review_date", "").split()[0]
            if review.get("review_date")
            else "Дата неизвестна"
        )

        text += f"{i}. <b>{client}</b> {stars} ({rating}/5)\n"
        if comment:
            if len(comment) > 60:
                text += f'   <i>"{comment[:60]}..."</i>\n'
            else:
                text += f'   <i>"{comment}"</i>\n'
        text += f"   📅 {date}\n\n"

    return text


def _user_display_name(user: types.User) -> str:
    full_name = " ".join(part for part in [user.first_name, user.last_name] if part)
    return full_name or (user.username or "Гость")


def _build_my_bookings_keyboard(bookings: list[dict]) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    for idx, booking in enumerate(bookings, 1):
        record_id = booking.get("id")
        if not record_id:
            continue
        status = booking.get("status", "")
        if status == "Оплачено":
            continue
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"❌ Отменить {idx}", callback_data=f"booking_cancel:{record_id}"
                ),
                InlineKeyboardButton(
                    text=f"🔁 Перенести {idx}", callback_data=f"booking_reschedule:{record_id}"
                ),
            ]
        )

    buttons.append([InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def send_my_bookings(message: types.Message, ctx: AppContext) -> None:
    user_id = message.from_user.id
    result = await ctx.gas.request("get_user_bookings", {"user_id": user_id, "active_only": False})

    if result.get("status") != "success":
        await send_user_error(
            message,
            ctx,
            "⚠️ Не удалось получить список броней. Попробуйте позже.",
            f"get_user_bookings failed: {result}",
            "my_bookings",
        )
        return

    bookings = result.get("bookings", [])
    if not bookings:
        await message.answer("📭 У вас еще нет броней.", reply_markup=main_menu_keyboard())
        return

    response = "📋 <b>Ваши брони</b>\n\n"
    bot_info = await ctx.bot.get_me()

    for i, booking in enumerate(bookings[:10], 1):
        status = booking.get("status", "Неизвестно")
        status_emoji = "✅" if status == "Оплачено" else "⏳"
        response += f"{i}. {status_emoji} <b>{booking.get('date')} {booking.get('time')}</b>\n"
        response += f"   Статус: {status}\n"
        if booking.get("price"):
            response += f"   Цена: {booking.get('price')} ₽\n"
        response += f"   🆔 {booking.get('id')}\n"

        if status == "Оплачено" and is_past_booking(ctx, booking.get("date")):
            response += (
                "   📝 "
                f"[Оставить отзыв](https://t.me/{bot_info.username}?start=review_{booking.get('id')})\n"
            )

        response += "\n"

    await message.answer(
        response,
        parse_mode="HTML",
        reply_markup=_build_my_bookings_keyboard(bookings[:10]),
    )


@router.message(Command("my_bookings"))
async def cmd_my_bookings(message: types.Message, ctx: AppContext) -> None:
    await send_my_bookings(message, ctx)


@router.message(Command("reviews"))
async def cmd_reviews(message: types.Message, ctx: AppContext) -> None:
    await message.answer("📖 Загружаю отзывы...")

    result = await get_reviews_gas(ctx, public_only=True, limit=10, mask_names=True)

    if result.get("status") == "success":
        reviews_text = format_reviews_for_telegram(result)

        keyboard_buttons: list[list[InlineKeyboardButton]] = []

        if is_admin(ctx, message.from_user.id):
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(
                        text="📊 Все отзывы (админ)", callback_data="admin_all_reviews"
                    ),
                    InlineKeyboardButton(text="📈 Статистика", callback_data="admin_review_stats"),
                ]
            )

        keyboard_buttons.append(
            [
                InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data="leave_review_info"),
                InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu"),
            ]
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await message.answer(reviews_text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await send_user_error(
            message,
            ctx,
            "⚠️ Не удалось загрузить отзывы. Попробуйте позже.",
            f"get_reviews failed: {result}",
            "reviews",
        )


@router.message(Command("myid"))
async def cmd_myid(message: types.Message, ctx: AppContext) -> None:
    await message.answer(
        "👤 <b>Ваши данные:</b>\n\n"
        f"ID пользователя: <code>{message.from_user.id}</code>\n"
        f"Username: @{message.from_user.username or 'нет'}\n"
        f"Имя: {message.from_user.first_name or 'не указано'}\n"
        f"Чат ID: <code>{message.chat.id}</code>\n"
        f"Тип чата: {message.chat.type}\n\n"
        f"Являетесь админом: {'✅ Да' if is_admin(ctx, message.from_user.id) else '❌ Нет'}",
        parse_mode="HTML",
    )


async def start_booking_flow(message: types.Message, state: FSMContext, ctx: AppContext) -> None:
    await state.clear()

    tomorrow = get_tomorrow_date(ctx)
    await message.answer(
        "📅 <b>Шаг 1: Выберите дату</b>\n\n"
        "Введите дату в формате <b>ДД.ММ.ГГГГ</b>\n"
        f"<i>Например: {tomorrow}</i>",
        parse_mode="HTML",
        reply_markup=menu_only_keyboard(),
    )
    await state.set_state(BookingStates.choosing_date)


async def send_confirmation(message: types.Message, state: FSMContext, ctx: AppContext) -> None:
    data = await state.get_data()
    date_str = data.get("date_str", "")
    selected_slot = data.get("selected_slot", "")
    client_name = data.get("client_name") or _user_display_name(message.from_user)
    client_phone = data.get("client_phone")

    await state.update_data(client_name=client_name)

    phone_text = client_phone if client_phone else "<i>не указан</i>"

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="✅ Подтвердить"),
                KeyboardButton(text="❌ Отменить"),
            ],
            [KeyboardButton(text="✏️ Изменить имя")],
            [KeyboardButton(text="📱 Отправить телефон", request_contact=True)],
            [KeyboardButton(text="🏠 В меню")],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        "✅ <b>Подтверждение бронирования</b>\n\n"
        f"📅 Дата: <b>{date_str}</b>\n"
        f"🕐 Слот: <b>{selected_slot}</b>\n"
        f"👤 Имя: <b>{client_name}</b>\n"
        f"📞 Телефон: {phone_text}\n\n"
        "Проверьте данные и подтвердите бронирование.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await state.set_state(BookingStates.confirming_booking)


@router.message(F.text == "📅 Забронировать")
async def new_booking(message: types.Message, state: FSMContext, ctx: AppContext) -> None:
    await start_booking_flow(message, state, ctx)


@router.message(F.text == "🧾 Мои брони")
async def handle_my_bookings_button(message: types.Message, ctx: AppContext) -> None:
    await send_my_bookings(message, ctx)


@router.message(BookingStates.choosing_date)
async def process_date(message: types.Message, state: FSMContext, ctx: AppContext) -> None:
    date_str = message.text.strip()
    parsed_date, error = parse_date(ctx, date_str)

    if error:
        tomorrow = get_tomorrow_date(ctx)
        await message.answer(
            f"{error}\n\nВведите дату в формате <b>ДД.ММ.ГГГГ</b>\n<i>Например: {tomorrow}</i>",
            parse_mode="HTML",
            reply_markup=menu_only_keyboard(),
        )
        return

    await state.update_data(booking_date=parsed_date, date_str=date_str)

    await message.answer(
        f"📅 Дата: <b>{date_str}</b>\n🔍 <i>Ищу свободное время...</i>", parse_mode="HTML"
    )

    free_slots = await get_free_slots_for_date(ctx, date_str)

    if not free_slots:
        await message.answer(
            f"❌ На <b>{date_str}</b> нет свободных слотов.\n\nВыберите другую дату.",
            parse_mode="HTML",
            reply_markup=menu_only_keyboard(),
        )
        await state.set_state(BookingStates.choosing_date)
        return

    await state.update_data(free_slots=free_slots)

    keyboard_buttons: list[list[KeyboardButton]] = []
    row: list[KeyboardButton] = []
    for i, slot in enumerate(free_slots):
        row.append(KeyboardButton(text=slot))
        if len(row) == 3 or i == len(free_slots) - 1:
            keyboard_buttons.append(row)
            row = []

    keyboard_buttons.append([KeyboardButton(text="🏠 В меню")])
    keyboard = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)

    await message.answer(
        f"📅 Дата: <b>{date_str}</b>\n"
        "🕐 <b>Шаг 2: Выберите свободное время</b>\n\n"
        "Доступные слоты:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await state.set_state(BookingStates.choosing_time)


@router.message(BookingStates.choosing_time)
async def process_time(message: types.Message, state: FSMContext, ctx: AppContext) -> None:
    selected_slot = message.text.strip()

    data = await state.get_data()
    free_slots = data.get("free_slots", [])
    date_str = data.get("date_str", "")

    if selected_slot not in free_slots:
        current_free_slots = await get_free_slots_for_date(ctx, date_str)

        if selected_slot in current_free_slots:
            await state.update_data(free_slots=current_free_slots)
            free_slots = current_free_slots
        else:
            await message.answer("❌ Этот слот только что заняли! Выбирайте из доступных:")
            await state.update_data(free_slots=current_free_slots)
            free_slots = current_free_slots

            if current_free_slots:
                keyboard_buttons: list[list[KeyboardButton]] = []
                row: list[KeyboardButton] = []
                for i, slot in enumerate(current_free_slots):
                    row.append(KeyboardButton(text=slot))
                    if len(row) == 3 or i == len(current_free_slots) - 1:
                        keyboard_buttons.append(row)
                        row = []

                keyboard_buttons.append([KeyboardButton(text="🏠 В меню")])
                keyboard = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)

                await message.answer(
                    f"📅 Дата: <b>{date_str}</b>\n🕐 Обновленные слоты:",
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            else:
                await message.answer(
                    f"❌ На <b>{date_str}</b> больше нет свободных слотов.",
                    parse_mode="HTML",
                    reply_markup=menu_only_keyboard(),
                )
                await state.set_state(BookingStates.choosing_date)
            return

    await state.update_data(selected_slot=selected_slot)
    await send_confirmation(message, state, ctx)


@router.message(BookingStates.getting_name)
async def process_name(message: types.Message, state: FSMContext, ctx: AppContext) -> None:
    name = message.text.strip()

    if len(name) < 2:
        await message.answer(
            "❌ Имя слишком короткое. Введите имя (минимум 2 символа):",
            reply_markup=menu_only_keyboard(),
        )
        return

    await state.update_data(client_name=name)
    await send_confirmation(message, state, ctx)


@router.message(BookingStates.confirming_booking, F.content_type.in_({"contact", "text"}))
async def process_confirmation(message: types.Message, state: FSMContext, ctx: AppContext) -> None:
    if message.contact:
        phone = message.contact.phone_number
        if not validate_phone(phone):
            await message.answer(
                "❌ Неверный формат телефона. Попробуйте другой номер.",
                reply_markup=menu_only_keyboard(),
            )
            return
        formatted_phone = format_phone(phone)
        await state.update_data(client_phone=formatted_phone)
        await send_confirmation(message, state, ctx)
        return

    user_choice = (message.text or "").strip()

    if validate_phone(user_choice):
        formatted_phone = format_phone(user_choice)
        await state.update_data(client_phone=formatted_phone)
        await send_confirmation(message, state, ctx)
        return

    if user_choice == "✏️ Изменить имя":
        await message.answer(
            "📝 Введите имя для брони:",
            reply_markup=menu_only_keyboard(),
        )
        await state.set_state(BookingStates.getting_name)
        return

    if user_choice == "❌ Отменить":
        await message.answer(
            "❌ Бронирование отменено.",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        return

    if user_choice == "✅ Подтвердить":
        data = await state.get_data()
        if not data.get("client_phone"):
            await message.answer("📞 Пожалуйста, отправьте номер телефона (можно через кнопку).")
            await send_confirmation(message, state, ctx)
            return

        await message.answer("📝 Отправляю данные на сервер...", parse_mode="HTML")

        booking_data = {
            "date": data.get("date_str", ""),
            "time": data.get("selected_slot", ""),
            "name": data.get("client_name", ""),
            "phone": data.get("client_phone", ""),
            "user_id": str(message.from_user.id),
        }

        result = await ctx.gas.request("create_booking", booking_data)

        if result.get("status") == "success":
            record_id = result.get("record_id", "")

            await message.answer(
                "🎉 <b>Бронирование успешно создано!</b>\n\n"
                f"📅 {data.get('date_str', '')}\n"
                f"🕐 {data.get('selected_slot', '')}\n"
                f"👤 {data.get('client_name', '')}\n"
                f"📞 {data.get('client_phone', '')}\n\n"
                f"📋 ID брони: <code>{record_id}</code>\n\n"
                "✅ Администратор получил уведомление.",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )

            logger.info("Created booking: %s (ID: %s)", booking_data, record_id)

            await notify_admin_about_new_booking(ctx, booking_data, record_id, message.from_user.id)

        else:
            await send_user_error(
                message,
                ctx,
                "⚠️ Не удалось создать бронь. Попробуйте позже.",
                f"create_booking failed: {result}",
                "create_booking",
            )

        await state.clear()
        return

    await message.answer(
        "Пожалуйста, выберите действие из предложенных вариантов.",
        reply_markup=menu_only_keyboard(),
    )


@router.message(Command("today_bookings"))
async def cmd_today_bookings(message: types.Message, ctx: AppContext) -> None:
    user_id = message.from_user.id

    if is_admin(ctx, user_id):
        result = await ctx.gas.request("get_today_bookings", {})

        if result.get("status") == "success":
            bookings = result.get("bookings", [])

            if not bookings:
                await message.answer("📭 На сегодня броней нет.")
                return

            response = "📋 <b>Брони на сегодня</b>\n\n"

            for i, booking in enumerate(bookings, 1):
                status_emoji = "✅" if booking.get("status") == "Оплачено" else "⏳"
                response += f"{i}. {status_emoji} <b>{booking.get('time')}</b>\n"
                response += f"   👤 {booking.get('name')}\n"
                response += f"   📞 {booking.get('phone')}\n"
                response += f"   💰 {booking.get('price')} ₽\n"
                response += f"   🆔 {booking.get('id')}\n\n"

            await message.answer(response, parse_mode="HTML")
        else:
            await message.answer(f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}")
        return

    result = await ctx.gas.request("get_user_bookings", {"user_id": user_id, "active_only": True})

    if result.get("status") == "success":
        bookings = result.get("bookings", [])

        today = now(ctx).strftime("%d.%m.%Y")
        today_bookings = [b for b in bookings if b.get("date") == today]

        if not today_bookings:
            await message.answer("📭 У вас нет броней на сегодня.")
            return

        response = "📋 <b>Ваши брони на сегодня</b>\n\n"

        for i, booking in enumerate(today_bookings, 1):
            status_emoji = "✅" if booking.get("status") == "Оплачено" else "⏳"
            response += f"{i}. {status_emoji} <b>{booking.get('time')}</b>\n"
            response += f"   Статус: {booking.get('status')}\n"
            if booking.get("price"):
                response += f"   Цена: {booking.get('price')} ₽\n"
            response += f"   🆔 {booking.get('id')}\n\n"

        await message.answer(response, parse_mode="HTML")
    else:
        await send_user_error(
            message,
            ctx,
            "⚠️ Не удалось получить брони на сегодня. Попробуйте позже.",
            f"get_user_bookings failed: {result}",
            "today_bookings",
        )


@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, ctx: AppContext) -> None:
    args = message.text.split()

    if len(args) < 2:
        help_text = (
            "❌ <b>Отмена бронирования</b>\n\n"
            "Использование:\n"
            "• <code>/cancel [ID_брони]</code> - отменить конкретную бронь\n\n"
            "Чтобы посмотреть ID ваших броней:\n"
            "• Используйте <code>/my_bookings</code>\n"
            "• Или нажмите кнопку 'Мои брони' в меню"
        )
        await message.answer(help_text, parse_mode="HTML")
        return

    record_id = args[1]
    user_id = message.from_user.id

    result = await ctx.gas.request("get_user_bookings", {"user_id": user_id, "active_only": False})

    if result.get("status") != "success":
        await send_user_error(
            message,
            ctx,
            "⚠️ Не удалось получить бронь. Попробуйте позже.",
            f"get_user_bookings failed: {result}",
            "cancel_booking",
        )
        return

    bookings = result.get("bookings", [])
    user_booking = next((b for b in bookings if b.get("id") == record_id), None)

    if not user_booking:
        if is_admin(ctx, user_id):
            await cancel_booking_by_admin(message, record_id, user_id, ctx)
            return
        await message.answer("❌ Бронь не найдена или у вас нет прав для её отмены.")
        return

    if user_booking.get("status") == "Оплачено":
        await message.answer(
            "⚠️ <b>Оплаченные брони нельзя отменить через бота.</b>\n\n"
            "Пожалуйста, свяжитесь с администратором:\n"
            "📞 Телефон: [ваш телефон]",
            parse_mode="HTML",
        )
        return

    cancel_result = await ctx.gas.request(
        "cancel_booking", {"record_id": record_id, "user_id": str(user_id)}
    )

    if cancel_result.get("status") == "success":
        await message.answer(
            "✅ <b>Бронь отменена!</b>\n\n"
            f"ID: <code>{record_id}</code>\n"
            f"Дата: {user_booking.get('date', 'Неизвестно')}\n"
            f"Время: {user_booking.get('time', 'Неизвестно')}\n\n"
            "Деньги не списывались, так как бронь не была оплачена.",
            parse_mode="HTML",
        )

        await notify_admin_about_cancellation(ctx, record_id, user_booking, user_id)
    else:
        await send_user_error(
            message,
            ctx,
            "⚠️ Не удалось отменить бронь. Попробуйте позже.",
            f"cancel_booking failed: {cancel_result}",
            "cancel_booking",
        )


async def cancel_booking_by_admin(
    message: types.Message, record_id: str, admin_id: int, ctx: AppContext
) -> None:
    booking_info = await ctx.gas.request("get_booking_info", {"record_id": record_id})

    if booking_info.get("status") != "success":
        await message.answer(f"❌ Бронь не найдена: {record_id}")
        return

    cancel_result = await ctx.gas.request(
        "cancel_booking", {"record_id": record_id, "admin_id": str(admin_id), "force": True}
    )

    if cancel_result.get("status") == "success":
        client_name = booking_info.get("client_name", "Неизвестно")
        booking_date = booking_info.get("booking_date", "Неизвестно")
        booking_time = booking_info.get("booking_time", "Неизвестно")

        await message.answer(
            "✅ <b>Бронь отменена администратором</b>\n\n"
            f"ID: <code>{record_id}</code>\n"
            f"👤 Клиент: {client_name}\n"
            f"📅 Дата: {booking_date}\n"
            f"🕐 Время: {booking_time}\n\n"
            f"Отменено администратором ID: {admin_id}",
            parse_mode="HTML",
        )

        if booking_info.get("status") == "YES" and booking_info.get("client_chat_id"):
            try:
                await ctx.bot.send_message(
                    chat_id=int(booking_info["client_chat_id"]),
                    text=(
                        "⚠️ <b>Ваша бронь отменена</b>\n\n"
                        f"📅 Дата: {booking_date}\n"
                        f"🕐 Время: {booking_time}\n\n"
                        "Бронь отменена администратором.\n"
                        "По вопросам возврата средств свяжитесь с нами."
                    ),
                    parse_mode="HTML",
                )
            except Exception as exc:
                logger.error("Failed to notify client about cancellation: %s", exc)
    else:
        await message.answer(
            f"❌ Ошибка отмены: {cancel_result.get('message', 'Неизвестная ошибка')}"
        )


@router.message(Command("today"))
async def cmd_today(message: types.Message, ctx: AppContext) -> None:
    await cmd_today_bookings(message, ctx)


@router.message(F.text == "Брони на сегодня")
async def handle_today_bookings_button(message: types.Message, ctx: AppContext) -> None:
    await cmd_today_bookings(message, ctx)


@router.message(F.text == "Отменить бронирование")
async def handle_cancel_button(message: types.Message) -> None:
    help_text = (
        "❌ <b>Отмена бронирования</b>\n\n"
        "Чтобы отменить бронь:\n"
        "1. Посмотрите ID брони через <code>/my_bookings</code>\n"
        "2. Используйте команду: <code>/cancel [ID_брони]</code>\n\n"
        "Пример: <code>/cancel ID_ABC123</code>"
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(F.text == "Статистика")
async def handle_stats_button(message: types.Message) -> None:
    await message.answer(
        "📊 <b>Статистика</b>\n\n"
        "Статистика доступна только администраторам.\n\n"
        "Для просмотра своих броней используйте:\n"
        "• <code>/my_bookings</code>\n"
        "• Или кнопку 'Мои брони' в меню",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "leave_review_info")
async def action_leave_review_info(callback: types.CallbackQuery) -> None:
    info_text = (
        "⭐️ <b>Как оставить отзыв?</b>\n\n"
        "Отзыв можно оставить только после посещения коворкинга.\n\n"
        "<b>Способ 1:</b> Автоматически\n"
        "• После посещения бот автоматически спросит ваш отзыв\n"
        "• Ответьте на сообщение бота с предложением оценить\n\n"
        "<b>Способ 2:</b> Через бота\n"
        "• Используйте команду /my_bookings\n"
        "• Выберите завершенную бронь\n"
        '• Нажмите "Оставить отзыв"\n\n'
        "<b>Обратите внимание:</b>\n"
        "• Можно оценить от 1 до 5 звезд\n"
        "• Можно добавить текстовый комментарий\n"
        "• Отзывы проходят модерацию"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мои брони", callback_data="my_bookings_callback")],
            [InlineKeyboardButton(text="↩️ Назад к отзывам", callback_data="reviews_back")],
        ]
    )

    await callback.message.edit_text(info_text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "my_bookings_callback")
async def action_my_bookings_callback(callback: types.CallbackQuery, ctx: AppContext) -> None:
    await send_my_bookings(callback.message, ctx)
    await callback.answer()


@router.callback_query(F.data.startswith("booking_cancel:"))
async def action_booking_cancel(callback: types.CallbackQuery, ctx: AppContext) -> None:
    record_id = callback.data.split("booking_cancel:", 1)[-1]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, отменить", callback_data=f"booking_cancel_confirm:{record_id}"
                ),
                InlineKeyboardButton(text="↩️ Назад", callback_data="my_bookings_callback"),
            ],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")],
        ]
    )
    await callback.message.edit_text(
        "⚠️ Вы уверены, что хотите отменить бронь?", reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("booking_reschedule:"))
async def action_booking_reschedule(callback: types.CallbackQuery, ctx: AppContext) -> None:
    record_id = callback.data.split("booking_reschedule:", 1)[-1]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, перенести",
                    callback_data=f"booking_reschedule_confirm:{record_id}",
                ),
                InlineKeyboardButton(text="↩️ Назад", callback_data="my_bookings_callback"),
            ],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")],
        ]
    )
    await callback.message.edit_text(
        "⚠️ Перенос означает отмену текущей брони и создание новой.",
        reply_markup=keyboard,
    )
    await callback.answer()


async def _find_user_booking(ctx: AppContext, user_id: int, record_id: str) -> dict | None:
    result = await ctx.gas.request("get_user_bookings", {"user_id": user_id, "active_only": False})
    if result.get("status") != "success":
        return None
    bookings = result.get("bookings", [])
    return next((b for b in bookings if b.get("id") == record_id), None)


@router.callback_query(F.data.startswith("booking_cancel_confirm:"))
async def action_booking_cancel_confirm(callback: types.CallbackQuery, ctx: AppContext) -> None:
    record_id = callback.data.split("booking_cancel_confirm:", 1)[-1]
    user_id = callback.from_user.id
    booking = await _find_user_booking(ctx, user_id, record_id)

    if not booking:
        await callback.message.edit_text(
            "❌ Бронь не найдена или у вас нет прав для отмены.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")]
                ]
            ),
        )
        await callback.answer()
        return

    if booking.get("status") == "Оплачено":
        await callback.message.edit_text(
            "⚠️ Оплаченные брони нельзя отменить через бота. Свяжитесь с поддержкой.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")]
                ]
            ),
        )
        await callback.answer()
        return

    cancel_result = await ctx.gas.request(
        "cancel_booking", {"record_id": record_id, "user_id": str(user_id)}
    )

    if cancel_result.get("status") == "success":
        await callback.message.edit_text(
            "✅ Бронь отменена.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")]
                ]
            ),
        )
        await notify_admin_about_cancellation(ctx, record_id, booking, user_id)
    else:
        await callback.message.edit_text(
            "⚠️ Не удалось отменить бронь. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")]
                ]
            ),
        )
        await send_user_error(
            callback.message,
            ctx,
            "⚠️ Не удалось отменить бронь. Попробуйте позже.",
            f"cancel_booking failed: {cancel_result}",
            "cancel_booking",
        )

    await callback.answer()


@router.callback_query(F.data.startswith("booking_reschedule_confirm:"))
async def action_booking_reschedule_confirm(
    callback: types.CallbackQuery, state: FSMContext, ctx: AppContext
) -> None:
    record_id = callback.data.split("booking_reschedule_confirm:", 1)[-1]
    user_id = callback.from_user.id
    booking = await _find_user_booking(ctx, user_id, record_id)

    if not booking:
        await callback.message.edit_text(
            "❌ Бронь не найдена или у вас нет прав для переноса.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")]
                ]
            ),
        )
        await callback.answer()
        return

    if booking.get("status") == "Оплачено":
        await callback.message.edit_text(
            "⚠️ Оплаченные брони нельзя переносить через бота. Свяжитесь с поддержкой.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")]
                ]
            ),
        )
        await callback.answer()
        return

    cancel_result = await ctx.gas.request(
        "cancel_booking", {"record_id": record_id, "user_id": str(user_id)}
    )

    if cancel_result.get("status") == "success":
        await notify_admin_about_cancellation(ctx, record_id, booking, user_id, reason="переносом")
        await callback.message.edit_text(
            "✅ Бронь отменена. Давайте выберем новую дату.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")]
                ]
            ),
        )
        await start_booking_flow(callback.message, state, ctx)
    else:
        await callback.message.edit_text(
            "⚠️ Не удалось перенести бронь. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")]
                ]
            ),
        )
        await send_user_error(
            callback.message,
            ctx,
            "⚠️ Не удалось перенести бронь. Попробуйте позже.",
            f"reschedule cancel failed: {cancel_result}",
            "reschedule_booking",
        )

    await callback.answer()


@router.callback_query(F.data == "reviews_back")
async def action_reviews_back(callback: types.CallbackQuery, ctx: AppContext) -> None:
    await cmd_reviews(callback.message, ctx)
    await callback.answer()

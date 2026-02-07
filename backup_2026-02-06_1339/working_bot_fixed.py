import asyncio
import logging
import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import aiohttp
import pytz


# ========== УВЕДОМЛЕНИЯ АДМИНАМ ==========
async def send_admin_notification(text: str):
    """Отправка уведомления всем администраторам"""
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=int(admin_id),
                text=text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8243239133:AAEu3F0GW6gnaC8jM-1yb-Xwx-psZq1Zg2w"
GAS_WEBAPP_URL = "https://script.google.com/macros/s/AKfycbzAIULQDw_2nBavJOJCvmGvmpEwnVdGAjH9B5ziUVnVQlmLYYd8xdXogUBULlXyettRuQ/exec"
API_TOKEN = "0XZlVlDyx8gZfiiPIF97Z7hiuWybOJbE"
ADMIN_IDS = ['7793200469']
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# ========== СОСТОЯНИЯ FSM ==========
class BookingStates(StatesGroup):
    choosing_date = State()
    choosing_time = State()
    choosing_duration = State()
    getting_name = State()
    getting_phone = State()
    confirming_booking = State()

class ReviewStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_rating = State()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_tomorrow_date() -> str:
    """Получить завтрашнюю дату в формате ДД.ММ.ГГГГ"""
    tomorrow = datetime.now(MOSCOW_TZ) + timedelta(days=1)
    return tomorrow.strftime("%d.%m.%Y")

def parse_date(date_str: str) -> Tuple[Optional[datetime], Optional[str]]:
    """Парсинг даты из строки"""
    try:
        parsed_date = datetime.strptime(date_str, "%d.%m.%Y")
        parsed_date = MOSCOW_TZ.localize(parsed_date)
        
        # СРАВНИВАЕМ ТОЛЬКО ДАТЫ (без времени)
        today = datetime.now(MOSCOW_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        parsed_date_only = parsed_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        if parsed_date_only < today:
            return None, "❌ Нельзя выбрать прошедшую дату."
        
        return parsed_date, None
    except ValueError:
        return None, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ"

def calculate_price(duration_hours: int) -> int:
    """Расчет стоимости бронирования"""
    if duration_hours < 4:
        price_per_hour = 2200
    else:
        price_per_hour = 2000
    
    return price_per_hour * duration_hours

def validate_phone(phone: str) -> bool:
    """Валидация номера телефона"""
    phone_clean = re.sub(r'[\s\(\)\-+]', '', phone)
    
    # Проверка российских номеров
    patterns = [
        r'^7\d{10}$',      # 7XXXXXXXXXX
        r'^8\d{10}$',      # 8XXXXXXXXXX
        r'^\+7\d{10}$',    # +7XXXXXXXXXX
        r'^9\d{9}$',       # 9XXXXXXXXX
    ]
    
    return any(re.match(pattern, phone_clean) for pattern in patterns)

def format_phone(phone: str) -> str:
    """Форматирование телефона в единый формат"""
    phone_clean = re.sub(r'[\s\(\)\-+]', '', phone)
    
    if phone_clean.startswith('8'):
        return '7' + phone_clean[1:]
    elif phone_clean.startswith('+7'):
        return phone_clean[1:]
    elif phone_clean.startswith('9') and len(phone_clean) == 10:
        return '7' + phone_clean
    else:
        return phone_clean

def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return str(user_id) in ADMIN_IDS

def is_past_booking(date_str: str) -> bool:
    """Проверяет, прошла ли дата брони"""
    try:
        booking_date = datetime.strptime(date_str, "%d.%m.%Y")
        booking_date = MOSCOW_TZ.localize(booking_date)
        now = datetime.now(MOSCOW_TZ)
        return booking_date < now
    except:
        return False

async def call_google_script(action: str, payload: Dict) -> Dict:
    """Вызов Google Apps Script"""
    data = {
        "token": API_TOKEN,
        "action": action,
        **payload
    }
    
    logger.debug(f"Отправка в GAS: action={action}, payload={payload}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GAS_WEBAPP_URL, json=data, timeout=10) as response:
                response_text = await response.text()
                if response.status == 200:
                    try:
                        return json.loads(response_text)
                    except json.JSONDecodeError as e:
                        logger.error(f"Ошибка парсинга JSON: {e}, текст: {response_text}")
                        return {"status": "error", "message": f"Ошибка формата ответа: {e}"}
                else:
                    logger.error(f"HTTP ошибка {response.status} от GAS: {response_text}")

                    asyncio.create_task(
                        notify_admin_about_error(
                            f"HTTP {response.status}: {response_text[:100]}",
                            f"GAS action: {action}"
                        )
                    )

                    return {"status": "error", "message": f"Ошибка сервера: {response.status}"}
    except asyncio.TimeoutError:
        logger.error("Таймаут запроса к GAS")
        return {"status": "error", "message": "Сервер не отвечает. Попробуйте позже."}
    except Exception as e:
        logger.error(f"Ошибка соединения: {e}")

        asyncio.create_task(
            notify_admin_about_error(
                str(e),
                f"GAS action: {action}"
            )
        )

        return {"status": "error", "message": f"Ошибка сети: {str(e)}"}

async def get_free_slots_for_date(date_str: str) -> List[str]:
    """Получение свободных слотов на дату"""
    result = await call_google_script("get_free_slots", {"date": date_str})
    
    if result.get("status") == "success":
        return result.get("free_slots", [])
    else:
        logger.error(f"Ошибка GAS при запросе слотов: {result.get('message')}")
        return []

async def get_stats_from_gas() -> Dict:
    """Получение статистики"""
    result = await call_google_script("get_stats", {})
    
    if result.get("status") == "success":
        return {
            "success": True,
            "stats": result.get("stats", {}),
            "formatted_text": result.get("formatted_telegram", "Статистика не доступна")
        }
    else:
        return {
            "success": False,
            "error": result.get("message", "Неизвестная ошибка")
        }

async def get_report_from_gas(report_type: str, period: str = "current") -> Dict:
    """Получение отчета"""
    result = await call_google_script("get_report", {
        "report_type": report_type,
        "period": period
    })
    
    if result.get("status") == "success":
        return {
            "success": True,
            "data": result.get("data", {}),
            "formatted_text": result.get("formatted_telegram", "Отчет сформирован")
        }
    else:
        return {
            "success": False,
            "error": result.get("message", "Неизвестная ошибка")
        }

async def get_reviews_gas(public_only: bool = True, limit: int = 10, mask_names: bool = True) -> Dict:
    """Получение отзывов из GAS"""
    result = await call_google_script("get_reviews", {
        "public_only": public_only,
        "limit": limit,
        "mask_names": mask_names
    })
    return result

async def save_review_gas(record_id: str, rating: int, review_text: str = "") -> Dict:
    """Сохранение отзыва в GAS"""
    result = await call_google_script("save_review", {
        "record_id": record_id,
        "rating": rating,
        "review_text": review_text
    })
    
    if result.get("status") == "success":
        # TODO: Нужно получить user_id из контекста
        # Пока заглушка - user_id нужно будет передавать из вызывающего кода
        # await notify_admin_about_new_review(record_id, review_text, user_id, rating)
        pass
    
    return result

def format_reviews_for_telegram(result: dict) -> str:
    """Форматирование отзывов для Telegram"""
    if result.get("status") != "success":
        return "❌ Не удалось загрузить отзывы. Попробуйте позже."
    
    reviews = result.get("reviews", [])
    count = result.get("count", 0)
    avg_rating = result.get("average_rating", 0)
    
    if count == 0:
        return "⭐️ <b>Отзывы</b>\n\nНа данный момент отзывов еще нет."
    
    # Формируем текст с отзывами
    text = f"⭐️ <b>Отзывы клиентов</b>\n\n"
    text += f"📊 <b>Статистика:</b>\n"
    text += f"• Всего отзывов: {count}\n"
    try:
        avg_rating_num = float(avg_rating) if avg_rating else 0
        text += f"• Средняя оценка: {avg_rating_num:.1f}/5\n\n"
    except (ValueError, TypeError):
        text += f"• Средняя оценка: {avg_rating}/5\n\n"
    
    # Добавляем последние 5 отзывов
    for i, review in enumerate(reviews[:5], 1):
        rating = review.get('rating', 0)
        stars = "⭐" * int(rating)
        client = review.get('client_name', 'Аноним')
        comment = review.get('review_text', '')
        date = review.get('review_date', '').split()[0] if review.get('review_date') else 'Дата неизвестна'
        
        text += f"{i}. <b>{client}</b> {stars} ({rating}/5)\n"
        if comment:
            if len(comment) > 60:
                text += f"   <i>\"{comment[:60]}...\"</i>\n"
            else:
                text += f"   <i>\"{comment}\"</i>\n"
        text += f"   📅 {date}\n\n"
    
    return text


async def notify_admin_about_cancellation(record_id: str, booking_data: dict, user_id: int, reason: str = "пользователем"):
    """Уведомление админа об отмене брони"""
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
    
    await send_admin_notification(message_text)


async def notify_admin_about_payment_confirmation(record_id: str, client_name: str, admin_id: int):
    """Уведомление другим админам о подтверждении оплаты"""
    message_text = (
        f"💰 <b>ОПЛАТА ПОДТВЕРЖДЕНА</b>\n\n"
        f"📋 ID записи: <code>{record_id}</code>\n"
        f"👤 Клиент: {client_name}\n"
        f"👑 Подтвердил: Администратор ID: {admin_id}\n"
        f"⏰ Время: {datetime.now(MOSCOW_TZ).strftime('%H:%M %d.%m.%Y')}"
    )
    
    # Отправляем всем админам, кроме того кто подтвердил
    for admin in ADMIN_IDS:
        if int(admin) != admin_id:
            try:
                await bot.send_message(
                    chat_id=int(admin),
                    text=message_text,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления админу {admin}: {e}")



async def notify_admin_about_new_booking(booking_data: Dict, record_id: str, user_id: int):
    """Уведомление админа о новой брони"""
    message_text = (
        f"🆕 <b>НОВАЯ БРОНЬ!</b>\n\n"
        f"📅 Дата: {booking_data['date']}\n"
        f"🕐 Время: {booking_data['time']}\n"
        f"👤 Клиент: {booking_data['name']}\n"
        f"📞 Телефон: {booking_data['phone']}\n"
        f"👤 ID клиента: {user_id}\n"
        f"📋 ID записи: <code>{record_id}</code>"
    )
    
    # Используем новую функцию
    await send_admin_notification(message_text)
    
    # Оставляем старую логику с кнопкой подтверждения
    confirm_button = InlineKeyboardButton(
        text="✅ Подтвердить оплату",
        callback_data=f"confirm_{record_id}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[confirm_button]])
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=int(admin_id),
                text=message_text + "\n\nИспользуйте /admin для подтверждения оплаты",
                parse_mode="HTML",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")

async def notify_admin_about_new_review(record_id: str, review_text: str, user_id: int, rating: int = 0):
    """Уведомление админа о новом отзыве"""
    stars = "⭐" * rating if rating else ""
    message_text = (
        f"⭐ <b>НОВЫЙ ОТЗЫВ {stars}</b>\n\n"
        f"📋 ID брони: <code>{record_id}</code>\n"
        f"👤 ID клиента: {user_id}\n"
        f"⭐ Оценка: {rating}/5\n"
        f"💬 Отзыв: {review_text[:200] if review_text else 'Без текста'}..."
    )
    
    await send_admin_notification(message_text)


async def notify_admin_about_error(error_message: str, context: str = ""):
    """Уведомление админа об ошибке в системе"""
    message_text = (
        f"🚨 <b>ОШИБКА В СИСТЕМЕ</b>\n\n"
        f"🕐 Время: {datetime.now(MOSCOW_TZ).strftime('%H:%M %d.%m.%Y')}\n"
        f"📝 Контекст: {context}\n"
        f"💥 Ошибка: {error_message[:500]}"
    )
    
    await send_admin_notification(message_text)



@dp.message(Command("test_notify"))
async def cmd_test_notify(message: types.Message):
    """Тест уведомлений (только для админов)"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админов")
        return
    
    test_messages = [
        "🆕 Тест: Новая бронь",
        "❌ Тест: Отмена брони", 
        "💰 Тест: Подтверждение оплаты",
        "⭐ Тест: Новый отзыв",
        "🚨 Тест: Ошибка системы"
    ]
    
    for msg in test_messages:
        await send_admin_notification(f"🔔 {msg}\n⏰ {datetime.now(MOSCOW_TZ).strftime('%H:%M')}")
        await asyncio.sleep(1)
    
    await message.answer("✅ Тестовые уведомления отправлены!")


# ========== КОМАНДЫ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    """Обработка команды /start"""
    await state.clear()
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Новое бронирование")],
            [KeyboardButton(text="⭐ Отзывы клиентов")],
            [KeyboardButton(text="❓ Помощь и инструкции")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "👋 Добро пожаловать в бот бронирования коворкинга!\n"
        "Минимальное время аренды - 1 час. Слоты по 2 часа.\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Помощь и инструкции для всех пользователей"""
    help_text = (
        "🤖 <b>Бот для бронирования коворкинга</b>\n\n"
        
        "<b>📋 Основные команды:</b>\n"
        "• /start - Начало работы\n"
        "• /help - Эта справка\n"
        "• /my_bookings - Мои брони\n"
        "• /today - Мои брони на сегодня\n"
        "• /reviews - Посмотреть отзывы\n"
        "• Отмена: свяжитесь с администратором\n\n"
        
        "<b>👑 Команды для администраторов:</b>\n"
        "• /admin - Админ-панель\n"
        "• /stats - Статистика\n"
        "• /test - Тест подключения\n"
        "• /confirm ID - Подтвердить оплату\n\n"
        
        "<b>📞 Контакты:</b>\n"
        "• Телефон: [ваш телефон]\n"
        "• Адрес: [ваш адрес]\n"
        "• Время работы: 10:00 - 22:00\n\n"
        
        "<b>❓ Частые вопросы:</b>\n"
        "• Минимальное время брони: 1 час\n"
        "• Оплата: при посещении\n"
        "• Отмена: бесплатно за 24 часа"
    )
    
    await message.answer(help_text, parse_mode="HTML")

@dp.message(Command("my_bookings"))
async def cmd_my_bookings(message: types.Message):
    """Показать брони пользователя"""
    user_id = message.from_user.id
    
    # Получаем брони пользователя
    result = await call_google_script("get_user_bookings", {
        "user_id": user_id,
        "active_only": False
    })
    
    if result.get("status") == "success":
        bookings = result.get("bookings", [])
        
        if not bookings:
            await message.answer("📭 У вас еще нет броней.")
            return
        
        response = "📋 <b>Ваши брони</b>\n\n"
        
        for i, booking in enumerate(bookings[:10], 1):
            status_emoji = "✅" if booking.get('status') == 'Оплачено' else "⏳"
            response += f"{i}. {status_emoji} <b>{booking.get('date')} {booking.get('time')}</b>\n"
            response += f"   Статус: {booking.get('status')}\n"
            if booking.get('price'):
                response += f"   Цена: {booking.get('price')} ₽\n"
            
            # Проверяем, можно ли оставить отзыв
            if (booking.get('status') == 'Оплачено' and 
                is_past_booking(booking.get('date'))):
                # Получаем username бота
                bot_info = await bot.get_me()
                response += f"   📝 [Оставить отзыв](https://t.me/{bot_info.username}?start=review_{booking.get('id')})\n"
            
            response += "\n"
        
        await message.answer(response, parse_mode="HTML")
    else:
        await message.answer(f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}")

@dp.message(Command("reviews"))
async def cmd_reviews(message: types.Message):
    """Обработка команды /reviews"""
    await message.answer("📖 Загружаю отзывы...")
    
    result = await get_reviews_gas(public_only=True, limit=10, mask_names=True)
    
    if result.get("status") == "success":
        reviews_text = format_reviews_for_telegram(result)
        
        keyboard_buttons = []
        
        if is_admin(message.from_user.id):
            keyboard_buttons.append([
                InlineKeyboardButton(text="📊 Все отзывы (админ)", callback_data="admin_all_reviews"),
                InlineKeyboardButton(text="📈 Статистика", callback_data="admin_review_stats")
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data="leave_review_info"),
            InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await message.answer(
            reviews_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            f"❌ Ошибка загрузки отзывов:\n{result.get('message', 'Попробуйте позже')}",
            parse_mode="HTML"
        )

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Брони на сегодня", callback_data="admin_view_today"),
                InlineKeyboardButton(text="📅 Брони на завтра", callback_data="admin_view_tomorrow")
            ],
            [
                InlineKeyboardButton(text="📊 Отчеты", callback_data="report_menu"),
                InlineKeyboardButton(text="📈 Статистика", callback_data="admin_stats")
            ],
            [
                InlineKeyboardButton(text="🔄 Автоотмена", callback_data="admin_auto_cancel"),
                InlineKeyboardButton(text="🔔 Напоминания", callback_data="admin_send_reminders")
            ],
            [
                InlineKeyboardButton(text="⭐ Отзывы (админ)", callback_data="admin_all_reviews"),
                InlineKeyboardButton(text="❓ Помощь", callback_data="admin_help")
            ],
            [
                InlineKeyboardButton(text="🚪 Выйти", callback_data="main_menu")
            ]
        ]
    )
    
    await message.answer(
        "👑 <b>Админ-панель</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.message(Command("confirm"))
async def cmd_confirm(message: types.Message):
    """Подтверждение оплаты администратором"""
    if not is_admin(message.from_user.id):
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
    
    result = await call_google_script("confirm_payment", {
        "record_id": record_id,
        "admin_id": str(message.from_user.id)
    })
    
    if result.get("status") == "success":
        if result.get("already_confirmed"):
            await message.answer(f"✅ Оплата уже была подтверждена ранее")
        else:
            await message.answer(
                f"✅ <b>Оплата подтверждена!</b>\n\n"
                f"📋 ID: <code>{record_id}</code>\n"
                f"👤 Клиент: {result.get('client_name', 'Неизвестно')}\n"
                f"📅 Дата: {result.get('booking_date', 'Неизвестно')}\n"
                f"🕐 Время: {result.get('booking_time', 'Неизвестно')}",
                parse_mode="HTML"
            )
    else:
        await message.answer(f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Обработка команды /stats"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к статистике.")
        return
    
    loading_msg = await message.answer("📊 Запрашиваю статистику...")
    
    result = await get_stats_from_gas()
    
    try:
        await bot.delete_message(message.chat.id, loading_msg.message_id)
    except:
        pass
    
    if result["success"]:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📊 Подробный отчет", callback_data="report_detailed_current")],
                [InlineKeyboardButton(text="↩️ В админ-панель", callback_data="admin_back")]
            ]
        )
        
        await message.answer(
            result["formatted_text"],
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}",
            parse_mode="HTML"
        )

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Тест подключения к GAS"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админов")
        return
    
    await message.answer("🔗 Тестирую подключение к GAS...")
    
    try:
        result = await call_google_script("test_connection", {})
        
        if result.get("status") == "success":
            await message.answer(
                f"✅ <b>Подключение работает!</b>\n\n"
                f"Сервер: <code>{GAS_WEBAPP_URL}</code>\n"
                f"Статус: {result.get('message', 'OK')}\n"
                f"Время: {result.get('timestamp', 'N/A')}",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"❌ <b>Ошибка подключения</b>\n\n"
                f"{result.get('message', 'Нет ответа от сервера')}",
                parse_mode="HTML"
            )
    except Exception as e:
        await message.answer(
            f"🔥 <b>Критическая ошибка:</b>\n\n<code>{str(e)}</code>",
            parse_mode="HTML"
        )

@dp.message(Command("myid"))
async def cmd_myid(message: types.Message):
    """Показать ID пользователя"""
    await message.answer(
        f"👤 <b>Ваши данные:</b>\n\n"
        f"ID пользователя: <code>{message.from_user.id}</code>\n"
        f"Username: @{message.from_user.username or 'нет'}\n"
        f"Имя: {message.from_user.first_name or 'не указано'}\n"
        f"Чат ID: <code>{message.chat.id}</code>\n"
        f"Тип чата: {message.chat.type}\n\n"
        f"Являетесь админом: {'✅ Да' if is_admin(message.from_user.id) else '❌ Нет'}",
        parse_mode="HTML"
    )

# ========== ОБРАБОТКА КНОПОК ГЛАВНОГО МЕНЮ ==========
@dp.message(F.text == "🔄 Новое бронирование")
async def new_booking(message: types.Message, state: FSMContext):
    """Начало нового бронирования"""
    await state.clear()
    
    tomorrow = get_tomorrow_date()
    await message.answer(
        f"📅 <b>ШАГ 1 из 7: Выберите дату</b>\n\n"
        f"Введите дату в формате <b>ДД.ММ.ГГГГ</b>\n"
        f"<i>Например: {tomorrow}</i>",
        parse_mode="HTML",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(BookingStates.choosing_date)

@dp.message(F.text == "⭐ Отзывы клиентов")
async def handle_reviews_button(message: types.Message):
    """Обработка кнопки отзывов"""
    await cmd_reviews(message)

@dp.message(F.text == "❓ Помощь и инструкции")
async def handle_help(message: types.Message):
    """Обработка кнопки помощи"""
    await cmd_help(message)

# ========== ПРОЦЕСС БРОНИРОВАНИЯ ==========
@dp.message(BookingStates.choosing_date)
async def process_date(message: types.Message, state: FSMContext):
    """Обработка выбора даты"""
    date_str = message.text.strip()
    parsed_date, error = parse_date(date_str)
    
    if error:
        tomorrow = get_tomorrow_date()
        await message.answer(
            f"{error}\n\nВведите дату в формате <b>ДД.ММ.ГГГГ</b>\n<i>Например: {tomorrow}</i>",
            parse_mode="HTML"
        )
        return
    
    await state.update_data(booking_date=parsed_date, date_str=date_str)
    
    await message.answer(
        f"📅 Дата: <b>{date_str}</b>\n🔍 <i>Ищу свободное время...</i>",
        parse_mode="HTML"
    )
    
    free_slots = await get_free_slots_for_date(date_str)
    
    if not free_slots:
        await message.answer(
            f"❌ На <b>{date_str}</b> нет свободных слотов.\n\nВыберите другую дату.",
            parse_mode="HTML"
        )
        await state.set_state(BookingStates.choosing_date)
        return
    
    await state.update_data(free_slots=free_slots)
    
    keyboard_buttons = []
    row = []
    for i, slot in enumerate(free_slots):
        row.append(KeyboardButton(text=slot))
        if len(row) == 3 or i == len(free_slots) - 1:
            keyboard_buttons.append(row)
            row = []
    
    keyboard = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
    
    await message.answer(
        f"📅 Дата: <b>{date_str}</b>\n"
        f"🕐 <b>ШАГ 2 из 7: Выберите свободное время</b>\n\n"
        f"Доступные слоты:",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.set_state(BookingStates.choosing_time)

@dp.message(BookingStates.choosing_time)
async def process_time(message: types.Message, state: FSMContext):
    """Обработка выбора времени"""
    selected_slot = message.text.strip()
    
    data = await state.get_data()
    free_slots = data.get('free_slots', [])
    date_str = data.get('date_str', '')
    
    if selected_slot not in free_slots:
        # Обновляем список слотов
        current_free_slots = await get_free_slots_for_date(date_str)
        
        if selected_slot in current_free_slots:
            await state.update_data(free_slots=current_free_slots)
            free_slots = current_free_slots
        else:
            await message.answer("❌ Этот слот только что заняли! Выбирайте из доступных:")
            await state.update_data(free_slots=current_free_slots)
            free_slots = current_free_slots
            
            if current_free_slots:
                keyboard_buttons = []
                row = []
                for i, slot in enumerate(current_free_slots):
                    row.append(KeyboardButton(text=slot))
                    if len(row) == 3 or i == len(current_free_slots) - 1:
                        keyboard_buttons.append(row)
                        row = []
                
                keyboard = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
                
                await message.answer(
                    f"📅 Дата: <b>{date_str}</b>\n🕐 Обновленные слоты:",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                await message.answer(
                    f"❌ На <b>{date_str}</b> больше нет свободных слотов.",
                    parse_mode="HTML"
                )
                await state.set_state(BookingStates.choosing_date)
            return
    
    start_time = selected_slot.split('-')[0]
    
    await state.update_data(selected_slot=selected_slot, start_time=start_time)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1 час"), KeyboardButton(text="2 часа"), KeyboardButton(text="3 часа")],
            [KeyboardButton(text="4 часа"), KeyboardButton(text="5 часов"), KeyboardButton(text="6 часов")],
            [KeyboardButton(text="↩️ Назад ко времени")],
            [KeyboardButton(text="🔄 Начать заново")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"🕐 Слот: <b>{selected_slot}</b>\n"
        f"⏱️ <b>ШАГ 3 из 7: Выберите длительность</b>\n\n"
        f"<i>Тарифы:</i>\n• До 4 часов: 2200 руб/час\n• От 4 часов: 2000 руб/час\n\n"
        f"Минимум - 1 час",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.set_state(BookingStates.choosing_duration)

@dp.message(BookingStates.choosing_duration)
async def process_duration(message: types.Message, state: FSMContext):
    """Обработка выбора длительности"""
    duration_text = message.text.strip()
    
    if duration_text == "↩️ Назад ко времени":
        data = await state.get_data()
        free_slots = data.get('free_slots', [])
        date_str = data.get('date_str', '')
        
        if free_slots:
            keyboard_buttons = []
            row = []
            for i, slot in enumerate(free_slots):
                row.append(KeyboardButton(text=slot))
                if len(row) == 3 or i == len(free_slots) - 1:
                    keyboard_buttons.append(row)
                    row = []
            
            keyboard = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
            
            await message.answer(
                f"📅 Дата: <b>{date_str}</b>\n🕐 Выберите время:",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            await state.set_state(BookingStates.choosing_time)
        else:
            await message.answer("❌ Нет доступных слотов. Начнем заново.")
            await new_booking(message, state)
        return
    
    if duration_text == "🔄 Начать заново":
        await new_booking(message, state)
        return
    
    duration_map = {
        "1 час": 1, "2 часа": 2, "3 часа": 3,
        "4 часа": 4, "5 часов": 5, "6 часов": 6
    }
    
    if duration_text not in duration_map:
        await message.answer("❌ Выберите длительность из предложенных вариантов")
        return
    
    duration_hours = duration_map[duration_text]
    price = calculate_price(duration_hours)
    
    await state.update_data(duration_hours=duration_hours, duration_text=duration_text, price=price)
    
    data = await state.get_data()
    start_time = data.get('start_time', '')
    end_hour = int(start_time.split(':')[0]) + duration_hours
    
    await message.answer(
        f"✅ Длительность: <b>{duration_text}</b>\n"
        f"💰 Стоимость: <b>{price} руб.</b>\n"
        f"🕒 Время: <b>{start_time} - {end_hour:02d}:00</b>\n\n"
        f"📝 <b>ШАГ 4 из 7: Введите ваше имя</b>\n\n"
        f"<i>Например: Иван Иванов</i>",
        parse_mode="HTML",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(BookingStates.getting_name)

@dp.message(BookingStates.getting_name)
async def process_name(message: types.Message, state: FSMContext):
    """Обработка ввода имени"""
    name = message.text.strip()
    
    if len(name) < 2:
        await message.answer("❌ Имя слишком короткое. Введите имя (минимум 2 символа):")
        return
    
    await state.update_data(client_name=name)
    
    request_phone_button = KeyboardButton(
        text="📱 Отправить мой телефон",
        request_contact=True
    )
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [request_phone_button],
            [KeyboardButton(text="↩️ Изменить имя")],
            [KeyboardButton(text="🔄 Начать заново")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"👤 Имя: <b>{name}</b>\n\n"
        f"📞 <b>ШАГ 5 из 7: Введите ваш телефон</b>\n\n"
        f"Можете отправить контакт кнопкой ниже\n"
        f"<i>Или введите вручную (например: 89991234567)</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.set_state(BookingStates.getting_phone)

@dp.message(BookingStates.getting_phone, F.content_type.in_({'contact', 'text'}))
async def process_phone(message: types.Message, state: FSMContext):
    """Обработка ввода телефона"""
    phone = None
    
    if message.contact:
        phone = message.contact.phone_number
    elif message.text:
        text = message.text.strip()
        
        if text == "↩️ Изменить имя":
            await message.answer("📝 Введите ваше имя (например: Иван Иванов):")
            await state.set_state(BookingStates.getting_name)
            return
        
        if text == "🔄 Начать заново":
            await new_booking(message, state)
            return
        
        phone = text
    
    if not phone:
        await message.answer("❌ Не удалось получить номер телефона. Попробуйте еще раз:")
        return
    
    if not validate_phone(phone):
        await message.answer(
            "❌ Неверный формат телефона.\n\n"
            "Используйте российский номер:\n"
            "• 89991234567\n"
            "• +79991234567\n"
            "• 9991234567\n\n"
            "Попробуйте еще раз:"
        )
        return
    
    formatted_phone = format_phone(phone)
    await state.update_data(client_phone=formatted_phone)
    
    data = await state.get_data()
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="✅ Подтвердить бронирование"),
                KeyboardButton(text="❌ Отменить")
            ],
            [KeyboardButton(text="↩️ Изменить телефон")],
            [KeyboardButton(text="🔄 Начать заново")]
        ],
        resize_keyboard=True
    )
    
    start_time = data.get('start_time', '')
    duration_hours = data.get('duration_hours', 1)
    end_hour = int(start_time.split(':')[0]) + duration_hours
    
    await message.answer(
        f"📋 <b>ШАГ 6 из 7: Итог бронирования</b>\n\n"
        f"📅 Дата: <b>{data.get('date_str', '')}</b>\n"
        f"🕐 Время: <b>{start_time} - {end_hour:02d}:00</b>\n"
        f"⏱️ Длительность: <b>{data.get('duration_text', '')}</b>\n"
        f"👤 Имя: <b>{data.get('client_name', '')}</b>\n"
        f"📞 Телефон: <b>{formatted_phone}</b>\n"
        f"💰 Стоимость: <b>{data.get('price', 0)} руб.</b>\n\n"
        f"<i>Проверьте данные. Всё верно?</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.set_state(BookingStates.confirming_booking)

@dp.message(BookingStates.confirming_booking)
async def process_confirmation(message: types.Message, state: FSMContext):
    """Обработка подтверждения бронирования"""
    user_choice = message.text.strip()
    
    if user_choice == "✅ Подтвердить бронирование":
        data = await state.get_data()
        
        await message.answer("📝 Отправляю данные на сервер...", parse_mode="HTML")
        
        booking_data = {
            "date": data.get('date_str', ''),
            "time": data.get('selected_slot', ''),
            "name": data.get('client_name', ''),
            "phone": data.get('client_phone', ''),
            "user_id": str(message.from_user.id)
        }
        
        result = await call_google_script("create_booking", booking_data)
        
        if result.get("status") == "success":
            record_id = result.get("record_id", "")
            
            start_time = data.get('start_time', '')
            duration_hours = data.get('duration_hours', 1)
            end_hour = int(start_time.split(':')[0]) + duration_hours
            
            await message.answer(
                f"🎉 <b>Бронирование успешно создано!</b>\n\n"
                f"📅 {data.get('date_str', '')}\n"
                f"🕐 {start_time} - {end_hour:02d}:00\n"
                f"⏱️ {data.get('duration_text', '')}\n"
                f"👤 {data.get('client_name', '')}\n"
                f"💰 {data.get('price', 0)} руб.\n\n"
                f"📋 ID брони: <code>{record_id}</code>\n\n"
                f"✅ Администратор получил уведомление.",
                parse_mode="HTML",
                reply_markup=types.ReplyKeyboardRemove()
            )
            
            logger.info(f"Создана бронь: {booking_data}, ID: {record_id}")
            
            await notify_admin_about_new_booking(booking_data, record_id, message.from_user.id)
            
        else:
            error_msg = result.get("message", "Неизвестная ошибка")
            await message.answer(
                f"❌ <b>Ошибка при создании брони:</b>\n\n{error_msg}\n\nПопробуйте снова.",
                parse_mode="HTML",
                reply_markup=types.ReplyKeyboardRemove()
            )
        
        await state.clear()
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🔄 Новое бронирование")]
            ],
            resize_keyboard=True
        )
        await message.answer("Хотите создать новое бронирование?", reply_markup=keyboard)
        
    elif user_choice == "❌ Отменить":
        await message.answer("❌ Бронирование отменено.", reply_markup=types.ReplyKeyboardRemove())
        await state.clear()
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🔄 Новое бронирование")]
            ],
            resize_keyboard=True
        )
        await message.answer("Хотите создать новое бронирование?", reply_markup=keyboard)
        
    elif user_choice == "↩️ Изменить телефон":
        request_phone_button = KeyboardButton(
            text="📱 Отправить мой телефон",
            request_contact=True
        )
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [request_phone_button],
                [KeyboardButton(text="↩️ Изменить имя")],
                [KeyboardButton(text="🔄 Начать заново")]
            ],
            resize_keyboard=True
        )
        
        data = await state.get_data()
        
        await message.answer(
            f"📞 <b>Измените телефон</b>\n\n"
            f"Текущий: {data.get('client_phone', 'не указан')}\n\n"
            f"Можете отправить контакт кнопкой ниже\n"
            f"<i>Или введите вручную (например: 89991234567)</i>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await state.set_state(BookingStates.getting_phone)
        return
        
    elif user_choice == "🔄 Начать заново":
        await new_booking(message, state)
        return
    
    else:
        await message.answer("Пожалуйста, выберите действие из предложенных вариантов")
        return



# ========== ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ ==========
@dp.message(Command("today_bookings"))
async def cmd_today_bookings(message: types.Message):
    """Брони на сегодня (для админов и пользователей)"""
    user_id = message.from_user.id
    
    if is_admin(user_id):
        # Для админа - полный список броней на сегодня
        result = await call_google_script("get_today_bookings", {})
        
        if result.get("status") == "success":
            bookings = result.get("bookings", [])
            
            if not bookings:
                await message.answer("📭 На сегодня броней нет.")
                return
            
            response = "📋 <b>Брони на сегодня</b>\n\n"
            
            for i, booking in enumerate(bookings, 1):
                status_emoji = "✅" if booking.get('status') == 'Оплачено' else "⏳"
                response += f"{i}. {status_emoji} <b>{booking.get('time')}</b>\n"
                response += f"   👤 {booking.get('name')}\n"
                response += f"   📞 {booking.get('phone')}\n"
                response += f"   💰 {booking.get('price')} ₽\n"
                response += f"   🆔 {booking.get('id')}\n\n"
            
            await message.answer(response, parse_mode="HTML")
        else:
            await message.answer(f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}")
    
    else:
        # Для обычного пользователя - только его брони на сегодня
        result = await call_google_script("get_user_bookings", {
            "user_id": user_id,
            "active_only": True
        })
        
        if result.get("status") == "success":
            bookings = result.get("bookings", [])
            
            # Фильтруем только сегодняшние брони
            today = datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y")
            today_bookings = [b for b in bookings if b.get('date') == today]
            
            if not today_bookings:
                await message.answer("📭 У вас нет броней на сегодня.")
                return
            
            response = "📋 <b>Ваши брони на сегодня</b>\n\n"
            
            for i, booking in enumerate(today_bookings, 1):
                status_emoji = "✅" if booking.get('status') == 'Оплачено' else "⏳"
                response += f"{i}. {status_emoji} <b>{booking.get('time')}</b>\n"
                response += f"   Статус: {booking.get('status')}\n"
                if booking.get('price'):
                    response += f"   Цена: {booking.get('price')} ₽\n"
                response += f"   🆔 {booking.get('id')}\n\n"
            
            await message.answer(response, parse_mode="HTML")
        else:
            await message.answer(f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}")

@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message):
    """Отмена бронирования"""
    args = message.text.split()
    
    if len(args) < 2:
        # Показываем инструкцию
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
    
    # Проверяем существование брони и права пользователя
    result = await call_google_script("get_user_bookings", {
        "user_id": user_id,
        "active_only": False
    })
    
    if result.get("status") != "success":
        await message.answer(f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}")
        return
    
    bookings = result.get("bookings", [])
    user_booking = next((b for b in bookings if b.get('id') == record_id), None)
    
    if not user_booking:
        # Проверяем, может админ пытается отменить
        if is_admin(user_id):
            # Для админа - можно отменить любую бронь
            await cancel_booking_by_admin(message, record_id, user_id)
            return
        else:
            await message.answer("❌ Бронь не найдена или у вас нет прав для её отмены.")
            return
    
    # Проверяем статус брони
    if user_booking.get('status') == 'Оплачено':
        await message.answer(
            "⚠️ <b>Оплаченные брони нельзя отменить через бота.</b>\n\n"
            "Пожалуйста, свяжитесь с администратором:\n"
            "📞 Телефон: [ваш телефон]",
            parse_mode="HTML"
        )
        return
    
    # Отменяем бронь
    cancel_result = await call_google_script("cancel_booking", {
        "record_id": record_id,
        "user_id": str(user_id)
    })
    
    if cancel_result.get("status") == "success":
        await message.answer(
            f"✅ <b>Бронь отменена!</b>\n\n"
            f"ID: <code>{record_id}</code>\n"
            f"Дата: {user_booking.get('date', 'Неизвестно')}\n"
            f"Время: {user_booking.get('time', 'Неизвестно')}\n\n"
            f"Деньги не списывались, так как бронь не была оплачена.",
            parse_mode="HTML"
        )

        await notify_admin_about_cancellation(
            record_id, 
            user_booking, 
            message.from_user.id,
            "пользователем"
        )
        
        # Уведомляем админа
        await notify_admin_about_cancellation(record_id, user_booking, user_id)
        
    else:
        await message.answer(f"❌ Ошибка отмены: {cancel_result.get('message', 'Неизвестная ошибка')}")

async def cancel_booking_by_admin(message: types.Message, record_id: str, admin_id: int):
    """Отмена брони администратором"""
    # Сначала получаем информацию о брони
    # (нужно добавить функцию get_booking_by_id в GAS)
    booking_info = await call_google_script("get_booking_info", {
        "record_id": record_id
    })
    
    if booking_info.get("status") != "success":
        await message.answer(f"❌ Бронь не найдена: {record_id}")
        return
    
    # Отменяем бронь
    cancel_result = await call_google_script("cancel_booking", {
        "record_id": record_id,
        "admin_id": str(admin_id),
        "force": True
    })
    
    if cancel_result.get("status") == "success":
        client_name = booking_info.get('client_name', 'Неизвестно')
        booking_date = booking_info.get('booking_date', 'Неизвестно')
        booking_time = booking_info.get('booking_time', 'Неизвестно')
        
        await message.answer(
            f"✅ <b>Бронь отменена администратором</b>\n\n"
            f"ID: <code>{record_id}</code>\n"
            f"👤 Клиент: {client_name}\n"
            f"📅 Дата: {booking_date}\n"
            f"🕐 Время: {booking_time}\n\n"
            f"Отменено администратором ID: {admin_id}",
            parse_mode="HTML"
        )
        
        # Уведомляем клиента если был статус "Оплачено"
        if booking_info.get('status') == 'YES' and booking_info.get('client_chat_id'):
            try:
                await bot.send_message(
                    chat_id=int(booking_info['client_chat_id']),
                    text=f"⚠️ <b>Ваша бронь отменена</b>\n\n"
                         f"📅 Дата: {booking_date}\n"
                         f"🕐 Время: {booking_time}\n\n"
                         f"Бронь отменена администратором.\n"
                         f"По вопросам возврата средств свяжитесь с нами.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления клиента об отмене: {e}")
    else:
        await message.answer(f"❌ Ошибка отмены: {cancel_result.get('message', 'Неизвестная ошибка')}")

async def notify_admin_about_cancellation(record_id: str, booking_data: dict, user_id: int):
    """Уведомление админа об отмене брони"""
    message_text = (
        f"❌ <b>ОТМЕНА БРОНИ</b>\n\n"
        f"📅 Дата: {booking_data.get('date', 'Неизвестно')}\n"
        f"🕐 Время: {booking_data.get('time', 'Неизвестно')}\n"
        f"👤 Клиент: {booking_data.get('name', 'Неизвестно')}\n"
        f"📞 Телефон: {booking_data.get('phone', 'Неизвестно')}\n"
        f"👤 ID клиента: {user_id}\n"
        f"📋 ID записи: <code>{record_id}</code>"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=int(admin_id),
                text=message_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")


# ========== КОМАНДЫ ДЛЯ БУРГЕР-МЕНЮ ==========

@dp.message(Command("today"))
async def cmd_today(message: types.Message):
    """Команда /today - брони на сегодня"""
    await cmd_today_bookings(message)  # Используем существующую функцию

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Команда /help - помощь (уже есть, но убедитесь)"""
    help_text = (
        "🤖 <b>Бот для бронирования коворкинга</b>\n\n"
        
        "<b>📋 Основные команды:</b>\n"
        "• /start - Начало работы\n"
        "• /help - Эта справка\n"
        "• /my_bookings - Мои брони\n"
        "• /today - Брони на сегодня\n"
        "• /reviews - Посмотреть отзывы\n"
        "• /cancel - Отменить бронирование\n\n"
        
        "<b>👑 Команды для администраторов:</b>\n"
        "• /admin - Админ-панель\n"
        "• /stats - Статистика\n"
        "• /test - Тест подключения\n"
        "• /confirm ID - Подтвердить оплату\n\n"
        
        "<b>📞 Контакты:</b>\n"
        "• Телефон: [ваш телефон]\n"
        "• Адрес: [ваш адрес]\n"
        "• Время работы: 10:00 - 22:00"
    )
    
    await message.answer(help_text, parse_mode="HTML")

# Команды /start, /my_bookings, /reviews, /admin, /stats, /test, /myid уже есть

# ========== ОБРАБОТКА КНОПОК БУРГЕР-МЕНЮ ==========
@dp.message(F.text == "Брони на сегодня")
async def handle_today_bookings_button(message: types.Message):
    """Обработка кнопки 'Брони на сегодня' из бургер-меню"""
    await cmd_today_bookings(message)

@dp.message(F.text == "Отменить бронирование")
async def handle_cancel_button(message: types.Message):
    """Обработка кнопки 'Отменить бронирование' из бургер-меню"""
    # Показываем инструкцию
    help_text = (
        "❌ <b>Отмена бронирования</b>\n\n"
        "Чтобы отменить бронь:\n"
        "1. Посмотрите ID брони через <code>/my_bookings</code>\n"
        "2. Используйте команду: <code>/cancel [ID_брони]</code>\n\n"
        "Пример: <code>/cancel ID_ABC123</code>"
    )
    await message.answer(help_text, parse_mode="HTML")

@dp.message(F.text == "Статистика")
async def handle_stats_button(message: types.Message):
    """Обработка кнопки 'Статистика' из бургер-меню"""
    await cmd_stats(message)


# ========== ОБНОВИТЬ ОБРАБОТКУ КОМАНДЫ /STATS ==========
@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Обработка команды /stats"""
    if not is_admin(message.from_user.id):
        # Для обычных пользователей показываем другое сообщение
        await message.answer(
            "📊 <b>Статистика</b>\n\n"
            "Статистика доступна только администраторам.\n\n"
            "Для просмотра своих броней используйте:\n"
            "• <code>/my_bookings</code>\n"
            "• Или кнопку 'Мои брони' в меню",
            parse_mode="HTML"
        )
        return
    
    loading_msg = await message.answer("📊 Запрашиваю статистику...")
    
    result = await get_stats_from_gas()
    
    try:
        await bot.delete_message(message.chat.id, loading_msg.message_id)
    except:
        pass
    
    if result["success"]:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📊 Подробный отчет", callback_data="report_detailed_current")],
                [InlineKeyboardButton(text="↩️ В админ-панель", callback_data="admin_back")]
            ]
        )
        
        await message.answer(
            result["formatted_text"],
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}",
            parse_mode="HTML"
        )


# ========== ОБРАБОТКА КОЛБЭКОВ ==========
@dp.callback_query(F.data == "main_menu")
async def handle_main_menu(callback: types.CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Новое бронирование")],
            [KeyboardButton(text="⭐ Отзывы клиентов")],
            [KeyboardButton(text="❓ Помощь и инструкции")]
        ],
        resize_keyboard=True
    )
    
    await callback.message.answer(
        "👋 Добро пожаловать в бот бронирования коворкинга!\n"
        "Минимальное время аренды - 1 час. Слоты по 2 часа.\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data == "leave_review_info")
async def action_leave_review_info(callback: types.CallbackQuery):
    """Информация о том, как оставить отзыв"""
    info_text = (
        "⭐️ <b>Как оставить отзыв?</b>\n\n"
        "Отзыв можно оставить только после посещения коворкинга.\n\n"
        "<b>Способ 1:</b> Автоматически\n"
        "• После посещения бот автоматически спросит ваш отзыв\n"
        "• Ответьте на сообщение бота с предложением оценить\n\n"
        "<b>Способ 2:</b> Через бота\n"
        "• Используйте команду /my_bookings\n"
        "• Выберите завершенную бронь\n"
        "• Нажмите \"Оставить отзыв\"\n\n"
        "<b>Обратите внимание:</b>\n"
        "• Можно оценить от 1 до 5 звезд\n"
        "• Можно добавить текстовый комментарий\n"
        "• Отзывы проходят модерацию"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои брони", callback_data="my_bookings_callback")],
        [InlineKeyboardButton(text="↩️ Назад к отзывам", callback_data="reviews_back")]
    ])
    
    await callback.message.edit_text(info_text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "my_bookings_callback")
async def action_my_bookings_callback(callback: types.CallbackQuery):
    """Показать брони пользователя через колбэк"""
    user_id = callback.from_user.id
    
    result = await call_google_script("get_user_bookings", {
        "user_id": user_id,
        "active_only": False
    })
    
    if result.get("status") == "success":
        bookings = result.get("bookings", [])
        
        if not bookings:
            await callback.message.answer("📭 У вас еще нет броней.")
            await callback.answer()
            return
        
        response = "📋 <b>Ваши брони</b>\n\n"
        
        for i, booking in enumerate(bookings[:10], 1):
            status_emoji = "✅" if booking.get('status') == 'Оплачено' else "⏳"
            response += f"{i}. {status_emoji} <b>{booking.get('date')} {booking.get('time')}</b>\n"
            response += f"   Статус: {booking.get('status')}\n"
            if booking.get('price'):
                response += f"   Цена: {booking.get('price')} ₽\n"
            
            if (booking.get('status') == 'Оплачено' and 
                is_past_booking(booking.get('date'))):
                response += f"   [📝 Оставить отзыв](https://t.me/{bot.username}?start=review_{booking.get('id')})\n"
            
            response += "\n"
        
        await callback.message.answer(response, parse_mode="HTML")
    else:
        await callback.message.answer(f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}")
    
    await callback.answer()

@dp.callback_query(F.data == "reviews_back")
async def action_reviews_back(callback: types.CallbackQuery):
    """Возврат к списку отзывов"""
    await cmd_reviews(callback.message)
    await callback.answer()

# ========== АДМИН-ПАНЕЛЬ ОБРАБОТЧИКИ ==========
@dp.callback_query(F.data == "admin_back")
async def action_admin_back(callback: types.CallbackQuery):
    """Возврат в админ-панель"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Брони на сегодня", callback_data="admin_view_today"),
                InlineKeyboardButton(text="📅 Брони на завтра", callback_data="admin_view_tomorrow")
            ],
            [
                InlineKeyboardButton(text="📊 Отчеты", callback_data="report_menu"),
                InlineKeyboardButton(text="📈 Статистика", callback_data="admin_stats")
            ],
            [
                InlineKeyboardButton(text="🔄 Автоотмена", callback_data="admin_auto_cancel"),
                InlineKeyboardButton(text="🔔 Напоминания", callback_data="admin_send_reminders")
            ],
            [
                InlineKeyboardButton(text="⭐ Отзывы (админ)", callback_data="admin_all_reviews"),
                InlineKeyboardButton(text="❓ Помощь", callback_data="admin_help")
            ],
            [
                InlineKeyboardButton(text="🚪 Выйти", callback_data="main_menu")
            ]
        ]
    )
    
    await callback.message.edit_text(
        "👑 <b>Админ-панель</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_view_today")
async def action_admin_view_today(callback: types.CallbackQuery):
    """Показать брони на сегодня"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    try:
        result = await call_google_script("get_today_bookings", {})
        
        if result.get("status") == "success":
            bookings = result.get("bookings", [])
            
            if not bookings:
                await callback.message.edit_text(
                    "📭 <b>Брони на сегодня</b>\n\nНа сегодня броней нет.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
                    ])
                )
                return
            
            response = "📋 <b>Брони на сегодня</b>\n\n"
            
            for i, booking in enumerate(bookings, 1):
                status_emoji = "✅" if booking.get('status') == 'Оплачено' else "⏳"
                response += f"{i}. {status_emoji} <b>{booking.get('time')}</b>\n"
                response += f"   👤 {booking.get('name')}\n"
                response += f"   📞 {booking.get('phone')}\n"
                response += f"   💰 {booking.get('price')} ₽\n"
                response += f"   🆔 {booking.get('id')}\n\n"
            
            await callback.message.edit_text(
                response, 
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
                ])
            )
        else:
            await callback.message.edit_text(
                f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
                ])
            )
    
    except Exception as e:
        logger.error(f"Ошибка в action_admin_view_today: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при получении данных",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
            ])
        )
    
    await callback.answer()

@dp.callback_query(F.data == "admin_view_tomorrow")
async def action_admin_view_tomorrow(callback: types.CallbackQuery):
    """Показать брони на завтра"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    try:
        tomorrow = (datetime.now(MOSCOW_TZ) + timedelta(days=1)).strftime("%d.%m.%Y")
        
        result = await call_google_script("get_busy_slots", {"date": tomorrow})
        
        if result.get("status") == "success":
            bookings = result.get("busy_slots", [])
            
            if not bookings:
                await callback.message.edit_text(
                    f"📭 <b>Брони на завтра ({tomorrow})</b>\n\nНа завтра броней нет.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
                    ])
                )
                return
            
            response = f"📋 <b>Брони на завтра ({tomorrow})</b>\n\n"
            
            for i, booking in enumerate(bookings, 1):
                status_emoji = "✅" if booking.get('status') == 'YES' else "⏳"
                response += f"{i}. {status_emoji} <b>{booking.get('time')}</b>\n"
                response += f"   👤 {booking.get('name')}\n"
                response += f"   Статус: {'Оплачено' if booking.get('status') == 'YES' else 'Не оплачено'}\n\n"
            
            await callback.message.edit_text(
                response, 
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
                ])
            )
        else:
            await callback.message.edit_text(
                f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
                ])
            )
    
    except Exception as e:
        logger.error(f"Ошибка в action_admin_view_tomorrow: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при получении данных",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
            ])
        )
    
    await callback.answer()

@dp.callback_query(F.data == "admin_stats")
async def handle_admin_stats(callback: types.CallbackQuery):
    """Обработка статистики в админ-панели"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await callback.answer("📊 Получаю статистику...")
    
    result = await get_stats_from_gas()
    
    if result["success"]:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📊 Подробный отчет", callback_data="report_detailed_current")],
                [InlineKeyboardButton(text="↩️ В админ-панель", callback_data="admin_back")]
            ]
        )
        
        await callback.message.edit_text(
            result["formatted_text"],
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await callback.message.edit_text(
            f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]]
            )
        )

@dp.callback_query(F.data == "report_menu")
async def action_report_menu(callback: types.CallbackQuery):
    """Меню отчетов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Ежедневный", callback_data="report_daily"),
                InlineKeyboardButton(text="📈 Еженедельный", callback_data="report_weekly")
            ],
            [
                InlineKeyboardButton(text="📅 Ежемесячный", callback_data="report_monthly"),
                InlineKeyboardButton(text="📋 Детальный", callback_data="report_detailed")
            ],
            [
                InlineKeyboardButton(text="🚀 Быстрая статистика", callback_data="report_quick_stats"),
                InlineKeyboardButton(text="⚙️ Настроить автоотчеты", callback_data="report_setup_triggers")
            ],
            [
                InlineKeyboardButton(text="🧪 Тест подключения", callback_data="report_test_connection")
            ],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
        ]
    )
    
    await callback.message.edit_text(
        "📈 <b>Система отчетности</b>\n\n"
        "Выберите тип отчета или действие:",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data == "report_daily")
async def action_report_daily(callback: types.CallbackQuery):
    """Ежедневный отчет"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    try:
        result = await get_report_from_gas("daily")
        
        if result["success"]:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Назад к отчетам", callback_data="report_menu")]
            ])
            
            await callback.message.edit_text(
                result["formatted_text"],
                parse_mode="HTML",
                reply_markup=keyboard
            )
        else:
            await callback.message.edit_text(
                f"❌ Ошибка: {result['error']}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Назад", callback_data="report_menu")]
                ])
            )
    
    except Exception as e:
        logger.error(f"Ошибка в action_report_daily: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
    
    await callback.answer()

@dp.callback_query(F.data == "report_weekly")
async def action_report_weekly(callback: types.CallbackQuery):
    """Еженедельный отчет"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    try:
        result = await get_report_from_gas("weekly")
        
        if result["success"]:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Назад к отчетам", callback_data="report_menu")]
            ])
            
            await callback.message.edit_text(
                result["formatted_text"],
                parse_mode="HTML",
                reply_markup=keyboard
            )
        else:
            await callback.message.edit_text(
                f"❌ Ошибка: {result['error']}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Назад", callback_data="report_menu")]
                ])
            )
    
    except Exception as e:
        logger.error(f"Ошибка в action_report_weekly: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
    
    await callback.answer()

@dp.callback_query(F.data == "report_monthly")
async def action_report_monthly(callback: types.CallbackQuery):
    """Ежемесячный отчет"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    try:
        result = await get_report_from_gas("monthly")
        
        if result["success"]:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Назад к отчетам", callback_data="report_menu")]
            ])
            
            await callback.message.edit_text(
                result["formatted_text"],
                parse_mode="HTML",
                reply_markup=keyboard
            )
        else:
            await callback.message.edit_text(
                f"❌ Ошибка: {result['error']}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Назад", callback_data="report_menu")]
                ])
            )
    
    except Exception as e:
        logger.error(f"Ошибка в action_report_monthly: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
    
    await callback.answer()

@dp.callback_query(F.data == "report_detailed")
async def action_report_detailed(callback: types.CallbackQuery):
    """Меню детальных отчетов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📅 Текущий месяц", callback_data="report_detailed_current")],
            [InlineKeyboardButton(text="📅 Предыдущий месяц", callback_data="report_detailed_last")],
            [InlineKeyboardButton(text="📅 За всё время", callback_data="report_detailed_all")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="report_menu")]
        ])
        
        await callback.message.edit_text(
            "📊 <b>Детальный отчет</b>\n\nВыберите период:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    
    except Exception as e:
        logger.error(f"Ошибка в action_report_detailed: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
    
    await callback.answer()

@dp.callback_query(F.data.startswith("report_detailed_"))
async def action_report_detailed_period(callback: types.CallbackQuery):
    """Детальный отчет по периоду"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    try:
        period = callback.data.replace("report_detailed_", "")
        
        result = await get_report_from_gas("detailed", period)
        
        if result["success"]:
            data = result.get("data", {})
            
            response = f"📊 <b>Детальный отчет</b>\n\n"
            
            if period == "current":
                response += "📅 <b>Период:</b> Текущий месяц\n"
            elif period == "last":
                response += "📅 <b>Период:</b> Предыдущий месяц\n"
            else:
                response += "📅 <b>Период:</b> За всё время\n"
            
            if data.get('summary'):
                summary = data['summary']
                response += f"\n📈 <b>Сводка:</b>\n"
                response += f"• Всего броней: {summary.get('totalBookings', 0)}\n"
                response += f"• Оплачено: {summary.get('paidBookings', 0)}\n"
                response += f"• Не оплачено: {summary.get('unpaidBookings', 0)}\n"
                response += f"• Общий доход: {summary.get('totalIncome', 0)} ₽\n"
                response += f"• Конверсия: {summary.get('conversionRate', 0)}%\n"
                response += f"• Средний чек: {summary.get('avgCheck', 0)} ₽\n"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Назад к отчетам", callback_data="report_menu")]
            ])
            
            await callback.message.edit_text(response, parse_mode="HTML", reply_markup=keyboard)
        else:
            await callback.message.edit_text(
                f"❌ Ошибка генерации отчета: {result.get('error', 'Неизвестная ошибка')}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Назад", callback_data="report_menu")]
                ])
            )
    
    except Exception as e:
        logger.error(f"Ошибка в action_report_detailed_period: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
    
    await callback.answer()

@dp.callback_query(F.data == "report_quick_stats")
async def action_report_quick_stats(callback: types.CallbackQuery):
    """Быстрая статистика"""
    await handle_admin_stats(callback)

@dp.callback_query(F.data == "report_setup_triggers")
async def action_report_setup_triggers(callback: types.CallbackQuery):
    """Настройка автоотчетов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await callback.answer("🔄 Настраиваю автоотчеты...")
    
    result = await call_google_script("setup_triggers", {})
    
    if result.get("status") == "success":
        await callback.message.answer(
            "✅ <b>Автоотчеты настроены!</b>\n\n"
            "📅 Расписание:\n"
            "• Еженедельный отчет: воскресенье 20:00\n"
            "• Ежемесячный отчет: 1 число 10:00\n\n"
            "Отчеты будут приходить автоматически в этот чат.",
            parse_mode="HTML"
        )
    else:
        await callback.message.answer(
            f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}",
            parse_mode="HTML"
        )
    
    await callback.answer()

@dp.callback_query(F.data == "report_test_connection")
async def action_report_test_connection(callback: types.CallbackQuery):
    """Тест подключения - прямой вызов без проверки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await callback.answer("🔗 Тестирую подключение...")
    
    try:
        result = await call_google_script("test_connection", {})
        
        if result.get("status") == "success":
            await callback.message.answer(
                f"✅ <b>Подключение работает!</b>\n\n"
                f"Сервер: <code>{GAS_WEBAPP_URL}</code>\n"
                f"Статус: {result.get('message', 'OK')}\n"
                f"Время: {result.get('timestamp', 'N/A')}",
                parse_mode="HTML"
            )
        else:
            await callback.message.answer(
                f"❌ <b>Ошибка подключения</b>\n\n"
                f"{result.get('message', 'Нет ответа от сервера')}",
                parse_mode="HTML"
            )
    except Exception as e:
        await callback.message.answer(
            f"🔥 <b>Критическая ошибка:</b>\n\n<code>{str(e)}</code>",
            parse_mode="HTML"
        )

@dp.callback_query(F.data == "admin_auto_cancel")
async def action_auto_cancel(callback: types.CallbackQuery):
    """Автоотмена старых броней"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text("🔄 Запускаю автоотмену...")
    
    result = await call_google_script("auto_cancel", {})
    
    if result.get("status") == "success":
        message = f"✅ Автоотмена выполнена\nУдалено: {result.get('cancelled_count', 0)}"
    else:
        message = f"❌ Ошибка: {result.get('message')}"
    
    await callback.message.edit_text(
        message,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_send_reminders")
async def action_send_reminders(callback: types.CallbackQuery):
    """Отправка напоминаний"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text("🔔 Отправляю напоминания...")
    
    result = await call_google_script("send_reminders", {})
    
    if result.get("status") == "success":
        stats = result.get("stats", {})
        message = (f"✅ Напоминания отправлены\n\n"
                  f"За 24 часа: {stats.get('day_before', 0)}\n"
                  f"За 2 часа: {stats.get('two_hours_before', 0)}\n"
                  f"Ошибки: {stats.get('errors', 0)}")
    else:
        message = f"❌ Ошибка: {result.get('message')}"
    
    await callback.message.edit_text(
        message,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_all_reviews")
async def handle_admin_all_reviews(callback: types.CallbackQuery):
    """Просмотр всех отзывов для админа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await callback.answer("📝 Загружаю отзывы...")
    
    result = await get_reviews_gas(public_only=False, limit=20, mask_names=False)
    
    if result.get("status") == "success":
        reviews = result.get("reviews", [])
        
        if not reviews:
            await callback.message.edit_text(
                "📭 Пока нет отзывов для модерации.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]]
                )
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
        
        keyboard_buttons = []
        
        unpublished_reviews = [r for r in reviews if not r.get("is_public")]
        if unpublished_reviews:
            keyboard_buttons.append([
                InlineKeyboardButton(text="📈 Статистика", callback_data="admin_review_stats")
            ])
        
        keyboard_buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(
            message_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await callback.message.edit_text(
            f"❌ Ошибка загрузки отзывов: {result.get('message', 'Неизвестная ошибка')}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]]
            )
        )

@dp.callback_query(F.data == "admin_review_stats")
async def handle_admin_review_stats(callback: types.CallbackQuery):
    """Статистика отзывов для админа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await callback.answer("📈 Загружаю статистику...")
    
    result = await get_reviews_gas(public_only=False, limit=100, mask_names=False)
    
    if result.get("status") == "success":
        reviews = result.get("reviews", [])
        average = result.get("average_rating", 0)
        
        rating_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for review in reviews:
            rating = int(review.get("rating", 0))
            if rating in rating_counts:
                rating_counts[rating] += 1
        
        total = len(reviews)
        public_count = sum(1 for r in reviews if r.get("is_public"))
        
        message_text = (
            f"📊 <b>Статистика отзывов</b>\n\n"
            f"📈 Всего отзывов: <b>{total}</b>\n"
            f"✅ Опубликовано: <b>{public_count}</b>\n"
            f"⏳ На модерации: <b>{total - public_count}</b>\n"
            f"⭐ Средняя оценка: <b>{float(average):.1f}/5</b>\n\n"
            f"<b>Распределение оценок:</b>\n"
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
                    [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
                ]
            )
        )
    else:
        await callback.message.edit_text(
            f"❌ Ошибка загрузки статистики: {result.get('message', 'Неизвестная ошибка')}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]]
            )
        )

@dp.callback_query(F.data == "admin_help")
async def action_admin_help(callback: types.CallbackQuery):
    """Помощь и инструкции для админа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    help_text = (
        "👑 <b>Админ-панель: Помощь и инструкции</b>\n\n"
        
        "<b>📋 Основные функции:</b>\n"
        "1. <b>Брони на сегодня/завтра</b> - просмотр броней\n"
        "2. <b>Отчеты</b> - статистика и аналитика\n"
        "3. <b>Статистика</b> - быстрые цифры\n"
        "4. <b>Автоотмена</b> - удаление старых неоплаченных броней\n"
        "5. <b>Напоминания</b> - отправка уведомлений клиентам\n\n"
        
        "<b>📊 Типы отчетов:</b>\n"
        "• <b>Ежедневный</b> - статистика за сегодня\n"
        "• <b>Еженедельный</b> - за последние 7 дней\n"
        "• <b>Ежемесячный</b> - сравнение с предыдущим месяцем\n"
        "• <b>Детальный</b> - подробная статистика по периоду\n\n"
        
        "<b>⚙️ Автоматизация:</b>\n"
        "• Автоотмена запускается каждые 24 часа\n"
        "• Напоминания отправляются за 24 и 2 часа до брони\n"
        "• Отзывы запрашиваются автоматически после посещения\n\n"
        
        "<b>❓ Частые вопросы:</b>\n"
        "• Чтобы подтвердить оплату, найдите ID брони и используйте команду /confirm [ID]\n"
        "• Для отмены брони используйте команду /cancel [ID]\n"
        "• Статистика обновляется в реальном времени\n"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(help_text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_"))
async def handle_confirm_payment(callback: types.CallbackQuery):
    """Подтверждение оплаты админом"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    record_id = callback.data.replace("confirm_", "")
    
    await callback.answer(f"Подтверждаем оплату {record_id}...")
    
    result = await call_google_script("confirm_payment", {
        "record_id": record_id,
        "admin_id": str(callback.from_user.id)
    })
    
    if result.get("status") == "success":
        if result.get("already_confirmed"):
            await callback.answer(f"✅ Оплата уже была подтверждена ранее", show_alert=True)
        else:
            await callback.answer(f"✅ Оплата подтверждена!", show_alert=True)
        
        client_name = result.get("client_name", "")
        booking_date = result.get("booking_date", "")
        booking_time = result.get("booking_time", "")
        
        await notify_admin_about_payment_confirmation(record_id, client_name, callback.from_user.id)

        await callback.message.edit_text(
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"📋 ID: <code>{record_id}</code>\n"
            f"👤 Клиент: {client_name}\n"
            f"📅 Дата: {booking_date}\n"
            f"🕐 Время: {booking_time}\n"
            f"👑 Подтвердил: Администратор",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Назад в админ-панель", callback_data="admin_back")]
            ])
        )
        
        try:
            client_chat_id = result.get("client_chat_id")
            if client_chat_id:
                await bot.send_message(
                    chat_id=int(client_chat_id),
                    text=f"🎉 <b>Ваша оплата подтверждена!</b>\n\n"
                         f"📅 Дата: {booking_date}\n"
                         f"🕐 Время: {booking_time}\n"
                         f"👤 Имя: {client_name}\n\n"
                         f"✅ Бронирование активное. Ждем вас!",
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления клиенту: {e}")
        
    else:
        error_msg = result.get("message", "Неизвестная ошибка")
        await callback.answer(f"❌ Ошибка: {error_msg}", show_alert=True)
        
        

        await callback.message.edit_text(
            f"❌ <b>Ошибка подтверждения оплаты</b>\n\n"
            f"ID: <code>{record_id}</code>\n"
            f"Ошибка: {error_msg}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Назад в админ-панель", callback_data="admin_back")]
            ])
        )

# ========== ОБРАБОТКА НЕИЗВЕСТНЫХ СООБЩЕНИЙ ==========
@dp.message()
async def unknown_message(message: types.Message, state: FSMContext):
    """Обработчик неизвестных сообщений"""
    current_state = await state.get_state()
    if current_state:
        await message.answer("Пожалуйста, завершите текущее действие или используйте команду /start")
    else:
        await message.answer(
            "Я не понимаю эту команду. Используйте /start для начала работы.\n"
            "Или /help для получения справки."
        )

# ========== ЗАПУСК БОТА ==========
async def main():
    """Основная функция запуска бота"""
    logger.info("Запуск бота...")
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
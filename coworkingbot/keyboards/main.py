from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    # Минимальная клавиатура-заглушка, чтобы импорты проходили.
    # Дальше можно заменить на реальную.
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Забронировать")],
            [KeyboardButton(text="🧾 Мои брони"), KeyboardButton(text="⭐ Отзывы")],
            [KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
        selective=True,
    )

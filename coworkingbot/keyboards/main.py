from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Новое бронирование")],
            [KeyboardButton(text="⭐ Отзывы клиентов")],
            [KeyboardButton(text="❓ Помощь и инструкции")],
        ],
        resize_keyboard=True,
        selective=True,
    )

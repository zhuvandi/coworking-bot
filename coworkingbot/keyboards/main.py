from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Забронировать")],
            [KeyboardButton(text="🧾 Мои брони")],
            [KeyboardButton(text="📄 Условия")],
        ],
        resize_keyboard=True,
        selective=True,
    )


def menu_only_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🏠 В меню")]],
        resize_keyboard=True,
        selective=True,
    )

import os

from aiogram import Bot

# Для тестов/импортов подставляем валидный по формату токен-заглушку,
# если переменная окружения BOT_TOKEN не задана.
BOT_TOKEN = os.getenv("BOT_TOKEN", "123456:TESTTOKEN")

bot = Bot(token=BOT_TOKEN)

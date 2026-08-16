# Точка входа в бота. Запускается командой: python bot.py

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
from handlers import admin, ai_assistant, booking, feedback, guides, start


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    await init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # admin, guides, booking и ai_assistant регистрируем раньше start, чтобы их более
    # специфичные хендлеры (ожидание текста рассылки, данных для записи, вопроса ИИ)
    # обрабатывались первыми. feedback — самый последний: он ловит любой текст, который
    # не подошёл ни одному из хендлеров выше (например, свободный вопрос от пользователя)
    dp.include_router(admin.router)
    dp.include_router(guides.router)
    dp.include_router(booking.router)
    dp.include_router(ai_assistant.router)
    dp.include_router(start.router)
    dp.include_router(feedback.router)

    await bot.delete_webhook(drop_pending_updates=True)

    print("Бот запущен и слушает сообщения... (нажмите Ctrl+C, чтобы остановить)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")

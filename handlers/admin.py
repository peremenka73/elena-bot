# Админ-рассылка. Доступна только пользователю с ADMIN_ID из .env.

import asyncio

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

import database as db
from config import ADMIN_ID

router = Router()

# Пауза между отправками сообщений при рассылке, чтобы не упереться
# в лимит Telegram (примерно 30 сообщений в секунду)
BROADCAST_DELAY_SECONDS = 0.05


class BroadcastStates(StatesGroup):
    waiting_for_text = State()


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext) -> None:
    if message.from_user.id != ADMIN_ID:
        return

    await state.set_state(BroadcastStates.waiting_for_text)
    await message.answer(
        "Пришлите текст рассылки следующим сообщением — он будет отправлен всем, "
        "кто хотя бы раз писал боту."
    )


@router.message(BroadcastStates.waiting_for_text)
async def process_broadcast_text(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.from_user.id != ADMIN_ID:
        return

    await state.clear()

    text = message.text or message.caption
    if not text:
        await message.answer("Рассылка отменена: сообщение должно содержать текст.")
        return

    user_ids = await db.get_all_user_ids()

    sent = 0
    failed = 0
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, text)
            sent += 1
        except TelegramForbiddenError:
            # пользователь заблокировал бота — пропускаем, не роняем рассылку
            failed += 1
        except TelegramBadRequest:
            failed += 1
        await asyncio.sleep(BROADCAST_DELAY_SECONDS)

    await message.answer(f"Рассылка завершена.\nОтправлено успешно: {sent}\nОшибок: {failed}")

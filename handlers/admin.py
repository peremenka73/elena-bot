# Админ-рассылка. Доступна только пользователю с ADMIN_ID из .env.

import asyncio

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

import database as db
from config import ADMIN_ID, GUIDES

router = Router()

BOOKING_STATUS_LABELS = {
    "pending": "ожидают ответа Елены",
    "alternatives_proposed": "ждут выбора пользователя",
    "confirmed": "подтверждены",
}

# Пауза между отправками сообщений при рассылке, чтобы не упереться
# в лимит Telegram (примерно 30 сообщений в секунду)
BROADCAST_DELAY_SECONDS = 0.05


class BroadcastStates(StatesGroup):
    waiting_for_text = State()


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if message.from_user.id != ADMIN_ID:
        return

    stats = await db.get_stats()

    guide_lines = "\n".join(
        f"  {GUIDES.get(name, {}).get('title', name)}: {count}"
        for name, count in stats["guide_breakdown"]
    ) or "  (пока нет)"

    booking_lines = "\n".join(
        f"  {BOOKING_STATUS_LABELS.get(status, status)}: {count}"
        for status, count in stats["booking_breakdown"]
    ) or "  (пока нет)"

    text = (
        "📊 Статистика бота\n\n"
        f"Всего заходили в бота: {stats['total_users']}\n"
        f"Подписаны на канал сейчас: {stats['subscribed_users']}\n\n"
        f"Гайдов забрано всего: {stats['total_guide_requests']}\n"
        f"{guide_lines}\n\n"
        f"Вопросов ИИ-ассистенту задано: {stats['total_ai_questions']}\n\n"
        f"Заявок на консультацию: {stats['total_bookings']}\n"
        f"{booking_lines}"
    )
    await message.answer(text)


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

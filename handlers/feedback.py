# Обрабатывает свободные текстовые сообщения от пользователей (не команды и не нажатия
# на кнопки) — пересылает их Елене (ELENA_ID), чтобы она могла ответить. Ответить можно
# либо обычным Reply на пересланное сообщение, либо просто следующим сообщением — тогда
# он считается ответом на самый свежий вопрос без ответа.
# Этот роутер должен быть подключён в bot.py ПОСЛЕДНИМ, чтобы не перехватывать
# сообщения, которые предназначены другим хендлерам (например, текст рассылки).

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message

import database as db
from config import ADMIN_ID, ELENA_ID
from handlers.menu import MENU_BUTTON_TEXTS

router = Router()


@router.message(F.reply_to_message, F.from_user.id == ELENA_ID)
async def process_elena_reply(message: Message, bot: Bot) -> None:
    """Елена ответила Reply-ом на пересланный вопрос — пересылаем её текст пользователю."""
    text = message.text or message.caption
    if not text:
        await message.answer("Не получилось прочитать ответ — напишите его текстом.")
        return

    elena_message_id = message.reply_to_message.message_id
    user_id = await db.get_user_id_by_question_message(elena_message_id)
    if user_id is None:
        pending = await db.get_latest_unanswered_question()
        if pending is None:
            await message.answer("Не нашёл, кому переслать этот ответ — похоже, нет вопросов, ждущих ответа.")
            return
        elena_message_id, user_id = pending

    await _forward_answer_to_user(message, bot, user_id, text, elena_message_id)


@router.message(F.from_user.id == ELENA_ID, F.text, ~F.text.startswith("/"), ~F.text.in_(MENU_BUTTON_TEXTS))
async def process_elena_message_without_reply(message: Message, bot: Bot) -> None:
    """Елена написала обычным сообщением, не через Reply — считаем это ответом на
    самый свежий вопрос без ответа (так проще для не очень технического человека)."""
    pending = await db.get_latest_unanswered_question()
    if pending is None:
        return

    elena_message_id, user_id = pending
    await _forward_answer_to_user(message, bot, user_id, message.text, elena_message_id)


async def _forward_answer_to_user(message: Message, bot: Bot, user_id: int, text: str, elena_message_id: int) -> None:
    try:
        await bot.send_message(user_id, f"Елена ответила:\n\n{text}")
    except (TelegramForbiddenError, TelegramBadRequest):
        await message.answer("Не получилось отправить — пользователь, похоже, заблокировал бота.")
        return

    await db.mark_question_forward_answered(elena_message_id)
    await message.answer("Ответ отправлен пользователю ✅")


@router.message(F.text)
async def forward_to_elena(message: Message, bot: Bot) -> None:
    user = message.from_user
    first_name = user.first_name or "друг"

    if user.id in (ADMIN_ID, ELENA_ID):
        return

    await message.answer(
        f"Спасибо за вопрос, {first_name}! Записал(а) — Елена ответит вам здесь, "
        "как только сможет 💛"
    )

    username_part = f" (@{user.username})" if user.username else ""
    forward_text = (
        f"✉️ Новое сообщение от пользователя бота\n"
        f"{first_name}{username_part}, id: {user.id}\n\n"
        f"{message.text}\n\n"
        "Чтобы ответить — сделайте Reply на это сообщение, либо просто напишите следующим."
    )
    try:
        sent = await bot.send_message(ELENA_ID, forward_text)
        await db.save_question_forward(sent.message_id, user.id)
    except (TelegramForbiddenError, TelegramBadRequest):
        print(f"Не удалось переслать вопрос Елене от user_id={user.id} — она ещё не писала боту?")

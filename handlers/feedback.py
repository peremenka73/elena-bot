# Обрабатывает свободные текстовые сообщения от пользователей (не команды и не нажатия
# на кнопки) — пересылает их администратору (ADMIN_ID), чтобы можно было ответить вручную.
# Этот роутер должен быть подключён в bot.py ПОСЛЕДНИМ, чтобы не перехватывать
# сообщения, которые предназначены другим хендлерам (например, текст рассылки).

from aiogram import Bot, F, Router
from aiogram.types import Message

from config import ADMIN_ID, ELENA_ID

router = Router()


@router.message(F.text)
async def forward_to_admin(message: Message, bot: Bot) -> None:
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
        f"{message.text}"
    )
    await bot.send_message(ADMIN_ID, forward_text)

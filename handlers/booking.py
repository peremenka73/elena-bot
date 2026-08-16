# Запись на приём: пользователь нажимает кнопку, бот спрашивает удобное время
# и контакт, и пересылает заявку Елене (ELENA_ID). Если Елена отвечает на это
# сообщение через обычный Reply в Telegram — бот пересылает её ответ пользователю.
# Никакого реального календаря тут нет, всё передаётся вручную, через переписку.

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database as db
from config import ELENA_ID
from handlers.menu import BOOKING_BUTTON_TEXT, MENU_BUTTON_TEXTS

router = Router()

BOOK_APPOINTMENT_CALLBACK = "book_appointment"

# Куда можно записаться и без бота — упоминается в сообщении с просьбой оставить данные
BOOKING_SITE_URL = "https://psyhologguru.ru"


class BookingStates(StatesGroup):
    waiting_for_details = State()


def booking_button() -> InlineKeyboardButton:
    """Кнопка «Записаться на консультацию» — используется и в меню гайдов, и после выдачи гайда."""
    return InlineKeyboardButton(text="📅 Записаться на консультацию", callback_data=BOOK_APPOINTMENT_CALLBACK)


async def _start_booking(message: Message, first_name: str, state: FSMContext) -> None:
    await state.set_state(BookingStates.waiting_for_details)
    await message.answer(
        f"{first_name}, напишите, пожалуйста, удобное время для консультации и контакт "
        "для связи (телефон или @username) — передам Елене, и она свяжется с вами 💛\n\n"
        f"Записаться можно и напрямую на сайте: {BOOKING_SITE_URL}"
    )


@router.callback_query(F.data == BOOK_APPOINTMENT_CALLBACK)
async def callback_book_appointment(callback: CallbackQuery, state: FSMContext) -> None:
    first_name = callback.from_user.first_name or "друг"
    await callback.answer()
    await _start_booking(callback.message, first_name, state)


@router.message(F.text == BOOKING_BUTTON_TEXT)
async def button_book_appointment(message: Message, state: FSMContext) -> None:
    first_name = message.from_user.first_name or "друг"
    await _start_booking(message, first_name, state)


@router.message(BookingStates.waiting_for_details, ~F.text.in_(MENU_BUTTON_TEXTS))
async def process_booking_details(message: Message, state: FSMContext, bot: Bot) -> None:
    user = message.from_user
    first_name = user.first_name or "друг"

    text = message.text or message.caption
    if not text:
        await message.answer(
            f"{first_name}, не получилось прочитать сообщение — напишите, пожалуйста, "
            "текстом удобное время и контакт для связи."
        )
        return

    await state.clear()

    username_part = f" (@{user.username})" if user.username else ""
    forward_text = (
        f"📅 Заявка на консультацию\n"
        f"{first_name}{username_part}, id: {user.id}\n\n"
        f"{text}\n\n"
        "Чтобы ответить пользователю — просто сделайте Reply на это сообщение."
    )
    try:
        sent_message = await bot.send_message(ELENA_ID, forward_text)
    except (TelegramForbiddenError, TelegramBadRequest):
        # Такое бывает, если Елена ещё ни разу не писала боту — Telegram не разрешает
        # ботам первыми начинать переписку с человеком.
        print("Ошибка: не удалось отправить заявку Елене (ELENA_ID). Она ещё не писала боту?")
        await message.answer(
            f"{first_name}, заявку принял(а), но не получилось передать её Елене напрямую — "
            f"попробуйте, пожалуйста, также записаться через сайт: {BOOKING_SITE_URL}"
        )
        return

    await db.save_booking_forward(sent_message.message_id, user.id)
    await message.answer(
        f"Спасибо, {first_name}! Заявка на консультацию передана Елене, она свяжется с вами 💛"
    )


@router.message(F.reply_to_message, F.from_user.id == ELENA_ID)
async def process_elena_reply(message: Message, bot: Bot) -> None:
    """Елена ответила Reply-ом на пересланную заявку — пересылаем её текст пользователю."""
    text = message.text or message.caption
    if not text:
        await message.answer("Не получилось прочитать ответ — напишите его текстом.")
        return

    elena_message_id = message.reply_to_message.message_id
    user_id = await db.get_user_id_by_elena_message(elena_message_id)
    if user_id is None:
        # Reply сделан не на сообщение с заявкой — на всякий случай пробуем
        # подставить самую свежую заявку, на которую ещё не было ответа
        pending = await db.get_latest_unanswered_booking()
        if pending is None:
            await message.answer(
                "Не нашёл, кому переслать этот ответ — похоже, нет заявок, ждущих ответа."
            )
            return
        elena_message_id, user_id = pending

    await _forward_reply_to_user(message, bot, user_id, text, elena_message_id)


@router.message(
    F.from_user.id == ELENA_ID, F.text, ~F.text.startswith("/"), ~F.text.in_(MENU_BUTTON_TEXTS)
)
async def process_elena_message_without_reply(message: Message, bot: Bot) -> None:
    """Елена написала обычным сообщением, не через Reply — считаем это ответом на
    самую свежую заявку без ответа (так проще для не очень технического человека)."""
    pending = await db.get_latest_unanswered_booking()
    if pending is None:
        # Обычное сообщение Елены, не связанное с заявками на приём — просто игнорируем
        return

    elena_message_id, user_id = pending
    await _forward_reply_to_user(message, bot, user_id, message.text, elena_message_id)


async def _forward_reply_to_user(
    message: Message, bot: Bot, user_id: int, text: str, elena_message_id: int
) -> None:
    try:
        await bot.send_message(user_id, f"Елена ответила на вашу заявку на консультацию:\n\n{text}")
    except (TelegramForbiddenError, TelegramBadRequest):
        await message.answer("Не получилось отправить — пользователь, похоже, заблокировал бота.")
        return

    await db.mark_booking_forward_answered(elena_message_id)
    await message.answer("Ответ отправлен пользователю ✅")

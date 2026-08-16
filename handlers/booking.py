# Запись на консультацию: пользователь выбирает формат (онлайн/переписка), затем дату
# и время через кнопки (в Telegram нет настоящего визуального календаря — только так).
# Заявка уходит Елене с кнопками «Подтвердить» / «Предложить другое время». Если она
# предлагает другое — тем же способом выбирает 3 варианта, они уходят пользователю,
# он выбирает подходящий. После подтверждения — пользователю приходит дата/время
# и реквизиты для оплаты, Елене — итоговое подтверждение.

import json
from datetime import date, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database as db
from config import ELENA_ID
from handlers.menu import BOOKING_BUTTON_TEXT

router = Router()

BOOK_APPOINTMENT_CALLBACK = "book_appointment"

# Куда можно записаться и без бота — на случай, если не получится передать заявку Елене напрямую
BOOKING_SITE_URL = "https://psyhologguru.ru"

CONSULTATION_TYPES = {
    "online": "🎥 Онлайн (видеозвонок)",
    "chat": "💬 Переписка в чате",
}

# Часы, которые предлагаются для записи. При желании можно изменить список.
TIME_SLOTS = ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00"]

# На сколько дней вперёд показывать даты для выбора
DATE_RANGE_DAYS = 14

MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
WEEKDAYS_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

# TODO: впишите реальные реквизиты для оплаты (номер карты/телефона и получателя) —
# этот текст бот показывает клиенту после подтверждения записи на консультацию.
PAYMENT_REQUISITES = "# TODO: реквизиты для оплаты (номер карты/телефона, получатель)"


class ConsultationStates(StatesGroup):
    choosing_type = State()
    choosing_date = State()
    choosing_time = State()


class ElenaAltStates(StatesGroup):
    choosing_date = State()
    choosing_time = State()


def booking_button() -> InlineKeyboardButton:
    """Кнопка «Записаться на консультацию» — используется в меню гайдов и после выдачи гайда."""
    return InlineKeyboardButton(text="📅 Записаться на консультацию", callback_data=BOOK_APPOINTMENT_CALLBACK)


def _format_date(iso_date: str) -> str:
    d = date.fromisoformat(iso_date)
    return f"{d.day} {MONTHS_RU[d.month - 1]} ({WEEKDAYS_RU[d.weekday()]})"


def _date_keyboard(callback_prefix: str) -> InlineKeyboardMarkup:
    today = date.today()
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i in range(1, DATE_RANGE_DAYS + 1):
        d = today + timedelta(days=i)
        label = f"{d.day} {MONTHS_RU[d.month - 1]} ({WEEKDAYS_RU[d.weekday()]})"
        row.append(InlineKeyboardButton(text=label, callback_data=f"{callback_prefix}:{d.isoformat()}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _time_keyboard(callback_prefix: str) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for slot in TIME_SLOTS:
        row.append(InlineKeyboardButton(text=slot, callback_data=f"{callback_prefix}:{slot}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _start_booking(message: Message, state: FSMContext) -> None:
    await state.set_state(ConsultationStates.choosing_type)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"ctype:{key}")]
            for key, label in CONSULTATION_TYPES.items()
        ]
    )
    await message.answer("Выберите формат консультации:", reply_markup=keyboard)


@router.callback_query(F.data == BOOK_APPOINTMENT_CALLBACK)
async def callback_book_appointment(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _start_booking(callback.message, state)


@router.message(F.text == BOOKING_BUTTON_TEXT)
async def button_book_appointment(message: Message, state: FSMContext) -> None:
    await _start_booking(message, state)


@router.callback_query(ConsultationStates.choosing_type, F.data.startswith("ctype:"))
async def callback_choose_type(callback: CallbackQuery, state: FSMContext) -> None:
    consultation_type = callback.data.split(":", 1)[1]
    await callback.answer()
    await state.update_data(consultation_type=consultation_type)
    await state.set_state(ConsultationStates.choosing_date)
    await callback.message.edit_text(
        f"Формат: {CONSULTATION_TYPES[consultation_type]}\n\nВыберите удобную дату:",
        reply_markup=_date_keyboard("cdate"),
    )


@router.callback_query(ConsultationStates.choosing_date, F.data.startswith("cdate:"))
async def callback_choose_date(callback: CallbackQuery, state: FSMContext) -> None:
    chosen_date = callback.data.split(":", 1)[1]
    await callback.answer()
    await state.update_data(requested_date=chosen_date)
    await state.set_state(ConsultationStates.choosing_time)
    await callback.message.edit_text(
        f"Дата: {_format_date(chosen_date)}\n\nВыберите удобное время:",
        reply_markup=_time_keyboard("ctime"),
    )


@router.callback_query(ConsultationStates.choosing_time, F.data.startswith("ctime:"))
async def callback_choose_time(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    chosen_time = callback.data.split(":", 1)[1]
    data = await state.get_data()
    consultation_type = data["consultation_type"]
    requested_date = data["requested_date"]
    await callback.answer()
    await state.clear()

    user = callback.from_user
    first_name = user.first_name or "друг"

    booking_id = await db.create_booking(user.id, consultation_type, requested_date, chosen_time)

    await callback.message.edit_text(
        f"{first_name}, заявка отправлена Елене! 💛\n\n"
        f"Формат: {CONSULTATION_TYPES[consultation_type]}\n"
        f"Дата: {_format_date(requested_date)}\n"
        f"Время: {chosen_time}\n\n"
        "Как только Елена подтвердит — вы получите сообщение здесь."
    )

    username_part = f" (@{user.username})" if user.username else ""
    elena_text = (
        f"📅 Новая заявка на консультацию\n"
        f"{first_name}{username_part}, id: {user.id}\n\n"
        f"Формат: {CONSULTATION_TYPES[consultation_type]}\n"
        f"Дата: {_format_date(requested_date)}\n"
        f"Время: {chosen_time}"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"cconfirm:{booking_id}")],
            [InlineKeyboardButton(text="🔄 Предложить другое время", callback_data=f"calt:{booking_id}")],
        ]
    )
    try:
        sent = await bot.send_message(ELENA_ID, elena_text, reply_markup=keyboard)
        await db.set_booking_elena_message_id(booking_id, sent.message_id)
    except (TelegramForbiddenError, TelegramBadRequest):
        print(f"Не удалось отправить заявку на консультацию Елене (booking_id={booking_id})")
        await callback.message.answer(
            f"{first_name}, не получилось передать заявку Елене напрямую — "
            f"попробуйте, пожалуйста, также записаться через сайт: {BOOKING_SITE_URL}"
        )


@router.callback_query(F.data.startswith("cconfirm:"))
async def callback_elena_confirm(callback: CallbackQuery, bot: Bot) -> None:
    if callback.from_user.id != ELENA_ID:
        await callback.answer()
        return

    booking_id = int(callback.data.split(":", 1)[1])
    booking = await db.get_booking(booking_id)
    await callback.answer()
    if booking is None:
        await callback.message.answer("Заявка не найдена.")
        return

    await db.confirm_booking(booking_id, booking["requested_date"], booking["requested_time"])
    await _notify_confirmed(
        bot, booking_id, booking["user_id"], booking["consultation_type"],
        booking["requested_date"], booking["requested_time"],
    )
    await callback.message.edit_text((callback.message.text or "") + "\n\n✅ Подтверждено")


@router.callback_query(F.data.startswith("calt:"))
async def callback_elena_propose_alt(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id != ELENA_ID:
        await callback.answer()
        return

    booking_id = int(callback.data.split(":", 1)[1])
    await callback.answer()
    await state.update_data(alt_booking_id=booking_id, alt_slots=[])
    await state.set_state(ElenaAltStates.choosing_date)
    await callback.message.answer("Выберите дату для варианта 1 из 3:", reply_markup=_date_keyboard("adate"))


@router.callback_query(ElenaAltStates.choosing_date, F.data.startswith("adate:"))
async def callback_elena_alt_date(callback: CallbackQuery, state: FSMContext) -> None:
    chosen_date = callback.data.split(":", 1)[1]
    await callback.answer()
    await state.update_data(current_alt_date=chosen_date)
    await state.set_state(ElenaAltStates.choosing_time)
    await callback.message.edit_text(
        f"Дата: {_format_date(chosen_date)}\n\nВыберите время:", reply_markup=_time_keyboard("atime")
    )


@router.callback_query(ElenaAltStates.choosing_time, F.data.startswith("atime:"))
async def callback_elena_alt_time(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    chosen_time = callback.data.split(":", 1)[1]
    await callback.answer()
    data = await state.get_data()
    slots = list(data.get("alt_slots", []))
    slots.append({"date": data["current_alt_date"], "time": chosen_time})
    booking_id = data["alt_booking_id"]

    if len(slots) < 3:
        await state.update_data(alt_slots=slots)
        await state.set_state(ElenaAltStates.choosing_date)
        await callback.message.edit_text(
            f"Вариант {len(slots)} сохранён. Выберите дату для варианта {len(slots) + 1} из 3:",
            reply_markup=_date_keyboard("adate"),
        )
        return

    await db.save_proposed_slots(booking_id, json.dumps(slots, ensure_ascii=False))
    booking = await db.get_booking(booking_id)
    await state.clear()
    await callback.message.edit_text("Варианты отправлены пользователю 💛")

    lines = "\n".join(f"{i + 1}. {_format_date(s['date'])}, {s['time']}" for i, s in enumerate(slots))
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Вариант {i + 1}", callback_data=f"cpick:{booking_id}:{i}")]
            for i in range(len(slots))
        ]
    )
    try:
        await bot.send_message(
            booking["user_id"],
            f"Елена предложила другое время для консультации:\n\n{lines}\n\nВыберите подходящий вариант:",
            reply_markup=keyboard,
        )
    except (TelegramForbiddenError, TelegramBadRequest):
        print(f"Не удалось отправить варианты пользователю (booking_id={booking_id})")


@router.callback_query(F.data.startswith("cpick:"))
async def callback_user_pick_alt(callback: CallbackQuery, bot: Bot) -> None:
    _, booking_id_str, index_str = callback.data.split(":")
    booking_id = int(booking_id_str)
    index = int(index_str)
    await callback.answer()

    booking = await db.get_booking(booking_id)
    if booking is None or not booking["proposed_slots"]:
        await callback.message.answer("Не нашёл эту заявку.")
        return

    slots = json.loads(booking["proposed_slots"])
    slot = slots[index]

    await db.confirm_booking(booking_id, slot["date"], slot["time"])
    await callback.message.edit_text(f"Вы выбрали: {_format_date(slot['date'])}, {slot['time']} ✅")
    await _notify_confirmed(
        bot, booking_id, booking["user_id"], booking["consultation_type"], slot["date"], slot["time"]
    )


async def _notify_confirmed(
    bot: Bot, booking_id: int, user_id: int, consultation_type: str, confirmed_date: str, confirmed_time: str
) -> None:
    date_text = _format_date(confirmed_date)
    type_label = CONSULTATION_TYPES.get(consultation_type, consultation_type)

    user_text = (
        "Вы записаны на консультацию! ✅\n\n"
        f"Формат: {type_label}\n"
        f"Дата: {date_text}\n"
        f"Время: {confirmed_time}\n\n"
        "Чтобы консультация состоялась, пожалуйста, произведите оплату не позднее чем "
        "за сутки до назначенного времени.\n\n"
        f"Реквизиты для оплаты:\n{PAYMENT_REQUISITES}"
    )
    try:
        await bot.send_message(user_id, user_text)
    except (TelegramForbiddenError, TelegramBadRequest):
        print(f"Не удалось отправить подтверждение пользователю (booking_id={booking_id})")

    elena_text = (
        "✅ Консультация подтверждена\n\n"
        f"Формат: {type_label}\n"
        f"Дата: {date_text}\n"
        f"Время: {confirmed_time}\n"
        f"user_id: {user_id}"
    )
    try:
        await bot.send_message(ELENA_ID, elena_text)
    except (TelegramForbiddenError, TelegramBadRequest):
        print(f"Не удалось отправить подтверждение Елене (booking_id={booking_id})")

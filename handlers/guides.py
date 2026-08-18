# Хендлеры, отвечающие за меню гайдов и выдачу PDF-файлов.

from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import database as db
from config import GUIDES
from handlers.ai_assistant import ai_button
from handlers.booking import booking_button
from handlers.menu import GUIDES_BUTTON_TEXT
from subscription import is_user_subscribed

router = Router()

# Если рядом с bot.py есть папка data/ (постоянное хранилище на сервере — Volume у Bothost),
# гайды кладём внутрь неё (data/guides/), чтобы они не пропадали при пересборке бота.
# Локально такой папки нет — используется обычная guides/ рядом с bot.py, как раньше.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"
GUIDES_DIR = (_DATA_DIR / "guides") if _DATA_DIR.is_dir() else (_PROJECT_ROOT / "guides")


def guides_keyboard() -> InlineKeyboardMarkup:
    """Собирает inline-клавиатуру из списка гайдов в config.py — по 2 кнопки в ряд."""
    guide_buttons = [
        InlineKeyboardButton(text=guide["title"], callback_data=f"guide:{key}")
        for key, guide in GUIDES.items()
    ]
    buttons = [guide_buttons[i : i + 2] for i in range(0, len(guide_buttons), 2)]
    buttons.append([booking_button()])
    buttons.append([ai_button()])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def send_guides_menu_to(bot: Bot, chat_id: int) -> None:
    """Отправляет сообщение с меню гайдов по chat_id — используется там, где нет объекта Message
    (например, при автоодобрении заявки на вступление в канал)."""
    await bot.send_message(
        chat_id, "Выберите гайд, который хотите получить:", reply_markup=guides_keyboard()
    )


async def send_guides_menu(message: Message) -> None:
    """Отправляет сообщение с меню гайдов. Используется и из start.py, и из этого файла."""
    await send_guides_menu_to(message.bot, message.chat.id)


@router.message(Command("guides"))
@router.message(F.text == GUIDES_BUTTON_TEXT)
async def cmd_guides(message: Message, bot: Bot, state: FSMContext) -> None:
    user = message.from_user
    first_name = user.first_name or "друг"

    # Кнопка меню «Гайды» всегда переключает в этот раздел — сбрасываем незавершённый
    # диалог (например, ожидание вопроса ИИ или данных для записи на консультацию)
    await state.clear()

    subscribed = await is_user_subscribed(bot, user.id)
    await db.set_subscription_status(user.id, subscribed)

    if not subscribed:
        await message.answer(
            f"{first_name}, чтобы получить гайд, сначала нужно подписаться на канал. "
            "Наберите /start — там будет кнопка для подписки."
        )
        return

    await send_guides_menu(message)


@router.callback_query(F.data.startswith("guide:"))
async def callback_send_guide(callback: CallbackQuery) -> None:
    user = callback.from_user
    first_name = user.first_name or "друг"
    guide_key = callback.data.split(":", 1)[1]

    guide = GUIDES.get(guide_key)
    await callback.answer()

    if guide is None:
        return

    file_path = GUIDES_DIR / guide["file"]
    if not file_path.exists():
        print(f"Ошибка: файл гайда не найден на диске: {file_path}")
        await callback.message.answer(
            f"Ой, {first_name}, этот гайд сейчас недоступен, попробуйте чуть позже 🙏"
        )
        return

    await callback.message.answer(f"{first_name}, вот ваш гайд! Держите 📄")
    await callback.message.answer_document(FSInputFile(file_path), caption=guide["caption"])
    await callback.message.answer(
        f"Пользуйтесь на здоровье, {first_name}! Если появятся вопросы — "
        "можете написать прямо сюда, или загляните на psyhologguru.ru 💛\n\n"
        "Хотите забрать ещё один гайд? Наберите /guides в любой момент.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[booking_button()], [ai_button()]]),
    )

    await db.log_guide_request(user.id, guide_key)

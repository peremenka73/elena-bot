# Хендлеры для команды /start: приветствие и проверка подписки на канал.
# Поддерживает deep link с сайта вида t.me/bot_username?start=ai — такой переход
# сразу открывает раздел вопроса ИИ-ассистенту после подтверждения подписки.

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database as db
from config import CHANNEL_USERNAME
from handlers.ai_assistant import start_ai_question
from handlers.guides import send_guides_menu
from handlers.menu import ASK_AI_BUTTON_TEXT, main_menu_keyboard
from subscription import is_user_subscribed

router = Router()

# Значение параметра ?start=ai для deep link с сайта
DEEP_LINK_AI = "ai"

AI_INTRO_TEXT = (
    "Кроме гайдов, у вас есть 3 бесплатных вопроса нашему ИИ-ассистенту-психологу — "
    f"можно спросить о том, что беспокоит, прямо здесь, в чате. Нажмите «{ASK_AI_BUTTON_TEXT}» "
    "в меню внизу, когда будете готовы."
)


def subscribe_keyboard(payload: str | None = None) -> InlineKeyboardMarkup:
    channel_url = f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться на канал 📲", url=channel_url)],
            [
                InlineKeyboardButton(
                    text="Я подписался, проверить ✅",
                    callback_data=f"check_subscription:{payload or ''}",
                )
            ],
        ]
    )


async def _greet_subscribed_user(
    message: Message, first_name: str, state: FSMContext, user_id: int, payload: str | None
) -> None:
    await message.answer(f"С возвращением, {first_name}! 😊")

    if payload == DEEP_LINK_AI:
        await start_ai_question(message, user_id, first_name, state)
        return

    await send_guides_menu(message)
    await message.answer(AI_INTRO_TEXT, reply_markup=main_menu_keyboard())


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, command: CommandObject, state: FSMContext) -> None:
    user = message.from_user
    first_name = user.first_name or "друг"
    payload = command.args or None

    await db.upsert_user(user.id, user.username, first_name)

    subscribed = await is_user_subscribed(bot, user.id)
    await db.set_subscription_status(user.id, subscribed)

    if subscribed:
        await _greet_subscribed_user(message, first_name, state, user.id, payload)
        return

    text = (
        f"Привет, {first_name}! 👋\n\n"
        "Я бот Елены Семёновой, психолога-консультанта. Здесь можно бесплатно "
        "забрать полезные гайды по СРК, тревоге, панике и отношениям.\n\n"
        "Чтобы получить гайд, подпишитесь, пожалуйста, на канал Елены — "
        "там регулярно выходят разборы и полезные материалы 👇"
    )
    await message.answer(text, reply_markup=subscribe_keyboard(payload))


@router.callback_query(F.data.startswith("check_subscription"))
async def callback_check_subscription(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    user = callback.from_user
    first_name = user.first_name or "друг"
    payload = callback.data.split(":", 1)[1] if ":" in callback.data else ""
    payload = payload or None

    await callback.answer(f"Проверяю подписку, {first_name}... 🔍")

    subscribed = await is_user_subscribed(bot, user.id)
    await db.set_subscription_status(user.id, subscribed)

    if subscribed:
        await callback.message.edit_text(f"Спасибо, что подписались, {first_name}! 🎉")
        if payload == DEEP_LINK_AI:
            await start_ai_question(callback.message, user.id, first_name, state)
        else:
            await send_guides_menu(callback.message)
            await callback.message.answer(AI_INTRO_TEXT, reply_markup=main_menu_keyboard())
    else:
        await callback.message.edit_text(
            f"{first_name}, пока не вижу вашу подписку на канал 🙈\n\n"
            "Подпишитесь, пожалуйста, по кнопке выше, и нажмите «Я подписался» "
            "ещё раз — обычно это занимает секунд 10.",
            reply_markup=subscribe_keyboard(payload),
        )

# ИИ-ассистент психолога: после подписки пользователь может задать до 3 бесплатных
# вопросов прямо в боте. Вопрос уходит в DeepSeek с системным промптом в духе Елены,
# ответ приходит обратно. Счётчик заданных вопросов хранится в SQLite (users.free_ai_questions_used)
# и не сбрасывается при перезапуске бота. После лимита — приглашение на сайт и на консультацию.

import asyncio

import httpx
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database as db
from config import DEEPSEEK_API_KEY
from handlers.booking import booking_button
from handlers.menu import ASK_AI_BUTTON_TEXT, MENU_BUTTON_TEXTS, main_menu_keyboard

router = Router()

ASK_AI_CALLBACK = "ask_ai"
FREE_QUESTIONS_LIMIT = 3
SITE_URL = "https://psyhologguru.ru"

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

AI_SYSTEM_PROMPT = (
    "Ты — ИИ-ассистент психолога Елены Семёновой, специалиста по психосоматике, "
    "синдрому раздражённого кишечника (СРК) и паническим атакам. Отвечай тепло, эмпатично "
    "и по-человечески, как живой профессиональный психолог-консультант, без канцелярита. "
    "Давай содержательные ответы с элементами психообразования: помогай человеку понять, "
    "что с ним происходит, и предлагай конкретные, бережные шаги. "
    "Никогда не ставь медицинские или психиатрические диагнозы, не назначай лечение "
    "и не заменяй собой психотерапию — если видишь признаки серьёзного состояния, "
    "мягко порекомендуй очную консультацию с Еленой или врачом. "
    "Отвечай на русском языке, по существу, без давления и категоричности — "
    "несколько абзацев, не разворачивай ответ на весь экран."
)


class AIStates(StatesGroup):
    waiting_for_question = State()


def ai_button() -> InlineKeyboardButton:
    """Кнопка «Задать вопрос ИИ-ассистенту» — используется в меню гайдов и после подписки."""
    return InlineKeyboardButton(text="Задать вопрос ИИ-ассистенту 🤖", callback_data=ASK_AI_CALLBACK)


def _limit_reached_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Продолжить на сайте 💬", url=SITE_URL)],
            [booking_button()],
        ]
    )


async def _send_limit_reached(message: Message, first_name: str) -> None:
    await message.answer(
        f"{first_name}, бесплатные вопросы ИИ-ассистенту закончились 💛\n\n"
        f"Продолжить общение с ассистентом можно на сайте по подписке ({SITE_URL}, "
        "раздел «Чат с ассистентом», тарифы от 490₽/50 сообщений).\n\n"
        "Или запишитесь на личную консультацию к Елене — иногда это даёт больше, "
        "чем переписка с ботом.",
        reply_markup=_limit_reached_keyboard(),
    )


async def start_ai_question(message: Message, user_id: int, first_name: str, state: FSMContext) -> None:
    """Начинает диалог «задать вопрос ИИ» — используется из кнопок в этом файле,
    а также из start.py при переходе по deep link ?start=ai с сайта."""
    used = await db.get_ai_questions_used(user_id)
    remaining = FREE_QUESTIONS_LIMIT - used
    if remaining <= 0:
        await _send_limit_reached(message, first_name)
        return

    await state.set_state(AIStates.waiting_for_question)
    await message.answer(
        f"{first_name}, напишите свой вопрос — отвечу как психолог-консультант 💛\n"
        f"Осталось бесплатных вопросов: {remaining}.",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data == ASK_AI_CALLBACK)
async def callback_ask_ai(callback: CallbackQuery, state: FSMContext) -> None:
    first_name = callback.from_user.first_name or "друг"
    await callback.answer()
    await start_ai_question(callback.message, callback.from_user.id, first_name, state)


@router.message(F.text == ASK_AI_BUTTON_TEXT)
async def button_ask_ai(message: Message, state: FSMContext) -> None:
    first_name = message.from_user.first_name or "друг"
    await start_ai_question(message, message.from_user.id, first_name, state)


@router.message(AIStates.waiting_for_question, ~F.text.in_(MENU_BUTTON_TEXTS))
async def process_ai_question(message: Message, state: FSMContext, bot: Bot) -> None:
    user = message.from_user
    first_name = user.first_name or "друг"

    question = message.text
    if not question:
        await message.answer(
            f"{first_name}, опишите вопрос текстом, пожалуйста — так я смогу ответить."
        )
        return

    used = await db.get_ai_questions_used(user.id)
    if used >= FREE_QUESTIONS_LIMIT:
        await state.clear()
        await _send_limit_reached(message, first_name)
        return

    # Индикатор «печатает» в Telegram мелькает быстро и его легко не заметить —
    # поэтому дополнительно отправляем обычное сообщение, которое точно останется
    # видно в чате, пока готовится ответ.
    await message.answer("💭 Секунду, думаю над ответом...")

    # Сам индикатор «печатает» тоже держим — он сам гаснет через ~5 секунд,
    # а DeepSeek может отвечать дольше, поэтому обновляем его в фоне.
    typing_task = asyncio.create_task(_keep_typing(bot, message.chat.id))

    try:
        answer = await _ask_deepseek(question)
    except Exception as error:
        print(f"Ошибка запроса к DeepSeek: {error}")
        # Состояние оставляем как есть — пользователь может просто написать вопрос
        # заново, не нажимая кнопку повторно. Вопрос ему не засчитан.
        await message.answer(
            f"{first_name}, не получилось получить ответ от ассистента — попробуйте, "
            "пожалуйста, написать вопрос ещё раз чуть позже. Этот вопрос вам не засчитан."
        )
        return
    finally:
        typing_task.cancel()

    await db.increment_ai_questions_used(user.id)
    remaining = FREE_QUESTIONS_LIMIT - (used + 1)

    await message.answer(answer)

    if remaining > 0:
        # Оставляем то же состояние — можно сразу писать следующий вопрос,
        # без повторного нажатия кнопки.
        await message.answer(f"Осталось бесплатных вопросов: {remaining}. Можете писать следующий 💛")
    else:
        await state.clear()
        await _send_limit_reached(message, first_name)


async def _keep_typing(bot: Bot, chat_id: int) -> None:
    """Раз в 4 секунды обновляет статус «печатает», пока не отменят задачу."""
    try:
        while True:
            await bot.send_chat_action(chat_id, "typing")
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


async def _ask_deepseek(question: str) -> str:
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": AI_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        "temperature": 0.7,
        "max_tokens": 700,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    return data["choices"][0]["message"]["content"].strip()

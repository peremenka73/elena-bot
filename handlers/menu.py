# Постоянное меню внизу экрана (reply-клавиатура) — всегда видно над полем ввода,
# не нужно листать вверх в поисках инлайн-кнопок. Дублирует основные разделы бота.

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

GUIDES_BUTTON_TEXT = "📚 Гайды"
ASK_AI_BUTTON_TEXT = "Написать ассистенту"
BOOKING_BUTTON_TEXT = "Запись на консультацию"

# Тексты кнопок меню — используются в других хендлерах, чтобы нажатие кнопки меню
# не «проглатывалось» как ответ на предыдущий вопрос (например, как текст для ИИ)
MENU_BUTTON_TEXTS = {GUIDES_BUTTON_TEXT, ASK_AI_BUTTON_TEXT, BOOKING_BUTTON_TEXT}


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=GUIDES_BUTTON_TEXT)],
            [KeyboardButton(text=ASK_AI_BUTTON_TEXT), KeyboardButton(text=BOOKING_BUTTON_TEXT)],
        ],
        resize_keyboard=True,
    )

# Модуль читает настройки из файла .env и хранит их в удобном виде.
# Ничего не нужно менять в этом файле — все значения задаются в .env

import os
import sys

from dotenv import load_dotenv

# Загружаем переменные из файла .env в окружение
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
CHANNEL_ID_RAW = os.getenv("CHANNEL_ID")
ELENA_ID_RAW = os.getenv("ELENA_ID")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Проверяем, что все обязательные переменные заполнены.
# Если что-то забыли указать в .env — бот сразу скажет, что именно, и не будет
# падать с непонятной ошибкой где-то в середине работы.
_missing = [
    name
    for name, value in (
        ("BOT_TOKEN", BOT_TOKEN),
        ("ADMIN_ID", ADMIN_ID_RAW),
        ("CHANNEL_USERNAME", CHANNEL_USERNAME),
        ("CHANNEL_ID", CHANNEL_ID_RAW),
        ("ELENA_ID", ELENA_ID_RAW),
        ("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY),
    )
    if not value
]
if _missing:
    print(
        "Ошибка: в файле .env не заполнены переменные: "
        + ", ".join(_missing)
        + "\nСкопируйте .env.example в .env и заполните значения."
    )
    sys.exit(1)

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    print("Ошибка: ADMIN_ID в .env должен быть числом (ваш Telegram user_id).")
    sys.exit(1)

try:
    CHANNEL_ID = int(CHANNEL_ID_RAW)
except ValueError:
    print("Ошибка: CHANNEL_ID в .env должен быть числом вида -100xxxxxxxxxx.")
    sys.exit(1)

try:
    ELENA_ID = int(ELENA_ID_RAW)
except ValueError:
    print("Ошибка: ELENA_ID в .env должен быть числом (Telegram user_id Елены).")
    sys.exit(1)

# Список гайдов: ключ — используется в callback-кнопках,
# title — текст на кнопке, file — имя PDF-файла в папке guides/,
# caption — сопроводительный текст, который отправляется вместе с файлом.
GUIDES = {
    "srk_diary": {
        "title": "5 техник снять спазм при СРК",
        "file": "srk_5_tehnik_spazm.pdf",
        "caption": (
            "Внутри — 5 простых техник, которые помогают снять спазм и боль при СРК "
            "прямо в моменте, когда накрывает. Не требуют подготовки — можно применить "
            "дома, на работе или в дороге."
        ),
    },
    "panic_4steps": {
        "title": "4 шага остановить панику",
        "file": "panic_4_shaga_ostanovit_paniku.pdf",
        "caption": (
            "Внутри — 4 простых шага, которые помогают остановить паническую атаку "
            "прямо в моменте. Можно держать под рукой и применить, когда почувствуете "
            "первые признаки накатывающей паники."
        ),
    },
    "relationships_5signs": {
        "title": "5 сигналов языка любви",
        "file": "5_signalov_yazyka_lyubvi.pdf",
        "caption": (
            "Внутри — 5 сигналов, которые помогают понять, на каком «языке любви» "
            "говорит ваш партнёр. Разобравшись в них, легче почувствовать друг друга "
            "и меньше ссориться на пустом месте."
        ),
    },
    "empathy_test": {
        "title": "Тест: эмпатия или выгорание",
        "file": "test_empatiya_ili_vygoranie.pdf",
        "caption": (
            "Небольшой тест поможет разобраться: то, что вы чувствуете сейчас — это "
            "живая эмпатия к другим или уже признаки эмоционального выгорания. "
            "Пройдите его честно, это займёт пару минут."
        ),
    },
    "srk_kniga": {
        "title": "Авторская методика от СРК",
        "file": "srk_kniga.pdf",
        "caption": (
            "Авторская методика восстановления Елены Семёновой — загляните в книгу "
            "изнутри: 2 рабочие техники и что вас ждёт в полной версии на 10 недель "
            "методики, плюс бонус в книге."
        ),
    },
}

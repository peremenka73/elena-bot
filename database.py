# Модуль отвечает за всю работу с базой данных SQLite.
# База данных — это просто файл data.db, который создаётся автоматически
# при первом запуске бота. Никакой отдельный сервер для неё не нужен.

import os
import sqlite3

import aiosqlite

# Если рядом есть папка data/ (постоянное хранилище на сервере — Volume у Bothost),
# кладём базу туда, чтобы она не терялась при перезапуске/пересборке бота.
# Локально такой папки нет — база просто лежит в корне проекта, как раньше.
_DATA_DIR = "data" if os.path.isdir("data") else "."
DB_PATH = os.path.join(_DATA_DIR, "data.db")


async def init_db() -> None:
    """Создаёт таблицы в базе данных, если их ещё нет. Вызывается один раз при старте бота."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                subscribed_at TEXT NOT NULL,
                is_subscribed_channel INTEGER NOT NULL DEFAULT 0,
                free_ai_questions_used INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # На случай, если бот уже запускался раньше со старой версией таблицы users
        # (без счётчика бесплатных вопросов ИИ) — добавляем колонку, если её ещё нет.
        try:
            await db.execute("ALTER TABLE users ADD COLUMN free_ai_questions_used INTEGER NOT NULL DEFAULT 0")
            await db.commit()
        except sqlite3.OperationalError:
            pass
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS guide_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guide_name TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS question_forwards (
                elena_message_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                answered INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS consultation_bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                consultation_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                requested_date TEXT NOT NULL,
                requested_time TEXT NOT NULL,
                confirmed_date TEXT,
                confirmed_time TEXT,
                proposed_slots TEXT,
                elena_request_message_id INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.commit()


async def upsert_user(user_id: int, username: str | None, first_name: str) -> None:
    """Добавляет пользователя в базу при первом обращении, либо обновляет его имя/username."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, username, first_name, subscribed_at, is_subscribed_channel)
            VALUES (?, ?, ?, datetime('now'), 0)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
            """,
            (user_id, username, first_name),
        )
        await db.commit()


async def set_subscription_status(user_id: int, is_subscribed: bool) -> None:
    """Обновляет отметку о том, подписан ли пользователь на канал (проверяется при каждом /start)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_subscribed_channel = ? WHERE user_id = ?",
            (1 if is_subscribed else 0, user_id),
        )
        await db.commit()


async def log_guide_request(user_id: int, guide_name: str) -> None:
    """Записывает в базу факт выдачи гайда пользователю."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO guide_requests (user_id, guide_name, requested_at) VALUES (?, ?, datetime('now'))",
            (user_id, guide_name),
        )
        await db.commit()


async def save_question_forward(elena_message_id: int, user_id: int) -> None:
    """Запоминает, какому пользователю отвечать, если Елена сделает Reply на пересланный вопрос."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO question_forwards (elena_message_id, user_id, created_at) VALUES (?, ?, datetime('now'))",
            (elena_message_id, user_id),
        )
        await db.commit()


async def get_user_id_by_question_message(elena_message_id: int) -> int | None:
    """По id сообщения, отправленного Елене, находит пользователя, которому нужно переслать её ответ."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM question_forwards WHERE elena_message_id = ?", (elena_message_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def mark_question_forward_answered(elena_message_id: int) -> None:
    """Отмечает вопрос как отвеченный — чтобы не подставлять его повторно как «последний без ответа»."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE question_forwards SET answered = 1 WHERE elena_message_id = ?", (elena_message_id,)
        )
        await db.commit()


async def get_latest_unanswered_question() -> tuple[int, int] | None:
    """Возвращает (elena_message_id, user_id) самого свежего вопроса без ответа, если такой есть."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT elena_message_id, user_id FROM question_forwards "
            "WHERE answered = 0 ORDER BY elena_message_id DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return (row[0], row[1]) if row else None


async def create_booking(
    user_id: int, consultation_type: str, requested_date: str, requested_time: str
) -> int:
    """Создаёт новую заявку на консультацию (статус 'pending'), возвращает её id."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO consultation_bookings
                (user_id, consultation_type, status, requested_date, requested_time, created_at)
            VALUES (?, ?, 'pending', ?, ?, datetime('now'))
            """,
            (user_id, consultation_type, requested_date, requested_time),
        )
        await db.commit()
        return cursor.lastrowid


async def set_booking_elena_message_id(booking_id: int, message_id: int) -> None:
    """Запоминает id сообщения с заявкой, отправленного Елене — на его кнопки она отвечает."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE consultation_bookings SET elena_request_message_id = ? WHERE id = ?",
            (message_id, booking_id),
        )
        await db.commit()


async def get_booking(booking_id: int) -> dict | None:
    """Возвращает данные заявки на консультацию в виде словаря, либо None, если такой нет."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM consultation_bookings WHERE id = ?", (booking_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_booking_status(booking_id: int, status: str) -> None:
    """Меняет статус заявки: pending / alternatives_proposed / confirmed."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE consultation_bookings SET status = ? WHERE id = ?", (status, booking_id))
        await db.commit()


async def save_proposed_slots(booking_id: int, slots_json: str) -> None:
    """Сохраняет 3 предложенных Еленой варианта (в виде JSON-строки) и переводит заявку в статус ожидания выбора."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE consultation_bookings SET proposed_slots = ?, status = 'alternatives_proposed' WHERE id = ?",
            (slots_json, booking_id),
        )
        await db.commit()


async def confirm_booking(booking_id: int, confirmed_date: str, confirmed_time: str) -> None:
    """Фиксирует итоговые дату и время консультации, статус — 'confirmed'."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE consultation_bookings SET status = 'confirmed', confirmed_date = ?, confirmed_time = ? "
            "WHERE id = ?",
            (confirmed_date, confirmed_time, booking_id),
        )
        await db.commit()


async def get_ai_questions_used(user_id: int) -> int:
    """Сколько бесплатных вопросов ИИ-ассистенту пользователь уже задал."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT free_ai_questions_used FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def increment_ai_questions_used(user_id: int) -> None:
    """Увеличивает счётчик заданных вопросов ИИ-ассистенту на 1."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET free_ai_questions_used = free_ai_questions_used + 1 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


async def get_all_user_ids() -> list[int]:
    """Возвращает список user_id всех пользователей, которые когда-либо писали боту. Используется для рассылки."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def get_stats() -> dict:
    """Собирает сводную статистику по боту — для команды /stats."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        total_users = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE is_subscribed_channel = 1")
        subscribed_users = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM guide_requests")
        total_guide_requests = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT guide_name, COUNT(*) FROM guide_requests GROUP BY guide_name ORDER BY COUNT(*) DESC"
        )
        guide_breakdown = await cursor.fetchall()

        cursor = await db.execute("SELECT COALESCE(SUM(free_ai_questions_used), 0) FROM users")
        total_ai_questions = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM consultation_bookings")
        total_bookings = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT status, COUNT(*) FROM consultation_bookings GROUP BY status")
        booking_breakdown = await cursor.fetchall()

        return {
            "total_users": total_users,
            "subscribed_users": subscribed_users,
            "total_guide_requests": total_guide_requests,
            "guide_breakdown": guide_breakdown,
            "total_ai_questions": total_ai_questions,
            "total_bookings": total_bookings,
            "booking_breakdown": booking_breakdown,
        }

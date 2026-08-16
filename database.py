# Модуль отвечает за всю работу с базой данных SQLite.
# База данных — это просто файл data.db, который создаётся автоматически
# при первом запуске бота. Никакой отдельный сервер для неё не нужен.

import sqlite3

import aiosqlite

DB_PATH = "data.db"


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
            CREATE TABLE IF NOT EXISTS booking_forwards (
                elena_message_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                answered INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # На случай, если бот уже запускался раньше со старой версией таблицы
        # (без колонки answered) — добавляем колонку, если её ещё нет.
        try:
            await db.execute("ALTER TABLE booking_forwards ADD COLUMN answered INTEGER NOT NULL DEFAULT 0")
            await db.commit()
        except sqlite3.OperationalError:
            pass
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


async def save_booking_forward(elena_message_id: int, user_id: int) -> None:
    """Запоминает, какому пользователю отвечать, если Елена сделает Reply на это сообщение."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO booking_forwards (elena_message_id, user_id, created_at) VALUES (?, ?, datetime('now'))",
            (elena_message_id, user_id),
        )
        await db.commit()


async def get_user_id_by_elena_message(elena_message_id: int) -> int | None:
    """По id сообщения, отправленного Елене, находит пользователя, которому нужно переслать её ответ."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM booking_forwards WHERE elena_message_id = ?",
            (elena_message_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def mark_booking_forward_answered(elena_message_id: int) -> None:
    """Отмечает заявку как отвеченную — чтобы не подставлять её повторно как «последнюю без ответа»."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE booking_forwards SET answered = 1 WHERE elena_message_id = ?",
            (elena_message_id,),
        )
        await db.commit()


async def get_latest_unanswered_booking() -> tuple[int, int] | None:
    """Возвращает (elena_message_id, user_id) самой свежей заявки без ответа, если такая есть."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT elena_message_id, user_id FROM booking_forwards "
            "WHERE answered = 0 ORDER BY elena_message_id DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return (row[0], row[1]) if row else None


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

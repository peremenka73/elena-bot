# Общая функция проверки подписки на канал — используется и в /start, и в /guides.

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest

from config import CHANNEL_ID

# Эти статусы участника чата означают, что человек подписан на канал.
# "left" и "kicked" — не подписан.
SUBSCRIBED_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}


async def is_user_subscribed(bot: Bot, user_id: int) -> bool:
    """Проверяет через Telegram Bot API, подписан ли пользователь на канал Елены."""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
    except TelegramBadRequest:
        # Например, бот не является админом канала, или пользователь никогда
        # не взаимодействовал с каналом — в таком случае считаем, что не подписан.
        return False
    return member.status in SUBSCRIBED_STATUSES

import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from app.config import settings

log = logging.getLogger(__name__)
_bot = None
_dp = None


def get_bot():
    global _bot, _dp
    if _bot is None:
        if not settings.bot_token:
            raise RuntimeError("BOT_TOKEN is not configured")
        _bot = Bot(settings.bot_token)
        _dp = Dispatcher()
        @_dp.message(CommandStart())
        async def start_handler(message: Message):
            if message.from_user and message.from_user.id not in settings.admins:
                await message.answer("You are not authorized to use this recovery dashboard.")
                return
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Open Recovery Dashboard", web_app=WebAppInfo(url=settings.webapp_url))
            ]])
            await message.answer(
                "File Store Link Recovery\n\nScan channel history, preview affected buttons, and replace an old File Store bot username while preserving each start token.",
                reply_markup=keyboard,
            )
        @_dp.message(F.text == "/help")
        async def help_handler(message: Message):
            await message.answer("Use /start to open the Recovery Dashboard.")
    return _bot, _dp


async def run_bot():
    bot, dp = get_bot()
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from app.config import settings


async def main():
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise SystemExit("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env first.")
    async with TelegramClient(StringSession(), settings.telegram_api_id, settings.telegram_api_hash) as client:
        print("\nYour session string (keep it secret):\n")
        print(StringSession.save(client.session))
        print("\nCopy it into TELEGRAM_SESSION_STRING in your hosting secrets.\n")


if __name__ == "__main__":
    asyncio.run(main())

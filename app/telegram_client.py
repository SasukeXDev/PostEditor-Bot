import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from app.config import settings

log = logging.getLogger(__name__)
_client: TelegramClient | None = None


def get_client() -> TelegramClient:
    global _client
    if _client is None:
        if not settings.telegram_api_id or not settings.telegram_api_hash or not settings.telegram_session_string:
            raise RuntimeError("TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_SESSION_STRING are required")
        _client = TelegramClient(
            StringSession(settings.telegram_session_string),
            settings.telegram_api_id,
            settings.telegram_api_hash,
            flood_sleep_threshold=60,
            request_retries=3,
            connection_retries=5,
        )
    return _client


async def start_client():
    client = get_client()
    await client.start()
    me = await client.get_me()
    if not me:
        raise RuntimeError("MTProto session did not authorize")
    log.info("MTProto client connected as user id %s", me.id)
    return client


async def stop_client():
    global _client
    if _client:
        await _client.disconnect()
        _client = None

import logging
from datetime import datetime, timezone
from telethon.tl.types import KeyboardButtonUrl
from app.db import db
from app.telegram_client import get_client

log = logging.getLogger(__name__)


def message_button_records(message):
    records = []
    markup = getattr(message, "reply_markup", None)
    rows = getattr(markup, "rows", []) if markup else []
    for row_idx, row in enumerate(rows):
        for col_idx, button in enumerate(getattr(row, "buttons", [])):
            url = getattr(button, "url", None)
            label = getattr(button, "text", None) or ""
            records.append({
                "row": row_idx,
                "col": col_idx,
                "label": label,
                "url": url,
                "button_type": type(button).__name__,
                "is_url_button": bool(url),
            })
    return records


async def index_message(channel_key: str, message):
    buttons = message_button_records(message)
    now = datetime.now(timezone.utc)
    doc = {
        "channel_key": channel_key,
        "message_id": int(message.id),
        "date": message.date,
        "text_preview": (getattr(message, "message", "") or "")[:240],
        "has_media": bool(getattr(message, "media", None)),
        "buttons": buttons,
        "button_count": len(buttons),
        "indexed_at": now,
        "edited_at": now,
    }
    await db().posts.update_one(
        {"channel_key": channel_key, "message_id": int(message.id)},
        {"$set": doc},
        upsert=True,
    )
    return doc


async def scan_channel(channel_key: str, job_id: str):
    client = get_client()
    channel = await client.get_entity(channel_key)
    resolved_key = str(getattr(channel, "username", None) or getattr(channel, "id", channel_key))
    # Keep the user-supplied key as the stable app key; store resolved channel metadata separately.
    await db().channels.update_one(
        {"channel_key": channel_key},
        {"$set": {"resolved_id": int(getattr(channel, "id", 0)), "title": getattr(channel, "title", channel_key),
                  "username": getattr(channel, "username", None), "last_scan_started_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    job = await db().jobs.find_one({"job_id": job_id})
    checkpoint = int((job or {}).get("checkpoint_message_id", 0))
    scanned = 0
    max_count = int(__import__("app.config", fromlist=["settings"]).settings.max_scan_messages_per_channel or 0)
    # Resume by walking newest-to-oldest and skipping messages already covered by checkpoint.
    # We persist the smallest ID encountered so an interrupted scan can continue backwards.
    async for message in client.iter_messages(channel):
        # Messages arrive newest-to-oldest. On resume, skip the already-scanned
        # range (IDs >= the smallest checkpoint) and continue into older history.
        if checkpoint and message.id >= checkpoint:
            continue
        await index_message(channel_key, message)
        scanned += 1
        await db().jobs.update_one(
            {"job_id": job_id},
            {"$set": {"checkpoint_message_id": int(message.id), "updated_at": datetime.now(timezone.utc)},
             "$inc": {"scanned_count": 1}},
        )
        if max_count and scanned >= max_count:
            break
    await db().channels.update_one(
        {"channel_key": channel_key},
        {"$set": {"last_scanned_at": datetime.now(timezone.utc), "scan_status": "completed"}},
        upsert=True,
    )
    return {"scanned": scanned, "channel": resolved_key}


async def refresh_post(channel_key: str, message_id: int):
    client = get_client()
    channel = await client.get_entity(channel_key)
    message = await client.get_messages(channel, ids=message_id)
    if message:
        await index_message(channel_key, message)
    return message

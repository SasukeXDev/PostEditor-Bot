import asyncio
import copy
import logging
from datetime import datetime, timezone
from telethon import functions, types, errors
from app.db import db
from app.links import replace_bot_username
from app.telegram_client import get_client
from app.scanner import index_message

log = logging.getLogger(__name__)


def rewritten_markup(message, old_username: str, new_username: str):
    """Clone inline markup and alter only matching URL fields on buttons."""
    markup = getattr(message, "reply_markup", None)
    if not markup or not getattr(markup, "rows", None):
        return None, []
    new_markup = copy.deepcopy(markup)
    changes = []
    for row_idx, row in enumerate(getattr(new_markup, "rows", [])):
        for col_idx, button in enumerate(getattr(row, "buttons", [])):
            old_url = getattr(button, "url", None)
            if not old_url:
                continue
            new_url = replace_bot_username(old_url, old_username, new_username)
            if new_url and new_url != old_url:
                button.url = new_url
                changes.append({
                    "row": row_idx,
                    "col": col_idx,
                    "label": getattr(button, "text", "") or "",
                    "old_url": old_url,
                    "new_url": new_url,
                    "button_type": type(button).__name__,
                })
    return (new_markup if changes else None), changes


async def preview_replacement(channel_key: str, old_username: str, new_username: str, limit: int = 1000):
    cursor = db().posts.find({"channel_key": channel_key}).sort("message_id", -1).limit(max(1, min(limit, 10000)))
    rows = []
    count = 0
    post_ids = set()
    async for post in cursor:
        matches = []
        for button in post.get("buttons", []):
            url = button.get("url")
            new_url = replace_bot_username(url, old_username, new_username) if url else None
            if new_url and new_url != url:
                matches.append({"row": button.get("row"), "col": button.get("col"), "label": button.get("label", ""),
                                "old_url": url, "new_url": new_url})
        if matches:
            count += len(matches)
            post_ids.add(post["message_id"])
            if len(rows) < 100:
                rows.append({"message_id": post["message_id"], "text_preview": post.get("text_preview", ""),
                             "matches": matches})
    return {"matching_posts": len(post_ids), "matching_buttons": count, "sample": rows}


async def apply_job(job: dict):
    client = get_client()
    job_id = job["job_id"]
    channel_key = job["channel_key"]
    old_username = job["old_username"]
    new_username = job["new_username"]
    await db().jobs.update_one({"job_id": job_id}, {"$set": {"status": "running", "started_at": datetime.now(timezone.utc)}})
    cursor = db().posts.find({"channel_key": channel_key}).sort("message_id", 1)
    processed = 0
    async for indexed in cursor:
        if int(indexed["message_id"]) <= int(job.get("last_message_id", 0)):
            continue
        message_id = int(indexed["message_id"])
        try:
            channel = await client.get_entity(channel_key)
            message = await client.get_messages(channel, ids=message_id)
            if not message:
                await record_result(job_id, channel_key, message_id, "skipped", "Message unavailable")
                await advance(job_id, message_id)
                continue
            new_markup, changes = rewritten_markup(message, old_username, new_username)
            if not changes:
                # Refresh the index to keep it aligned with current Telegram state.
                await index_message(channel_key, message)
                await record_result(job_id, channel_key, message_id, "skipped", "No matching button in current message")
                await advance(job_id, message_id)
                continue
            # Only reply_markup is sent. No message text, media, or caption is passed.
            await client(functions.messages.EditMessageRequest(
                peer=channel,
                id=message_id,
                reply_markup=new_markup,
            ))
            await record_result(job_id, channel_key, message_id, "success", f"Updated {len(changes)} button(s)", changes)
            # Re-fetch after editing so indexed state reflects the server's current markup.
            latest = await client.get_messages(channel, ids=message_id)
            if latest:
                await index_message(channel_key, latest)
            await db().jobs.update_one({"job_id": job_id}, {"$inc": {"updated_buttons": len(changes), "updated_posts": 1}})
            await advance(job_id, message_id)
            processed += 1
            from app.config import settings
            await asyncio.sleep(max(0.2, settings.edit_delay_seconds))
        except errors.FloodWaitError as exc:
            wait_seconds = int(getattr(exc, "seconds", 30)) + 1
            await db().jobs.update_one({"job_id": job_id}, {"$set": {"status": "queued", "last_error": f"FloodWait: {wait_seconds}s"}})
            log.warning("FloodWait on job %s: sleeping %s seconds", job_id, wait_seconds)
            await asyncio.sleep(wait_seconds)
            # Do not advance checkpoint on a rate-limit exception; job will retry.
            raise
        except Exception as exc:
            log.exception("Failed editing %s/%s", channel_key, message_id)
            await record_result(job_id, channel_key, message_id, "failed", str(exc)[:500])
            await advance(job_id, message_id)
    await db().jobs.update_one({"job_id": job_id}, {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}})
    return {"processed": processed}


async def advance(job_id: str, message_id: int):
    await db().jobs.update_one({"job_id": job_id}, {"$max": {"last_message_id": int(message_id)},
                                                 "$set": {"updated_at": datetime.now(timezone.utc)}})


async def record_result(job_id, channel_key, message_id, status, detail, changes=None):
    await db().audit_logs.insert_one({
        "job_id": job_id, "channel_key": channel_key, "message_id": int(message_id),
        "status": status, "detail": detail, "changes": changes or [],
        "created_at": datetime.now(timezone.utc),
    })
    await db().jobs.update_one({"job_id": job_id}, {"$inc": {f"{status}_posts": 1}})

import asyncio
import logging
from datetime import datetime, timezone
from telethon import events
from app.config import settings
from app.db import connect_db, db, close_db
from app.telegram_client import start_client, stop_client
from app.scanner import scan_channel, index_message
from app.editor import apply_job, rewritten_markup
from telethon import functions
from app.bot import run_bot

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


async def process_job(job):
    job_id = job["job_id"]
    try:
        if job.get("type") == "scan":
            await db().jobs.update_one({"job_id": job_id}, {"$set": {"status": "running", "started_at": datetime.now(timezone.utc)}})
            result = await scan_channel(job["channel_key"], job_id)
            await db().jobs.update_one({"job_id": job_id}, {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc), "result": result}})
        elif job.get("type") == "replace":
            await apply_job(job)
        else:
            await db().jobs.update_one({"job_id": job_id}, {"$set": {"status": "failed", "last_error": "Unknown job type"}})
    except Exception as exc:
        log.exception("Job %s failed", job_id)
        # Persist as queued for resumable retry on transient failures, but avoid a tight retry loop.
        await db().jobs.update_one({"job_id": job_id}, {"$set": {"status": "queued", "last_error": str(exc)[:500], "updated_at": datetime.now(timezone.utc)}})
        await asyncio.sleep(5)


async def monitor_new_posts(client):
    # Resolve configured channels; channel IDs/usernames are registered in MongoDB.
    async def on_new_message(event):
        try:
            chat = await event.get_chat()
            key = "@" + chat.username if getattr(chat, "username", None) else str(getattr(chat, "id", ""))
            registered = await db().channels.find_one({"$or": [{"channel_key": key}, {"resolved_id": int(getattr(chat, "id", 0))}]})
            if registered and registered.get("monitor_new_posts", False):
                await index_message(registered["channel_key"], event.message)
                old_user = registered.get("old_username")
                new_user = registered.get("new_username")
                if old_user and new_user:
                    markup, changes = rewritten_markup(event.message, old_user, new_user)
                    if markup and changes:
                        # Only update reply markup; message text/media/caption remain untouched.
                        await client(functions.messages.EditMessageRequest(
                            peer=event.chat_id,
                            id=event.message.id,
                            reply_markup=markup,
                        ))
                        log.info("Auto-recovered %s button(s) in new post %s", len(changes), event.message.id)
                        latest = await client.get_messages(event.chat_id, ids=event.message.id)
                        if latest:
                            await index_message(registered["channel_key"], latest)
        except Exception:
            log.exception("Failed to index new channel post")

    client.add_event_handler(on_new_message, events.NewMessage())


async def main():
    await connect_db()
    client = await start_client()
    await monitor_new_posts(client)
    # Add configured channels to monitoring list.
    for channel in settings.default_channels:
        await db().channels.update_one({"channel_key": channel},
            {"$set": {"channel_key": channel, "monitor_new_posts": True},
             "$setOnInsert": {"created_at": datetime.now(timezone.utc), "scan_status": "not_scanned"}}, upsert=True)
    bot_task = None
    if settings.bot_token:
        bot_task = asyncio.create_task(run_bot())
    try:
        while True:
            job = await db().jobs.find_one_and_update(
                {"status": "queued"},
                {"$set": {"status": "claimed", "claimed_at": datetime.now(timezone.utc)}},
                sort=[("created_at", 1)],
            )
            if job:
                await process_job(job)
            else:
                await asyncio.sleep(max(0.5, settings.worker_poll_seconds))
    finally:
        if bot_task:
            bot_task.cancel()
        await stop_client()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())

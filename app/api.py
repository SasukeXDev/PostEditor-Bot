import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.auth import require_admin
from app.db import db
from app.links import normalize_username
from app.scanner import scan_channel
from app.editor import preview_replacement
from app.config import settings

router = APIRouter(prefix="/api")


class ChannelIn(BaseModel):
    channel: str = Field(min_length=2, max_length=128)


class ReplacementIn(BaseModel):
    channel_key: str
    old_username: str
    new_username: str
    preview_limit: int = 1000


class MonitorIn(BaseModel):
    channel: str = Field(min_length=2, max_length=128)
    old_username: str
    new_username: str


class ConfirmIn(ReplacementIn):
    confirm: bool = False


def normalize_channel(value: str) -> str:
    value = value.strip()
    if value.startswith("https://t.me/"):
        value = "@" + value.rstrip("/").split("/")[-1]
    if not (value.startswith("@") or value.lstrip("-").isdigit()):
        raise ValueError("Use a public channel username (@channel) or numeric channel ID (-100...).")
    return value


@router.get("/me")
async def me(auth=Depends(require_admin)):
    return {"ok": True, "user_id": auth["user_id"], "user": auth["user"]}


@router.get("/channels")
async def list_channels(auth=Depends(require_admin)):
    items = []
    async for item in db().channels.find({}).sort("created_at", -1):
        item.pop("_id", None)
        items.append(item)
    return {"channels": items}


@router.post("/channels")
async def add_channel(body: ChannelIn, auth=Depends(require_admin)):
    try:
        channel_key = normalize_channel(body.channel)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await db().channels.update_one(
        {"channel_key": channel_key},
        {"$set": {"channel_key": channel_key, "added_by": auth["user_id"], "updated_at": datetime.now(timezone.utc)},
         "$setOnInsert": {"created_at": datetime.now(timezone.utc), "scan_status": "not_scanned"}},
        upsert=True,
    )
    return {"ok": True, "channel_key": channel_key}


@router.post("/scan")
async def start_scan(body: ChannelIn, auth=Depends(require_admin)):
    try:
        channel_key = normalize_channel(body.channel)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await db().channels.update_one(
        {"channel_key": channel_key},
        {"$set": {"channel_key": channel_key, "added_by": auth["user_id"], "scan_status": "queued"},
         "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    job_id = secrets.token_urlsafe(12)
    await db().jobs.insert_one({
        "job_id": job_id, "type": "scan", "channel_key": channel_key, "status": "queued",
        "created_by": auth["user_id"], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
        "checkpoint_message_id": 0, "scanned_count": 0,
    })
    return {"ok": True, "job_id": job_id}


@router.post("/preview")
async def preview(body: ReplacementIn, auth=Depends(require_admin)):
    try:
        old = normalize_username(body.old_username)
        new = normalize_username(body.new_username)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if old.casefold() == new.casefold():
        raise HTTPException(400, "Old and new usernames must be different.")
    channel_key = normalize_channel(body.channel_key)
    result = await preview_replacement(channel_key, old, new, body.preview_limit)
    return {"ok": True, "channel_key": channel_key, "old_username": old, "new_username": new, **result}


@router.post("/replace")
async def create_replace_job(body: ConfirmIn, auth=Depends(require_admin)):
    if not body.confirm:
        raise HTTPException(400, "Explicit confirmation is required.")
    try:
        old = normalize_username(body.old_username)
        new = normalize_username(body.new_username)
        channel_key = normalize_channel(body.channel_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if old.casefold() == new.casefold():
        raise HTTPException(400, "Old and new usernames must be different.")
    preview = await preview_replacement(channel_key, old, new, body.preview_limit)
    if not preview["matching_buttons"]:
        raise HTTPException(400, "No matching buttons found. Scan the channel first.")
    job_id = secrets.token_urlsafe(12)
    await db().jobs.insert_one({
        "job_id": job_id, "type": "replace", "channel_key": channel_key,
        "old_username": old, "new_username": new, "status": "queued",
        "created_by": auth["user_id"], "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc), "last_message_id": 0,
        "preview_matching_posts": preview["matching_posts"],
        "preview_matching_buttons": preview["matching_buttons"],
        "updated_posts": 0, "updated_buttons": 0, "failed_posts": 0, "skipped_posts": 0,
    })
    return {"ok": True, "job_id": job_id, "preview": preview}


@router.get("/jobs")
async def jobs(auth=Depends(require_admin)):
    items = []
    async for item in db().jobs.find({}).sort("created_at", -1).limit(100):
        item.pop("_id", None)
        items.append(item)
    return {"jobs": items}


@router.get("/posts")
async def posts(channel: str, q: str = "", page: int = 1, auth=Depends(require_admin)):
    channel_key = normalize_channel(channel)
    query = {"channel_key": channel_key}
    if q:
        query["$or"] = [
            {"text_preview": {"$regex": q[:80], "$options": "i"}},
            {"buttons.url": {"$regex": q[:200], "$options": "i"}},
            {"buttons.label": {"$regex": q[:80], "$options": "i"}},
        ]
    page = max(1, page)
    cursor = db().posts.find(query, {"_id": 0}).sort("message_id", -1).skip((page - 1) * 50).limit(50)
    items = [item async for item in cursor]
    total = await db().posts.count_documents(query)
    return {"posts": items, "total": total, "page": page}


@router.get("/audit")
async def audit(job_id: str, auth=Depends(require_admin)):
    cursor = db().audit_logs.find({"job_id": job_id}, {"_id": 0}).sort("created_at", -1).limit(500)
    return {"items": [item async for item in cursor]}


@router.post("/monitor")
async def monitor(body: MonitorIn, auth=Depends(require_admin)):
    try:
        channel_key = normalize_channel(body.channel)
        old = normalize_username(body.old_username)
        new = normalize_username(body.new_username)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if old.casefold() == new.casefold():
        raise HTTPException(400, "Old and new usernames must be different.")
    await db().channels.update_one({"channel_key": channel_key},
        {"$set": {"channel_key": channel_key, "monitor_new_posts": True,
                   "old_username": old, "new_username": new,
                   "updated_at": datetime.now(timezone.utc)},
         "$setOnInsert": {"created_at": datetime.now(timezone.utc), "scan_status": "not_scanned"}}, upsert=True)
    return {"ok": True, "channel_key": channel_key, "monitor_new_posts": True,
            "old_username": old, "new_username": new}

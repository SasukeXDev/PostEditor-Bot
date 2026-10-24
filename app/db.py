from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

_client = None
_db = None


async def connect_db():
    global _client, _db
    if not settings.mongodb_uri:
        raise RuntimeError("MONGODB_URI is not configured")
    _client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=10000)
    await _client.admin.command("ping")
    _db = _client[settings.mongodb_database]
    await _db.channels.create_index("channel_key", unique=True)
    await _db.posts.create_index([("channel_key", 1), ("message_id", 1)], unique=True)
    await _db.posts.create_index([("buttons.url", 1)])
    await _db.jobs.create_index([("status", 1), ("created_at", 1)])
    await _db.audit_logs.create_index([("job_id", 1), ("created_at", 1)])
    await _db.jobs.create_index("job_id", unique=True)
    return _db


def db():
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


async def close_db():
    global _client, _db
    if _client:
        _client.close()
    _client = None
    _db = None

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl
from fastapi import Header, HTTPException
from app.config import settings


def validate_init_data(init_data: str, max_age_seconds: int = 86400) -> dict:
    if not init_data or not settings.bot_token:
        raise HTTPException(status_code=401, detail="Missing Telegram Web App authentication")
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Invalid Telegram Web App data")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="Telegram Web App signature validation failed")
    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid auth date")
    if auth_date <= 0 or abs(time.time() - auth_date) > max_age_seconds:
        raise HTTPException(status_code=401, detail="Telegram Web App data expired")
    try:
        user = json.loads(parsed.get("user", "{}"))
        user_id = int(user["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Telegram user not found")
    if settings.admins and user_id not in settings.admins:
        raise HTTPException(status_code=403, detail="Not authorized")
    if not settings.admins:
        raise HTTPException(status_code=403, detail="ADMIN_USER_IDS is not configured")
    return {"user_id": user_id, "user": user}


async def require_admin(x_telegram_init_data: str = Header(default="", alias="X-Telegram-Init-Data")):
    return validate_init_data(x_telegram_init_data)

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(default="")
    bot_username: str = Field(default="")
    webapp_url: str = Field(default="http://localhost:8000")
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_session_string: str = ""
    mongodb_uri: str = ""
    mongodb_database: str = "telegram_recovery"
    admin_user_ids: str = ""
    monitor_channels: str = ""
    host: str = "0.0.0.0"
    port: int = 8000
    role: str = "all"
    log_level: str = "INFO"
    max_scan_messages_per_channel: int = 0
    worker_poll_seconds: float = 2.0
    edit_delay_seconds: float = 1.0

    @property
    def admins(self) -> set[int]:
        result = set()
        for part in self.admin_user_ids.split(","):
            part = part.strip()
            if part.isdigit():
                result.add(int(part))
        return result

    @property
    def default_channels(self) -> list[str]:
        return [x.strip() for x in self.monitor_channels.split(",") if x.strip()]


settings = Settings()

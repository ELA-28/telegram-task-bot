import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    bot_token: str
    openai_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///tasks.db"
    timezone: str = "Europe/Moscow"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Используем постоянный диск на Render для хранения БД
        if os.environ.get("RENDER") == "true":
            # На Render используем persistent disk
            persist_dir = "/opt/render/project/persistent"
            os.makedirs(persist_dir, exist_ok=True)
            self.database_url = f"sqlite+aiosqlite:///{persist_dir}/tasks.db"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

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
        # Приоритет для DATABASE_URL из environment (Neon)
        db_url = os.environ.get("DATABASE_URL")
        if db_url:
            # Преобразуем postgres:// в postgresql+asyncpg:// для SQLAlchemy async
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            self.database_url = db_url
        # Если на Render нет DATABASE_URL, используем SQLite (локально)
        elif os.environ.get("RENDER") == "true":
            persist_dir = "/opt/render/project/persistent"
            os.makedirs(persist_dir, exist_ok=True)
            self.database_url = f"sqlite+aiosqlite:///{persist_dir}/tasks.db"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

import os
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "EvidenceGuard"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "dev-secret-key-32-chars-minimum-length!"

    # Database
    POSTGRES_USER: str = "evidenceguard"
    POSTGRES_PASSWORD: str = "evidenceguard_password"
    POSTGRES_DB: str = "evidenceguard_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = "postgresql+asyncpg://evidenceguard:evidenceguard_password@localhost:5432/evidenceguard_db"

    # LLM
    LLM_PROVIDER: Literal["ollama", "openai", "mock"] = "mock"
    LLM_BASE_URL: str = "http://localhost:11434/v1"
    LLM_MODEL: str = "llama3:8b"
    OPENAI_API_KEY: str = "not-needed-for-local"

    # Embedding
    EMBEDDING_PROVIDER: Literal["mock", "openai", "ollama"] = "mock"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536

    # Storage
    STORAGE_DIR: str = "./uploads"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# Ensure uploads directory exists
os.makedirs(settings.STORAGE_DIR, exist_ok=True)

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


APP_VERSION = "0.5.0-m5"
DEFAULT_CORS_ORIGINS = ("http://127.0.0.1:3000", "http://localhost:3000")


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or Path.cwd() / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class AppSettings:
    app_env: str
    llm_provider: str
    llm_model: str
    llm_api_key: str
    llm_timeout_seconds: float
    llm_schema_retry: int
    database_url: str
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS

    @property
    def provider_configured(self) -> bool:
        if self.llm_provider == "mock":
            return True
        return bool(self.llm_api_key and self.llm_model)


def get_settings() -> AppSettings:
    load_dotenv()
    return AppSettings(
        app_env=os.getenv("APP_ENV", "development").lower(),
        llm_provider=os.getenv("LLM_PROVIDER", "mock").lower(),
        llm_model=os.getenv("LLM_MODEL", "mock-v1"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "30") or 30),
        llm_schema_retry=int(os.getenv("LLM_SCHEMA_RETRY", "1") or 1),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./backend/data/app.db"),
        cors_origins=_parse_csv_env(os.getenv("CORS_ORIGINS"), DEFAULT_CORS_ORIGINS),
    )


def _parse_csv_env(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    parsed = tuple(item.strip() for item in value.split(",") if item.strip())
    return parsed or default

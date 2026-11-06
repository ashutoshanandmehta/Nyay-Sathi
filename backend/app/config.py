from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    app_name: str = "Nyay Saathi"
    app_origin: str = "http://localhost:5173"
    database_path: Path = ROOT / "runtime" / "nyay_saathi.sqlite3"
    checkpoint_path: Path = ROOT / "runtime" / "checkpoints.sqlite3"
    chroma_path: Path = ROOT / "runtime" / "chroma"
    upload_path: Path = ROOT / "runtime" / "uploads"
    export_path: Path = ROOT / "runtime" / "exports"
    openai_api_key: str | None = None
    openai_chat_model: str = "gpt-6-luna"
    openai_review_model: str = "gpt-6.1-sol"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_transcription_model: str = "gpt-transcribe"
    openai_tts_model: str = "gpt-realtime-2.1-mini"
    openai_web_search_model: str = "gpt-6-astra"
    assistant_engine: Literal["primary_agent", "legacy"] = "primary_agent"
    vector_index_enabled: bool = False
    agent_max_requests: int = Field(default=6, ge=1, le=8)
    agent_max_rounds: int = Field(default=3, ge=1, le=4)
    agent_max_tokens: int = Field(default=160000, ge=2000, le=200000)
    agent_max_output_tokens: int = Field(default=6000, ge=1000, le=16000)
    agent_context_chars: int = Field(default=36000, ge=8000, le=100000)
    agent_deadline_seconds: float = Field(default=60, ge=5, le=180)
    agent_research_seconds: float = Field(default=20, ge=1, le=60)
    agent_max_batches: int = Field(default=2, ge=0, le=2)
    agent_max_queries: int = Field(default=3, ge=0, le=4)
    agent_max_documents: int = Field(default=6, ge=0, le=8)
    agent_fetch_concurrency: int = Field(default=3, ge=1, le=4)
    agent_search_concurrency: int = Field(default=2, ge=1, le=2)
    agent_max_passages: int = Field(default=5, ge=1, le=8)
    agent_reasoning_effort: str | None = None
    agent_max_cost_usd: float | None = Field(default=None, gt=0)
    # Empty pricing means unknown cost, never free usage. Set from dated provider pricing.
    agent_pricing: dict[str, dict[str, float]] = Field(default_factory=dict)
    agent_pricing_date: str | None = None
    live_eval_max_cost_usd: float = Field(default=0, ge=0)
    cookie_secure: bool = False
    max_model_calls_per_turn: int = Field(default=8, ge=1, le=8)
    web_research_enabled: bool = True
    web_max_queries: int = Field(default=2, ge=1, le=2)
    web_max_documents: int = Field(default=3, ge=1, le=3)
    web_research_timeout_seconds: float = Field(default=40, ge=5, le=90)
    web_max_download_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    web_max_pdf_pages: int = Field(default=60, ge=1, le=100)
    web_cache_ttl_seconds: float = Field(default=3600, ge=0, le=86400)
    live_eval_max_cases: int = Field(default=0, ge=0, le=20)
    live_eval_max_model_calls: int = Field(default=0, ge=0, le=100)
    max_upload_bytes: int = 10 * 1024 * 1024
    max_pdf_pages: int = 50
    model_timeout_seconds: float = 65.0
    requests_per_minute: int = Field(default=120, ge=10, le=6000)

    @property
    def ai_configured(self) -> bool:
        return bool(self.openai_api_key)

    def ensure_dirs(self) -> None:
        for path in (
            self.database_path.parent,
            self.chroma_path,
            self.upload_path,
            self.export_path,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings

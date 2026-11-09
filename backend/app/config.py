import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.security.user_key import current_user_key

ROOT = Path(__file__).resolve().parents[2]
IS_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
DEFAULT_RUNTIME_DIR = (Path("/tmp") / "nyay_saathi") if IS_SERVERLESS else (ROOT / "runtime")
DEFAULT_AGENT_DEADLINE = 50.0 if IS_SERVERLESS else 180.0
DEFAULT_AGENT_RESEARCH = 18.0 if IS_SERVERLESS else 45.0
DEFAULT_REPAIR_MIN_REMAINING = 12.0 if IS_SERVERLESS else 25.0
DEFAULT_WEB_RESEARCH_TIMEOUT = 10.0 if IS_SERVERLESS else 40.0
DEFAULT_MODEL_TIMEOUT = 45.0 if IS_SERVERLESS else 120.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    app_name: str = "Nyay Saathi"
    app_origin: str = "http://localhost:5173"
    database_path: Path = DEFAULT_RUNTIME_DIR / "nyay_saathi.sqlite3"
    checkpoint_path: Path = DEFAULT_RUNTIME_DIR / "checkpoints.sqlite3"
    chroma_path: Path = DEFAULT_RUNTIME_DIR / "chroma"
    upload_path: Path = DEFAULT_RUNTIME_DIR / "uploads"
    export_path: Path = DEFAULT_RUNTIME_DIR / "exports"
    openai_api_key: str | None = None
    openai_chat_model: str = "gpt-6-luna"
    openai_review_model: str = "gpt-6.1-sol"
    openai_planner_model: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_transcription_model: str = "gpt-transcribe"
    openai_tts_model: str = "gpt-realtime-2.1-mini"
    openai_web_search_model: str = "gpt-6-astra"
    # Live voice input over WebRTC; gpt-realtime-whisper with "minimal" delay is the fastest.
    openai_live_transcription_model: str = "gpt-realtime-whisper"
    live_transcription_delay: Literal["minimal", "low", "medium", "high", "xhigh"] = "minimal"
    voice_max_seconds: int = Field(default=180, ge=10, le=600)
    assistant_engine: Literal["primary_agent", "legacy"] = "primary_agent"
    agent_planning_mode: Literal["none", "embedded", "separate_planner"] = "embedded"
    vector_index_enabled: bool = False
    # Upper caps, not targets: quality first, the agent uses only what a turn needs.
    agent_max_requests: int = Field(default=14, ge=1, le=24)
    agent_max_rounds: int = Field(default=5, ge=1, le=8)
    agent_max_tokens: int = Field(default=400000, ge=2000, le=1000000)
    agent_max_output_tokens: int = Field(default=6000, ge=1000, le=16000)
    agent_context_chars: int = Field(default=36000, ge=8000, le=100000)
    agent_deadline_seconds: float = Field(default=DEFAULT_AGENT_DEADLINE, ge=5, le=300)
    agent_repair_min_remaining_seconds: float = Field(default=DEFAULT_REPAIR_MIN_REMAINING, ge=0.0, le=180.0)
    # Requests research may never consume: one repair plus its mandatory re-review.
    agent_repair_reserve: int = Field(default=2, ge=0, le=6)
    agent_max_repairs: int = Field(default=2, ge=0, le=3)
    agent_research_seconds: float = Field(default=DEFAULT_AGENT_RESEARCH, ge=1, le=120)
    # Share of the research window searches may use; fetching keeps the rest.
    agent_search_share: float = Field(default=0.5, ge=0.1, le=0.9)
    agent_max_batches: int = Field(default=3, ge=0, le=4)
    agent_max_queries: int = Field(default=6, ge=0, le=8)
    agent_max_documents: int = Field(default=10, ge=0, le=16)
    agent_fetch_concurrency: int = Field(default=3, ge=1, le=4)
    agent_search_concurrency: int = Field(default=2, ge=1, le=2)
    agent_max_passages: int = Field(default=8, ge=1, le=16)
    agent_passages_per_source: int = Field(default=4, ge=1, le=8)
    agent_reasoning_effort: str | None = None
    # Roleplay replies are short and in character: favour speed. Unset to use the model default.
    openai_roleplay_model: str | None = None
    practice_reasoning_effort: str | None = "low"
    agent_max_cost_usd: float | None = Field(default=None, gt=0)
    # Empty pricing means unknown cost, never free usage. Set from dated provider pricing.
    agent_pricing: dict[str, dict[str, float]] = Field(default_factory=dict)
    agent_pricing_date: str | None = None
    live_eval_max_cost_usd: float = Field(default=0, ge=0)
    # Bring-your-own-key: the person running this copy configures it from DevSpace.
    # Set false when hosting a shared copy so visitors cannot change keys or limits.
    devspace_enabled: bool = True
    cookie_secure: bool = False
    credential_signing_secret: str = "nyay-saathi-local-dev-credential-key-change-in-prod"
    allow_legacy_unsigned_cookie: bool = True
    kms_master_key: str = "nyay-saathi-local-dev-kms-master-kek-change-in-prod"
    kms_key_id: str = "local-kek-v1"
    envelope_encryption_enabled: bool = True
    retention_inactivity_days: int = Field(default=365, ge=30, le=3650)
    require_explicit_attachment_consent: bool = False
    pdf_engine: Literal["pymupdf", "pypdf"] = "pymupdf"

    # National-scale pluggable infrastructure endpoints (optional; local adapters active when unset)
    postgresql_dsn: str | None = None
    redis_url: str | None = None
    opensearch_url: str | None = None
    opensearch_index: str = "nyay_legal_propositions_v1"
    object_storage_bucket: str | None = None
    temporal_target: str | None = None
    otlp_endpoint: str | None = None
    dr_region: str = "ap-south-2"
    primary_region: str = "ap-south-1"

    # Abuse & model-cost circuit breakers
    max_model_calls_per_turn: int = Field(default=8, ge=1, le=8)
    device_hourly_model_call_limit: int = Field(default=120, ge=5, le=10000)
    system_hourly_model_call_limit: int = Field(default=5000, ge=10, le=1000000)
    device_hourly_cost_limit_usd: float = Field(default=5.0, gt=0)
    system_hourly_cost_limit_usd: float = Field(default=250.0, gt=0)
    web_research_enabled: bool = True
    web_max_queries: int = Field(default=2, ge=1, le=2)
    web_max_documents: int = Field(default=3, ge=1, le=3)
    web_research_timeout_seconds: float = Field(default=DEFAULT_WEB_RESEARCH_TIMEOUT, ge=5, le=90)
    web_max_download_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    web_max_pdf_pages: int = Field(default=60, ge=1, le=100)
    web_cache_ttl_seconds: float = Field(default=3600, ge=0, le=86400)
    live_eval_max_cases: int = Field(default=0, ge=0, le=20)
    live_eval_max_model_calls: int = Field(default=0, ge=0, le=100)
    max_upload_bytes: int = 10 * 1024 * 1024
    max_pdf_pages: int = 50
    model_timeout_seconds: float = DEFAULT_MODEL_TIMEOUT
    requests_per_minute: int = Field(default=120, ge=10, le=6000)
    device_requests_per_minute: int = Field(default=90, ge=5, le=6000)
    turn_requests_per_minute: int = Field(default=30, ge=2, le=1000)

    @property
    def effective_openai_key(self) -> str | None:
        """The requesting user's own key when their browser unlocked it, else the server's."""
        return current_user_key() or self.openai_api_key

    @property
    def ai_configured(self) -> bool:
        return bool(self.effective_openai_key)

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

"""
config.py — Single source of truth for all ContractGuard settings.
Loads from .env file and validates required variables on startup.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Required ──────────────────────────────────────────────────────────────
    etherscan_api_key: str = Field(..., description="Etherscan API key")
    gemini_api_key: str = Field(..., description="Google Gemini API key")
    web3_provider_url: str = Field(..., description="Sepolia RPC URL (Alchemy/Infura)")

    # ── Optional ──────────────────────────────────────────────────────────────
    goplus_api_key: str = Field(default="", description="GoPlus Security API key")
    cache_ttl_seconds: int = Field(default=3600, description="Etherscan cache TTL in seconds")
    max_investigation_depth: int = Field(default=4, description="Max orchestrator loop depth")
    escalation_threshold_history: int = Field(default=70, description="Score to trigger History Agent")
    escalation_threshold_crossref: int = Field(default=80, description="Score to trigger CrossRef Agent")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    environment: str = Field(default="development")
    gemini_model: str = Field(default="gemini-1.5-flash")

    # ── Derived ───────────────────────────────────────────────────────────────
    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def cors_origins(self) -> list[str]:
        if self.is_development:
            return ["*"]
        return ["https://yourdomain.com"]  # Restrict in production


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns a cached singleton Settings instance."""
    return Settings()


# Module-level convenience alias
settings = get_settings()

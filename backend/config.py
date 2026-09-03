"""Configuration management for ContractGuard.

Reads settings from environment variables and .env file.
"""

import os
from pathlib import Path
from typing import Any

# Try importing pydantic_settings for validation
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    from pydantic import Field

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=(".env", "../.env"),
            env_file_encoding="utf-8",
            extra="ignore",
            case_sensitive=False,
        )

        gemini_api_key: str = Field(default="")
        gemini_model: str = Field(default="gemini-2.0-flash")
        etherscan_api_key: str = Field(default="")
        web3_provider_url: str = Field(default="https://rpc.sepolia.org")
        known_scams_file_path: str = Field(default="data/known_scams.csv")
        escalation_threshold_history: int = Field(default=70)
        escalation_threshold_crossref: int = Field(default=80)
        max_investigation_depth: int = Field(default=4)
        cache_ttl_seconds: int = Field(default=3600)
        environment: str = Field(default="development")
        host: str = Field(default="0.0.0.0")
        port: int = Field(default=8000)

        def __getattr__(self, name: str) -> Any:
            lower_name = name.lower()
            if lower_name in self.__dict__:
                return self.__dict__[lower_name]
            return super().__getattribute__(name)

except ImportError:
    # Standard library fallback when pydantic_settings is not installed in the environment
    class Settings:
        def __init__(self) -> None:
            self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
            self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
            self.etherscan_api_key: str = os.getenv("ETHERSCAN_API_KEY", "")
            self.web3_provider_url: str = os.getenv("WEB3_PROVIDER_URL", "https://rpc.sepolia.org")
            self.known_scams_file_path: str = os.getenv("KNOWN_SCAMS_FILE_PATH", "data/known_scams.csv")
            self.escalation_threshold_history: int = int(os.getenv("ESCALATION_THRESHOLD_HISTORY", "70"))
            self.escalation_threshold_crossref: int = int(os.getenv("ESCALATION_THRESHOLD_CROSSREF", "80"))
            self.max_investigation_depth: int = int(os.getenv("MAX_INVESTIGATION_DEPTH", "4"))
            self.cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
            self.environment: str = os.getenv("ENVIRONMENT", "development")
            self.host: str = os.getenv("HOST", "0.0.0.0")
            self.port: int = int(os.getenv("PORT", "8000"))

        def __getattr__(self, name: str) -> Any:
            lower_name = name.lower()
            if lower_name in self.__dict__:
                return self.__dict__[lower_name]
            raise AttributeError(f"'Settings' object has no attribute '{name}'")

        def __repr__(self) -> str:
            return (
                f"Settings(gemini_model={self.gemini_model!r}, "
                f"environment={self.environment!r}, "
                f"host={self.host!r}, port={self.port})"
            )


settings = Settings()

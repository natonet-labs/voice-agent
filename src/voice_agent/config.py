"""Runtime configuration, loaded from environment / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"

    # Voice providers (Option A now, Option B later)
    elevenlabs_api_key: str = ""
    vapi_api_key: str = ""
    retell_api_key: str = ""

    log_level: str = "INFO"


settings = Settings()

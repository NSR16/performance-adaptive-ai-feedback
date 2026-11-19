from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = ""
    LLM_API_KEY: str | None = None
    JAVA_COMPILER: str = "javac"
    JAVA_RUNTIME: str = "java"
    JAVA_CLASS_NAME: str = "Main"
    JAVA_COMPILATION_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
    JAVA_EXECUTION_TIMEOUT_SECONDS: float = Field(default=2.0, gt=0)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"
    OLLAMA_TIMEOUT: float = Field(default=60.0, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

__all__ = ["Settings", "settings"]

"""
Watheeq AI Service — Application Configuration

Loads settings from environment variables / .env file using pydantic-settings.
All configuration is centralized here for easy management.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- LLM Configuration ---
    # Uses OpenAI-compatible SDK to call Gemini 2.5 Flash
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""  # Optional: for direct Gemini SDK usage
    LLM_MODEL: str = "gemini-2.5-flash"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 4000

    # --- Firebase / Firestore ---
    FIREBASE_ENABLED: bool = True
    FIREBASE_PROJECT_ID: str = "watheeqai-2"
    FIREBASE_CREDENTIALS_PATH: str = "./firebase-credentials.json"

    # --- Service Configuration ---
    SERVICE_HOST: str = "0.0.0.0"
    SERVICE_PORT: int = 8000
    CORS_ORIGINS: str = "*"
    API_VERSION: str = "v1"
    BEARER_TOKEN: str = ""

    # --- Processing ---
    MAX_PDF_SIZE_MB: int = 20
    ANALYSIS_TIMEOUT_SECONDS: int = 60

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings come from environment variables or the .env file."""

    app_name: str = "Prescription Reader"

    # Upload limits
    max_upload_mb: int = 5
    min_image_side_px: int = 500

    # OCR
    ocr_provider: str = "auto"  # auto | vision | gemini
    google_vision_api_key: str | None = None
    low_confidence_threshold: float = 0.80

    # Gemini (used for OCR fallback and optional general information)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    enable_general_info: bool = True

    request_timeout_seconds: int = 40

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

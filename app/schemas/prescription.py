from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.translation_service import SUPPORTED_LANGUAGES


class HealthResponse(BaseModel):
    status: str
    app: str


class ConfigResponse(BaseModel):
    app_name: str
    max_upload_mb: int
    languages: dict[str, str]
    ocr_available: bool
    ocr_provider: str | None
    general_info_enabled: bool


class UploadResponse(BaseModel):
    provider: str
    text: str  # uncertain words are wrapped like [?word?]
    uncertain_words: list[str]
    quality_warnings: list[str]
    notes: list[str]
    image_width: int
    image_height: int


class ExplainRequest(BaseModel):
    text: str = Field(max_length=5000)
    language: str = "en"
    user_confirmed: bool

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Prescription text is empty.")
        return v

    @field_validator("language")
    @classmethod
    def language_supported(cls, v: str) -> str:
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language. Choose one of: {', '.join(SUPPORTED_LANGUAGES)}")
        return v


class ExplainedItem(BaseModel):
    source_text: str  # the line exactly as the user confirmed it
    status: Literal["explained", "needs_confirmation"]
    status_label: str
    form: str | None = None
    name: str | None = None  # exactly as written
    strength: str | None = None  # exactly as written
    schedule: str | None = None  # exactly as written
    timing: str | None = None  # exactly as written
    duration: str | None = None  # exactly as written
    explanation: list[str] = []
    flags: list[str] = []


class ExplainResponse(BaseModel):
    language: str
    labels: dict[str, str]
    transcription: str
    items: list[ExplainedItem]
    other_text: list[str]
    general_info: dict[str, str]
    general_info_note: str | None = None
    warnings: list[str]
    notes: list[str]
    disclaimer: str

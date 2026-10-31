"""Small wrapper around the Gemini REST API (no extra SDK needed).

The API key is sent in a header, never in the URL, and we never log request
or response bodies because they may contain medical information.
"""

import logging

import httpx

from app.core.config import settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiError(AppError):
    status_code = 502
    code = "gemini_error"


def generate_text(parts: list[dict], *, system: str | None = None, json_mode: bool = False) -> str:
    if not settings.gemini_api_key:
        raise GeminiError(
            "The Gemini API key is not configured.", code="gemini_not_configured", status_code=503
        )

    body: dict = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"

    try:
        response = httpx.post(
            URL.format(model=settings.gemini_model),
            headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
            json=body,
            timeout=settings.request_timeout_seconds,
        )
    except httpx.HTTPError:
        raise GeminiError("Could not reach the Gemini service. Check your internet connection and try again.")

    if response.status_code != 200:
        logger.warning("Gemini returned HTTP %s", response.status_code)
        raise GeminiError(f"The Gemini service returned an error (HTTP {response.status_code}).")

    try:
        out_parts = response.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in out_parts)
    except (ValueError, KeyError, IndexError, TypeError):
        raise GeminiError("The Gemini service returned an unexpected answer (it may have blocked the request).")

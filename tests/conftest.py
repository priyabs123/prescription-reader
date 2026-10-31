"""Shared test setup. No test ever calls a real online service or needs a real API key."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def no_real_keys(monkeypatch):
    """Every test starts with NO keys, even if a real .env file exists on this computer."""
    monkeypatch.setattr(settings, "google_vision_api_key", None)
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "ocr_provider", "auto")
    monkeypatch.setattr(settings, "enable_general_info", True)
    monkeypatch.setattr(settings, "max_upload_mb", 5)


@pytest.fixture
def client():
    # raise_server_exceptions=False lets us test the friendly 500 error page
    return TestClient(app, raise_server_exceptions=False)


class FakeResponse:
    """A stand-in for an httpx response."""

    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def vision_payload(lines):
    """Build a Google Vision style answer. lines = [[(word, confidence), ...], ...]"""
    words = []
    for line in lines:
        for i, (text, confidence) in enumerate(line):
            symbols = [{"text": ch} for ch in text]
            symbols[-1]["property"] = {
                "detectedBreak": {"type": "LINE_BREAK" if i == len(line) - 1 else "SPACE"}
            }
            words.append({"symbols": symbols, "confidence": confidence})
    return {"responses": [{"fullTextAnnotation": {"pages": [{"blocks": [{"paragraphs": [{"words": words}]}]}]}}]}

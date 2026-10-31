import httpx
import pytest

from app.core.config import settings
from app.services import gemini_client, ocr_service
from tests.conftest import FakeResponse, vision_payload

# ---------- Vision response parsing ----------


def test_low_confidence_words_are_marked():
    data = vision_payload([
        [("Tab", 0.99), ("Pantop", 0.41), ("40mg", 0.95), ("OD", 0.97)],
        [("Tab", 0.98), ("Paracetamol", 0.93), ("500mg", 0.90)],
    ])
    result = ocr_service.parse_vision_response(data, 0.80)
    assert result.text == "Tab [?Pantop?] 40mg OD\nTab Paracetamol 500mg"
    assert result.uncertain_words == ["Pantop"]
    assert result.provider == "vision"
    assert result.notes  # tells the user to compare everything


def test_threshold_boundary_is_not_uncertain():
    data = vision_payload([[("Tab", 0.80), ("X", 0.7999)]])
    assert ocr_service.parse_vision_response(data, 0.80).text == "Tab [?X?]"


def test_words_without_confidence_are_not_marked():
    payload = vision_payload([[("Tab", 0.9), ("X", 0.9)]])
    for w in payload["responses"][0]["fullTextAnnotation"]["pages"][0]["blocks"][0]["paragraphs"][0]["words"]:
        del w["confidence"]
    assert ocr_service.parse_vision_response(payload, 0.8).text == "Tab X"


def test_no_text_found_gives_empty_result():
    result = ocr_service.parse_vision_response({"responses": [{}]}, 0.8)
    assert result.text == "" and result.uncertain_words == []


def test_vision_error_inside_answer():
    with pytest.raises(ocr_service.OcrError):
        ocr_service.parse_vision_response({"responses": [{"error": {"code": 3, "message": "bad"}}]}, 0.8)


@pytest.mark.parametrize("bad", [{}, {"responses": []}, [], None, {"responses": [None]}])
def test_malformed_vision_answer(bad):
    with pytest.raises((ocr_service.OcrError, AttributeError)):
        ocr_service.parse_vision_response(bad, 0.8)


# ---------- text marked by a language model ----------


def test_marked_text_parsing():
    result = ocr_service.parse_marked_text("Tab [?Pantop?] 40mg OD\n\nCap Omeprazole 20mg\n")
    assert result.text == "Tab [?Pantop?] 40mg OD\nCap Omeprazole 20mg"
    assert result.uncertain_words == ["Pantop"]
    assert "no confidence scores" in result.notes[0]


def test_marked_text_with_spaces_inside_marker_and_code_fences():
    result = ocr_service.parse_marked_text("```\nTab [?Folic acid?] 5mg\n```")
    assert result.text == "Tab [?Folic acid?] 5mg"
    assert result.uncertain_words == ["Folic acid"]


# ---------- choosing a provider ----------


@pytest.mark.parametrize(
    "vision, gemini, choice, expected",
    [
        (None, None, "auto", None),
        ("k", None, "auto", "vision"),
        (None, "g", "auto", "gemini"),
        ("k", "g", "auto", "vision"),
        ("k", "g", "gemini", "gemini"),
        ("k", "g", "vision", "vision"),
        (None, "g", "vision", None),
        ("k", None, "gemini", None),
    ],
)
def test_resolve_provider(monkeypatch, vision, gemini, choice, expected):
    monkeypatch.setattr(settings, "google_vision_api_key", vision)
    monkeypatch.setattr(settings, "gemini_api_key", gemini)
    monkeypatch.setattr(settings, "ocr_provider", choice)
    assert ocr_service.resolve_provider() == expected


def test_run_ocr_without_any_key_says_how_to_fix_it():
    with pytest.raises(ocr_service.OcrError) as info:
        ocr_service.run_ocr(b"jpeg")
    assert info.value.status_code == 503 and info.value.code == "ocr_not_configured"
    assert "GOOGLE_VISION_API_KEY" in info.value.message


# ---------- calling Vision (network is faked) ----------


def test_vision_call_sends_key_in_header_not_url(monkeypatch):
    monkeypatch.setattr(settings, "google_vision_api_key", "SECRET-KEY")
    seen = {}

    def fake_post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse(200, vision_payload([[("Tab", 0.9), ("Metformin", 0.9)]]))

    monkeypatch.setattr(ocr_service.httpx, "post", fake_post)
    result = ocr_service.run_ocr(b"jpegbytes")
    assert result.text == "Tab Metformin"
    assert "SECRET-KEY" not in seen["url"]
    assert seen["headers"]["X-Goog-Api-Key"] == "SECRET-KEY"
    feature = seen["json"]["requests"][0]["features"][0]["type"]
    assert feature == "DOCUMENT_TEXT_DETECTION"


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500])
def test_vision_http_errors_become_friendly_errors(monkeypatch, status):
    monkeypatch.setattr(settings, "google_vision_api_key", "k")
    monkeypatch.setattr(ocr_service.httpx, "post", lambda *a, **k: FakeResponse(status, {"error": "x"}))
    with pytest.raises(ocr_service.OcrError) as info:
        ocr_service.run_ocr(b"x")
    assert str(status) in info.value.message and "API key" in info.value.message


def test_vision_network_failure(monkeypatch):
    monkeypatch.setattr(settings, "google_vision_api_key", "k")

    def boom(*a, **k):
        raise httpx.ConnectError("no internet")

    monkeypatch.setattr(ocr_service.httpx, "post", boom)
    with pytest.raises(ocr_service.OcrError) as info:
        ocr_service.run_ocr(b"x")
    assert "internet" in info.value.message


def test_vision_non_json_answer(monkeypatch):
    monkeypatch.setattr(settings, "google_vision_api_key", "k")
    monkeypatch.setattr(ocr_service.httpx, "post", lambda *a, **k: FakeResponse(200, None))
    with pytest.raises(ocr_service.OcrError):
        ocr_service.run_ocr(b"x")


# ---------- Gemini path (faked) ----------


def test_gemini_ocr_path(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "g")
    seen = {}

    def fake_generate(parts, **kwargs):
        seen["parts"] = parts
        return "Tab [?Pantop?] 40mg OD"

    monkeypatch.setattr(gemini_client, "generate_text", fake_generate)
    result = ocr_service.run_ocr(b"jpegbytes")
    assert result.provider == "gemini" and result.uncertain_words == ["Pantop"]
    assert "Never replace an unclear medicine name" in seen["parts"][0]["text"]
    assert seen["parts"][1]["inlineData"]["mimeType"] == "image/jpeg"


# ---------- the Gemini HTTP wrapper ----------


def test_gemini_client_key_in_header_and_parses_answer(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "SECRET")
    seen = {}

    def fake_post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": "hel"}, {"text": "lo"}]}}]})

    monkeypatch.setattr(gemini_client.httpx, "post", fake_post)
    assert gemini_client.generate_text([{"text": "hi"}], system="s", json_mode=True) == "hello"
    assert "SECRET" not in seen["url"] and seen["headers"]["x-goog-api-key"] == "SECRET"
    assert seen["json"]["generationConfig"]["responseMimeType"] == "application/json"
    assert seen["json"]["generationConfig"]["temperature"] == 0


def test_gemini_client_errors(monkeypatch):
    with pytest.raises(gemini_client.GeminiError) as info:  # no key
        gemini_client.generate_text([{"text": "hi"}])
    assert info.value.status_code == 503

    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(gemini_client.httpx, "post", lambda *a, **k: FakeResponse(429, {}))
    with pytest.raises(gemini_client.GeminiError) as info:
        gemini_client.generate_text([{"text": "hi"}])
    assert "429" in info.value.message

    monkeypatch.setattr(gemini_client.httpx, "post", lambda *a, **k: FakeResponse(200, {"candidates": []}))
    with pytest.raises(gemini_client.GeminiError):  # blocked / empty answer
        gemini_client.generate_text([{"text": "hi"}])

    def boom(*a, **k):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(gemini_client.httpx, "post", boom)
    with pytest.raises(gemini_client.GeminiError):
        gemini_client.generate_text([{"text": "hi"}])

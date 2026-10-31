"""End-to-end tests of the web API (the network calls to Google are faked)."""

import logging
import os
import tempfile
from pathlib import Path

import pytest

from app.core.config import settings
from app.services import explanation_service, ocr_service
from tests.conftest import FakeResponse, vision_payload
from tests.helpers import blurred, make_prescription, to_bytes

GOOD = to_bytes(make_prescription())


def upload(client, data=GOOD, name="rx.jpg", ctype="image/jpeg", **form):
    return client.post("/api/upload", files={"file": (name, data, ctype)}, data=form)


def use_vision(monkeypatch, lines):
    monkeypatch.setattr(settings, "google_vision_api_key", "test-key")
    monkeypatch.setattr(ocr_service.httpx, "post", lambda *a, **k: FakeResponse(200, vision_payload(lines)))


def explain(client, text, lang="en", confirmed=True):
    return client.post("/api/explain", json={"text": text, "language": lang, "user_confirmed": confirmed})


# ---------- basic pages ----------

def test_home_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Prescription Reader" in r.text and "does not replace your doctor" in r.text
    # on opening, only the upload card is visible; the check-text and results cards start hidden
    assert 'id="review-card"' in r.text and 'id="results"' in r.text
    assert r.text.count("hidden>") >= 2


def test_static_files(client):
    assert client.get("/static/css/style.css").status_code == 200
    assert client.get("/static/js/app.js").status_code == 200


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok", "app": "Prescription Reader"}


def test_config_without_keys(client):
    cfg = client.get("/api/config").json()
    assert cfg["ocr_available"] is False and cfg["ocr_provider"] is None
    assert cfg["general_info_enabled"] is False
    assert set(cfg["languages"]) == {"en", "kn"} and cfg["max_upload_mb"] == 5


def test_config_with_keys(client, monkeypatch):
    monkeypatch.setattr(settings, "google_vision_api_key", "k")
    monkeypatch.setattr(settings, "gemini_api_key", "g")
    cfg = client.get("/api/config").json()
    assert cfg["ocr_provider"] == "vision" and cfg["general_info_enabled"] is True


def test_unknown_api_path_is_404(client):
    assert client.get("/api/nothing").status_code == 404


# ---------- upload ----------

def test_upload_marks_unsure_words(client, monkeypatch):
    use_vision(monkeypatch, [[("Tab", 0.99), ("Pantop", 0.4), ("40mg", 0.95), ("OD", 0.97)],
                             [("Tab", 0.99), ("Metformin", 0.96), ("500mg", 0.95), ("BD", 0.9)]])
    r = upload(client)
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "Tab [?Pantop?] 40mg OD\nTab Metformin 500mg BD"
    assert body["uncertain_words"] == ["Pantop"]
    assert body["provider"] == "vision" and body["quality_warnings"] == []
    assert (body["image_width"], body["image_height"]) == (1000, 1300)


def test_upload_returns_quality_warnings(client, monkeypatch):
    use_vision(monkeypatch, [[("Tab", 0.99)]])
    r = upload(client, to_bytes(blurred(make_prescription(), 2)))
    assert r.status_code == 200 and any("blurry" in w for w in r.json()["quality_warnings"])


def test_upload_without_ocr_service_explains_what_to_do(client):
    r = upload(client)
    assert r.status_code == 503
    err = r.json()["error"]
    assert err["code"] == "ocr_not_configured" and "type" in err["message"].lower()


def test_upload_no_text_found(client, monkeypatch):
    monkeypatch.setattr(settings, "google_vision_api_key", "k")
    monkeypatch.setattr(ocr_service.httpx, "post", lambda *a, **k: FakeResponse(200, {"responses": [{}]}))
    r = upload(client)
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_text_found"


def test_upload_ocr_service_failure(client, monkeypatch):
    monkeypatch.setattr(settings, "google_vision_api_key", "k")
    monkeypatch.setattr(ocr_service.httpx, "post", lambda *a, **k: FakeResponse(403, {}))
    r = upload(client)
    assert r.status_code == 502 and "403" in r.json()["error"]["message"]


@pytest.mark.parametrize(
    "kwargs, status, code",
    [
        (dict(data=b"", name="rx.jpg"), 422, "empty_file"),
        (dict(data=GOOD, name="rx.gif", ctype="image/gif"), 415, "bad_file_type"),
        (dict(data=b"not an image at all", name="rx.jpg"), 422, "unreadable_image"),
        (dict(data=to_bytes(blurred(make_prescription(), 8)), name="rx.jpg"), 422, "too_blurry"),
        (dict(data=to_bytes(make_prescription().resize((300, 390))), name="rx.jpg"), 422, "image_too_small"),
    ],
)
def test_upload_rejects_bad_files_before_ocr(client, monkeypatch, kwargs, status, code):
    called = []
    monkeypatch.setattr(ocr_service, "run_ocr", lambda *a, **k: called.append(1))
    r = upload(client, **kwargs)
    assert r.status_code == status and r.json()["error"]["code"] == code
    assert called == [], "a rejected file must never be sent to the OCR service"


def test_upload_too_large(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    import random

    noise = random.Random(1).randbytes(1200 * 1200 * 3)  # random bytes do not compress
    from PIL import Image

    data = to_bytes(Image.frombytes("RGB", (1200, 1200), noise), "PNG")
    assert len(data) > 1024 * 1024
    r = upload(client, data, "big.png", "image/png")
    assert r.status_code == 413 and "1 MB" in r.json()["error"]["message"]


def test_upload_missing_file_field(client):
    r = client.post("/api/upload")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_upload_rotation(client, monkeypatch):
    use_vision(monkeypatch, [[("Tab", 0.99)]])
    r = upload(client, to_bytes(make_prescription(1000, 800, 60, 28)), rotate="90")
    assert r.status_code == 200 and (r.json()["image_width"], r.json()["image_height"]) == (800, 1000)
    assert upload(client, rotate="45").status_code == 422
    assert upload(client, rotate="abc").status_code == 422


def test_upload_png(client, monkeypatch):
    use_vision(monkeypatch, [[("Tab", 0.99)]])
    assert upload(client, to_bytes(make_prescription(), "PNG"), "rx.png", "image/png").status_code == 200


# ---------- explain ----------

def test_explain_english(client):
    r = explain(client, "Tab Paracetamol 500mg 1-0-1 after food x 5 days")
    assert r.status_code == 200
    body = r.json()
    assert body["items"][0]["status"] == "explained"
    assert body["transcription"] == "Tab Paracetamol 500mg 1-0-1 after food x 5 days"
    assert body["language"] == "en" and body["labels"]["lbl_medicines"]
    assert body["general_info"] == {}


def test_explain_kannada(client):
    body = explain(client, "Tab Paracetamol 500mg 1-0-1 after food", "kn").json()
    assert body["language"] == "kn"
    assert any("ಊಟದ ನಂತರ" in line for line in body["items"][0]["explanation"])
    assert "ಪರ್ಯಾಯವಲ್ಲ" in body["disclaimer"]


def test_explain_requires_the_user_to_confirm(client):
    r = explain(client, "Tab Paracetamol 500mg 1-0-1", confirmed=False)
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_confirmed"


def test_explain_unsupported_language(client):
    r = explain(client, "Tab Paracetamol 500mg 1-0-1", lang="fr")
    assert r.status_code == 422 and "Unsupported language" in r.json()["error"]["message"]


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_explain_empty_text(client, text):
    r = explain(client, text)
    assert r.status_code == 422 and "empty" in r.json()["error"]["message"].lower()


def test_explain_text_too_long(client):
    assert explain(client, "a" * 5001).status_code == 422


def test_explain_bad_json_shape(client):
    assert client.post("/api/explain", json={"text": 5}).status_code == 422
    assert client.post("/api/explain", content=b"not json", headers={"content-type": "application/json"}).status_code == 422


def test_explain_uncertain_line_is_not_explained_and_warns(client):
    body = explain(client, "Tab [?Pantop?] 40mg OD\nTab Metformin 500mg BD").json()
    statuses = [i["status"] for i in body["items"]]
    assert statuses == ["needs_confirmation", "explained"]
    assert body["items"][0]["explanation"] == []
    assert "pharmacist" in body["warnings"][0]


def test_explain_html_in_text_is_returned_as_plain_text(client):
    """The server returns data; the page shows it with textContent, so scripts never run."""
    body = explain(client, "<script>alert(1)</script> Tab X 5mg OD").json()
    assert "<script>" in body["transcription"]  # unchanged data, not executed anywhere


# ---------- privacy and error handling ----------

def test_api_responses_are_not_cached_and_have_security_headers(client):
    for r in (client.get("/api/health"), explain(client, "Tab X 5mg OD"), upload(client)):
        assert r.headers["cache-control"] == "no-store"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "no-referrer"
    assert "no-store" not in client.get("/").headers.get("cache-control", "")


def test_unexpected_errors_do_not_leak_medical_text(client, monkeypatch):
    def boom(text, lang):
        raise RuntimeError("secret Paracetamol 500mg detail")

    monkeypatch.setattr(explanation_service, "explain_text", boom)
    r = explain(client, "Tab Paracetamol 500mg 1-0-1")
    assert r.status_code == 500
    assert "Paracetamol" not in r.text and r.json()["error"]["code"] == "server_error"


def test_nothing_is_logged_about_prescription_content(client, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    use_vision(monkeypatch, [[("Tab", 0.99), ("Zorblax", 0.4), ("500mg", 0.9)]])
    upload(client)
    explain(client, "Tab Zorblax 500mg 1-0-1 after food")
    monkeypatch.setattr(explanation_service, "explain_text", lambda *a: (_ for _ in ()).throw(RuntimeError("Zorblax")))
    explain(client, "Tab Zorblax 500mg 1-0-1")
    assert "Zorblax" not in caplog.text and "test-key" not in caplog.text


def test_upload_writes_no_files(client, monkeypatch):
    """The image is processed in memory only."""
    use_vision(monkeypatch, [[("Tab", 0.99)]])
    roots = [Path(__file__).resolve().parent.parent, Path(tempfile.gettempdir())]

    def snapshot():
        found = set()
        for root in roots:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in {".git", "venv", ".venv", "__pycache__", ".pytest_cache"}]
                found.update(os.path.join(dirpath, f) for f in filenames)
        return found

    before = snapshot()
    assert upload(client).status_code == 200
    assert snapshot() - before == set()

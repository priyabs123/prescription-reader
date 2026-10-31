"""Turn an image into text, and mark the words we are not sure about.

Two providers:
  * vision - Google Cloud Vision (DOCUMENT_TEXT_DETECTION). Gives a confidence
             score for every word, so we can mark low-confidence words.
  * gemini - a vision language model. It gives NO confidence scores, so we ask
             it to mark unsure words itself. Treat all its output as unverified.

Uncertain words are wrapped like [?word?]. The user must review them.
Nothing here replaces or "fixes" a word with a similar-looking medicine.
"""

import base64
import logging
import re
from dataclasses import dataclass, field

import httpx

from app.core.config import settings
from app.core.errors import AppError
from app.services import gemini_client

logger = logging.getLogger(__name__)

VISION_URL = "https://vision.googleapis.com/v1/images:annotate"
MARKER_TOKEN_RE = re.compile(r"\[\?.*?\?\]|\S+")

GEMINI_OCR_PROMPT = (
    "You are transcribing a photographed medical prescription. Copy the text exactly as written, "
    "line by line, keeping the line breaks. Do NOT correct, complete or guess anything. "
    "If any word, medicine name, number or abbreviation is hard to read or you are not sure, "
    "wrap exactly that part in [? and ?], for example [?Pantop?]. If something is completely "
    "unreadable write [?unreadable?]. Never replace an unclear medicine name with a similar-looking "
    "medicine. Output only the transcription as plain text, with no comments."
)


class OcrError(AppError):
    status_code = 502
    code = "ocr_error"


@dataclass
class OcrWord:
    text: str
    confidence: float | None = None
    uncertain: bool = False


@dataclass
class OcrResult:
    provider: str
    lines: list[list[OcrWord]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Plain text where every uncertain word is written as [?word?]."""
        out_lines = []
        for line in self.lines:
            words = [f"[?{w.text}?]" if w.uncertain and not _is_marked(w.text) else w.text for w in line]
            out_lines.append(" ".join(words))
        return "\n".join(out_lines).strip()

    @property
    def uncertain_words(self) -> list[str]:
        return [_unwrap(w.text) for line in self.lines for w in line if w.uncertain]


def _is_marked(token: str) -> bool:
    return token.startswith("[?") and token.endswith("?]")


def _unwrap(token: str) -> str:
    return token[2:-2] if _is_marked(token) else token


# ---------- provider selection ----------

def resolve_provider() -> str | None:
    """Return "vision", "gemini", or None if nothing is configured."""
    choice = (settings.ocr_provider or "auto").lower()
    if choice == "vision":
        return "vision" if settings.google_vision_api_key else None
    if choice == "gemini":
        return "gemini" if settings.gemini_api_key else None
    if settings.google_vision_api_key:
        return "vision"
    if settings.gemini_api_key:
        return "gemini"
    return None


def run_ocr(jpeg_bytes: bytes) -> OcrResult:
    provider = resolve_provider()
    if provider is None:
        raise OcrError(
            "No OCR service is set up. Add GOOGLE_VISION_API_KEY or GEMINI_API_KEY to the .env file, "
            "or type the prescription text into the box below.",
            code="ocr_not_configured",
            status_code=503,
        )
    if provider == "vision":
        return _run_vision(jpeg_bytes)
    return _run_gemini(jpeg_bytes)


# ---------- Google Cloud Vision ----------

def _run_vision(jpeg_bytes: bytes) -> OcrResult:
    payload = {
        "requests": [
            {
                "image": {"content": base64.b64encode(jpeg_bytes).decode("ascii")},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            }
        ]
    }
    try:
        response = httpx.post(
            VISION_URL,
            headers={"X-Goog-Api-Key": settings.google_vision_api_key or "", "Content-Type": "application/json"},
            json=payload,
            timeout=settings.request_timeout_seconds,
        )
    except httpx.HTTPError:
        raise OcrError("Could not reach the OCR service. Check your internet connection and try again.")

    if response.status_code != 200:
        logger.warning("Vision API returned HTTP %s", response.status_code)
        raise OcrError(
            f"The OCR service returned an error (HTTP {response.status_code}). "
            "Check that your API key is correct and the Vision API is enabled."
        )
    try:
        data = response.json()
    except ValueError:
        raise OcrError("The OCR service returned an unexpected answer.")
    return parse_vision_response(data, settings.low_confidence_threshold)


def parse_vision_response(data: dict, threshold: float) -> OcrResult:
    """Convert the Vision JSON into lines of words with an 'uncertain' flag."""
    result = OcrResult(provider="vision")
    try:
        first = data["responses"][0]
    except (KeyError, IndexError, TypeError):
        raise OcrError("The OCR service returned an unexpected answer.")

    if first.get("error"):
        raise OcrError("The OCR service could not process this image. Please try another photo.")

    annotation = first.get("fullTextAnnotation")
    if not annotation:
        return result  # no text found

    current: list[OcrWord] = []
    for page in annotation.get("pages", []):
        for block in page.get("blocks", []):
            for paragraph in block.get("paragraphs", []):
                for word in paragraph.get("words", []):
                    symbols = word.get("symbols", [])
                    text = "".join(s.get("text", "") for s in symbols)
                    if not text:
                        continue
                    confidence = word.get("confidence")
                    uncertain = confidence is not None and confidence < threshold
                    current.append(OcrWord(text=text, confidence=confidence, uncertain=uncertain))

                    last_break = (symbols[-1].get("property", {}).get("detectedBreak", {}) or {}).get("type")
                    if last_break in ("LINE_BREAK", "EOL_SURE_SPACE"):
                        result.lines.append(current)
                        current = []
                if current:  # end of paragraph always ends a line
                    result.lines.append(current)
                    current = []
    if current:
        result.lines.append(current)

    result.notes.append(
        "Words marked [?like this?] had low OCR confidence. Handwriting recognition is often wrong, "
        "so compare ALL the text with your prescription, not only the marked words."
    )
    return result


# ---------- Gemini ----------

def _run_gemini(jpeg_bytes: bytes) -> OcrResult:
    parts = [
        {"text": GEMINI_OCR_PROMPT},
        {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(jpeg_bytes).decode("ascii")}},
    ]
    raw = gemini_client.generate_text(parts)
    return parse_marked_text(raw, provider="gemini")


def parse_marked_text(raw: str, provider: str = "gemini") -> OcrResult:
    """Parse text where unsure parts are already written as [?...?]."""
    text = raw.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text).strip()  # remove code fences if present

    result = OcrResult(provider=provider)
    for line in text.splitlines():
        if not line.strip():
            continue
        words = []
        for token in MARKER_TOKEN_RE.findall(line):
            if _is_marked(token):
                words.append(OcrWord(text=token, uncertain=True))
            else:
                words.append(OcrWord(text=token))
        result.lines.append(words)

    if provider == "gemini":
        result.notes.append(
            "This reading came from an AI model that gives no confidence scores. It may have made "
            "mistakes even in words that are not marked. Compare ALL the text with your prescription."
        )
    return result

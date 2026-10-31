"""Explain the text the user has confirmed.

Design rule: the SAFETY-CRITICAL part is plain code, not AI.

  1. A parser (regular expressions) finds the form, name, strength, schedule,
     timing and duration in each line, exactly as written.
  2. A fixed lookup table (translation_service.py) explains each abbreviation,
     in English or Kannada. It cannot invent a medicine or a dose.
  3. Anything missing, unclear or marked [?...?] is flagged, never filled in.
  4. Optionally an AI model writes ONE-sentence general information per
     confirmed medicine name. That output is validated (no numbers, no advice
     words, no extra medicine names) and shown in a separate, clearly labelled
     section. If validation fails, it is thrown away.
"""

import json
import logging
import re
from dataclasses import dataclass
from fractions import Fraction

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.prescription import ExplainedItem, ExplainResponse
from app.services import gemini_client
from app.services.translation_service import LLM_LANGUAGE_NAMES, label_set, t

logger = logging.getLogger(__name__)

MARKER_RE = re.compile(r"\[\?.*?\?\]")
MAX_LINES = 60

NUMBERING_RE = re.compile(r"^\s*\d{1,2}\s*[.)](?=\s|[A-Za-z])\s*")  # list numbers such as "3." or "4)"

FORM_RE = re.compile(
    r"^\s*(?:\d{1,2}\s*[.)](?=\s|[A-Za-z])\s*)?"
    r"(?:(?:eye|ear|nasal|nose)\s+)?"
    r"(tabs?|tablets?|caps?|capsules?|syp|syr|syrup|inj|injection|drops?|oint|ointment|cream|gel|susp|suspension)"
    r"\b\.?\s*",
    re.I,
)
FORM_MAP = {
    "tab": "tablet", "tabs": "tablet", "tablet": "tablet", "tablets": "tablet",
    "cap": "capsule", "caps": "capsule", "capsule": "capsule", "capsules": "capsule",
    "syp": "syrup", "syr": "syrup", "syrup": "syrup",
    "inj": "injection", "injection": "injection",
    "drop": "drops", "drops": "drops",
    "oint": "ointment", "ointment": "ointment",
    "cream": "cream", "gel": "gel",
    "susp": "suspension", "suspension": "suspension",
}

_UNIT = r"(?:mg|mcg|µg|ug|g|ml|iu|%)"
STRENGTH_RE = re.compile(
    rf"(?<![\w.])(\d+(?:\.\d+)?\s*{_UNIT}(?:\s*/\s*(?:\d+(?:\.\d+)?\s*)?{_UNIT})?)(?![a-z])", re.I
)
_QTY = r"(\d+\s*/\s*\d+|\d*½|\d)"  # 1, 1/2, ½, 1½
PATTERN_RE = re.compile(
    rf"(?<![\d\-/]){_QTY}\s*[-–—]\s*{_QTY}\s*[-–—]\s*{_QTY}(?:\s*[-–—]\s*{_QTY})?(?![\d\-/½])"
)
ABBR_RE = re.compile(
    r"\b(?:OD|QD|BD|BID|TDS|TID|QID|QDS|HS|SOS|PRN|STAT|weekly"
    r"|once\s+(?:a\s+)?week"
    r"|once\s+(?:a\s+)?(?:daily|day)"
    r"|twice\s+(?:a\s+)?(?:daily|day)"
    r"|(?:thrice|three\s+times)\s+(?:a\s+)?(?:daily|day)"
    r"|four\s+times\s+(?:a\s+)?(?:daily|day)"
    r"|at\s+bed\s?time|bed\s?time)\b",
    re.I,
)
TIMING_RE = re.compile(
    r"\b(?:(?:before|after)\s+(?:food|meals?|breakfast|lunch|dinner|eating)"
    r"|empty\s+stomach|with\s+(?:food|meals?)|AC|PC)\b",
    re.I,
)
DURATION_RE = re.compile(r"(?:(?:\bx|×|\bfor)\s*)?(\d{1,3})\s*(days?|weeks?|wks?|months?)\b", re.I)
DURATION_X_RE = re.compile(r"\bx\s*(\d{1,3})\s*d\b", re.I)

ABBR_COUNT = {"od": 1, "bd": 2, "tds": 3, "qid": 4}


@dataclass
class ParsedMedicine:
    source: str
    form: str | None = None
    name: str | None = None
    strength: str | None = None
    pattern: tuple[Fraction, ...] | None = None
    pattern_raw: str | None = None
    abbr_raw: str | None = None
    abbr_key: str | None = None
    timing_raw: str | None = None
    timing_key: str | None = None
    duration_raw: str | None = None
    duration_n: int | None = None
    duration_unit: str | None = None


def _abbr_key(raw: str) -> str | None:
    r = re.sub(r"\s+", " ", raw.lower()).strip()
    if r == "weekly" or r.endswith("week"):
        return "weekly"
    if r in ("od", "qd") or r.startswith("once"):
        return "od"
    if r in ("bd", "bid") or r.startswith("twice"):
        return "bd"
    if r in ("tds", "tid") or r.startswith(("thrice", "three")):
        return "tds"
    if r in ("qid", "qds") or r.startswith("four"):
        return "qid"
    if r == "hs" or "bed" in r:
        return "hs"
    if r in ("sos", "prn"):
        return "sos"
    if r == "stat":
        return "stat"
    return None


def _timing_key(raw: str) -> str:
    r = raw.lower()
    if r.startswith("before") or r == "ac":
        return "ac"
    if r.startswith("after") or r == "pc":
        return "pc"
    if r.startswith("empty"):
        return "empty"
    return "with_food"


def _to_fraction(token: str) -> Fraction:
    """Turn "1", "1/2", "½" or "1½" into an exact number."""
    token = token.replace(" ", "")
    if "½" in token:
        whole = token.replace("½", "")
        return Fraction(int(whole) if whole else 0) + Fraction(1, 2)
    if "/" in token:
        top, bottom = token.split("/")
        return Fraction(int(top), int(bottom)) if int(bottom) else Fraction(0)
    return Fraction(int(token))


def _quantity_text(n: Fraction, lang: str) -> str:
    """How a number of tablets is shown. Whole numbers stay as they are."""
    if n.denominator == 1:
        return str(n.numerator)
    if n == Fraction(1, 2):
        return t(lang, "qty_half")
    whole, rest = divmod(n.numerator, n.denominator)
    fraction = f"{rest}/{n.denominator}"
    return f"{whole} {fraction}" if whole else fraction


def _find_duration(text: str):
    m = DURATION_RE.search(text)
    if m:
        unit = m.group(2).lower()
        unit = "days" if unit.startswith("day") else "weeks" if unit.startswith(("week", "wk")) else "months"
        return m, int(m.group(1)), unit
    m = DURATION_X_RE.search(text)
    if m:
        return m, int(m.group(1)), "days"
    return None, None, None


def _detect(text: str) -> dict:
    """Find every part in a piece of text. Returns the regex matches."""
    dur_m, dur_n, dur_unit = _find_duration(text)
    return {
        "strength": STRENGTH_RE.search(text),
        "pattern": PATTERN_RE.search(text),
        "abbr": ABBR_RE.search(text),
        "timing": TIMING_RE.search(text),
        "duration": dur_m,
        "duration_n": dur_n,
        "duration_unit": dur_unit,
    }


def parse_medicine(source: str) -> ParsedMedicine:
    """Parse one confirmed line (a line with no [?...?] markers)."""
    parsed = ParsedMedicine(source=source)
    rest = NUMBERING_RE.sub("", source, count=1)  # "3. Tab X" -> "Tab X"
    fm = FORM_RE.match(rest)
    if fm:
        parsed.form = FORM_MAP[fm.group(1).lower()]
        rest = rest[fm.end():]

    found = _detect(rest)
    starts = []
    if found["strength"]:
        parsed.strength = re.sub(r"\s+", " ", found["strength"].group(1)).strip()
        starts.append(found["strength"].start())
    if found["pattern"]:
        parsed.pattern_raw = found["pattern"].group(0)
        parsed.pattern = tuple(_to_fraction(g) for g in found["pattern"].groups() if g is not None)
        starts.append(found["pattern"].start())
    if found["abbr"]:
        parsed.abbr_raw = found["abbr"].group(0)
        parsed.abbr_key = _abbr_key(parsed.abbr_raw)
        starts.append(found["abbr"].start())
    if found["timing"]:
        parsed.timing_raw = found["timing"].group(0)
        parsed.timing_key = _timing_key(parsed.timing_raw)
        starts.append(found["timing"].start())
    if found["duration"]:
        parsed.duration_raw = found["duration"].group(0).strip()
        parsed.duration_n = found["duration_n"]
        parsed.duration_unit = found["duration_unit"]
        starts.append(found["duration"].start())

    end = min(starts) if starts else len(rest)
    name = rest[:end].strip(" ,.-:;")
    parsed.name = name or None
    return parsed


def looks_like_medicine_line(masked: str, has_marker: bool) -> bool:
    """Decide if a line is a medicine line (True) or other text such as a date or doctor name."""
    form = bool(FORM_RE.match(masked))
    f = _detect(masked)
    any_part = any(f[k] for k in ("strength", "pattern", "abbr", "timing"))
    if has_marker:
        return form or any_part
    return form or (bool(f["strength"]) and bool(f["pattern"] or f["abbr"] or f["timing"]))


def _unit_words(form: str | None, lang: str, n: Fraction) -> str:
    base = "tablet" if form == "tablet" else "capsule" if form == "capsule" else "dose"
    return t(lang, f"unit_{base}" if n <= 1 else f"unit_{base}s")


def _duration_text(n: int, unit: str, lang: str) -> str:
    key = unit[:-1] if n == 1 else unit  # days -> day when the number is 1
    return t(lang, f"duration_{key}", n=n)


def _explain_pattern(parsed: ParsedMedicine, lang: str) -> str | None:
    slots = ["morning", "afternoon", "night"] if len(parsed.pattern) == 3 else [
        "morning", "afternoon", "evening", "night"
    ]
    pieces = [
        t(lang, f"slot_{slot}", n=_quantity_text(n, lang), unit=_unit_words(parsed.form, lang, n))
        for slot, n in zip(slots, parsed.pattern)
        if n > 0
    ]
    return ", ".join(pieces) if pieces else None


def build_item(line: str, lang: str) -> ExplainedItem:
    """Explain one medicine line. Never fills in anything that was not written."""
    source = line.strip()

    # A line that still contains [?...?] is NOT explained at all.
    if MARKER_RE.search(source):
        return ExplainedItem(
            source_text=source,
            status="needs_confirmation",
            status_label=t(lang, "status_needs_confirmation"),
            flags=[t(lang, "flag_marker")],
        )

    p = parse_medicine(source)
    flags: list[str] = []
    explanation: list[str] = []
    schedule_trusted = True

    if not p.name:
        flags.append(t(lang, "flag_no_name"))
    if not p.strength:
        flags.append(t(lang, "flag_no_strength"))

    # --- schedule ---
    schedule_raw = p.pattern_raw or p.abbr_raw
    if p.pattern is None and p.abbr_key is None:
        flags.append(t(lang, "flag_no_frequency"))
        schedule_trusted = False
    else:
        if p.pattern is not None:
            if any(n > 3 for n in p.pattern) or not any(p.pattern):
                flags.append(t(lang, "flag_unusual_number", value=p.pattern_raw))
                schedule_trusted = False
            elif p.abbr_key in ABBR_COUNT and sum(1 for n in p.pattern if n > 0) != ABBR_COUNT[p.abbr_key]:
                flags.append(t(lang, "flag_conflict"))
                schedule_trusted = False
        if (
            p.pattern is None
            and p.abbr_key == "od"
            and p.abbr_raw
            and p.abbr_raw.lower() == "od"
            and (p.form in ("drops", "ointment") or re.search(r"\beye\b", source, re.I))
        ):
            flags.append(t(lang, "flag_od_eye"))
            schedule_trusted = False

    # --- build the explanation lines ---
    if p.name:
        explanation.append(t(lang, "line_name", value=p.name))
    if p.form:
        explanation.append(t(lang, "line_form", value=t(lang, f"form_{p.form}")))
    if p.strength:
        explanation.append(t(lang, "line_strength", value=p.strength))
    if schedule_trusted and p.pattern is not None:
        meaning = _explain_pattern(p, lang)
        if meaning:
            explanation.append(t(lang, "line_schedule", raw=p.pattern_raw, meaning=meaning))
    if schedule_trusted and p.pattern is None and p.abbr_key:
        explanation.append(
            t(lang, "line_schedule", raw=p.abbr_raw, meaning=t(lang, f"freq_{p.abbr_key}"))
        )
    if p.timing_key:
        explanation.append(
            t(lang, "line_timing", raw=p.timing_raw, meaning=t(lang, f"timing_{p.timing_key}"))
        )
    if p.duration_n is not None:
        explanation.append(
            t(lang, "line_duration", value=_duration_text(p.duration_n, p.duration_unit, lang))
        )

    status = "needs_confirmation" if flags else "explained"
    return ExplainedItem(
        source_text=source,
        status=status,
        status_label=t(lang, f"status_{status}"),
        form=t(lang, f"form_{p.form}") if p.form else None,
        name=p.name,
        strength=p.strength,
        schedule=schedule_raw,
        timing=p.timing_raw,
        duration=p.duration_raw,
        explanation=explanation,
        flags=flags,
    )


# ---------- optional AI general information (validated) ----------

BANNED_EN = re.compile(
    r"\b(stop|stopping|increase|decrease|double|switch|replace|instead|diagnos\w*|you have|"
    r"dose|doses|dosage|mg|mcg|take\s+(?:it|this))\b",
    re.I,
)
BANNED_KN = re.compile(r"ನಿಲ್ಲಿಸ|ಹೆಚ್ಚಿಸ|ಬದಲಾಯಿಸ|ಡೋಸ್|ರೋಗ ನಿರ್ಣಯ|ಪ್ರಮಾಣ")
DIGIT_RE = re.compile(r"[0-9೦-೯]")
LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-]+")


def validate_general_info(data, names: list[str], lang: str) -> dict[str, str]:
    """Keep only safe, short entries for names that were really requested."""
    if not isinstance(data, dict):
        return {}
    allowed_latin = {tok.lower() for n in names for tok in LATIN_TOKEN_RE.findall(n)}
    clean: dict[str, str] = {}
    for key, value in data.items():
        if key not in names or not isinstance(value, str):
            continue  # unknown / invented medicine name -> dropped
        value = value.strip()
        if not value or len(value) > 300:
            continue
        if DIGIT_RE.search(value):
            continue  # no numbers: this blocks invented doses
        if BANNED_EN.search(value) or (lang == "kn" and BANNED_KN.search(value)):
            continue
        if lang == "kn":
            extra = {tok.lower() for tok in LATIN_TOKEN_RE.findall(value)} - allowed_latin
            if extra:
                continue  # a Latin word that is not one of our medicine names
        clean[key] = value
    return clean


def fetch_general_info(names: list[str], lang: str) -> dict[str, str]:
    language = LLM_LANGUAGE_NAMES.get(lang, "English")
    system = (
        "You give very short general information about medicines. Rules: output a JSON object. "
        "Each key must be EXACTLY one of the medicine names you are given. Each value is ONE simple "
        f"sentence in {language}, at most 25 words, saying what the medicine is commonly used for. "
        "Never mention doses, amounts, numbers, how long to take it, or tell anyone to start, stop or "
        "change anything. Never diagnose. Do not mention any other medicine. If you do not confidently "
        "recognise a name as a real medicine, give an empty string for it. Keep the medicine name in "
        "English letters."
    )
    prompt = "Medicine names: " + json.dumps(names, ensure_ascii=False)
    raw = gemini_client.generate_text([{"text": prompt}], system=system, json_mode=True)
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return validate_general_info(data, names, lang)


# ---------- main entry point ----------

def explain_text(text: str, lang: str, include_general_info: bool = True) -> ExplainResponse:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()][:MAX_LINES]

    items: list[ExplainedItem] = []
    other: list[str] = []
    marker_in_other = False

    for line in lines:
        has_marker = bool(MARKER_RE.search(line))
        masked = MARKER_RE.sub(" ", line)
        if looks_like_medicine_line(masked, has_marker):
            items.append(build_item(line, lang))
        else:
            other.append(line)
            marker_in_other = marker_in_other or has_marker

    warnings: list[str] = []
    needs_confirmation = any(i.status == "needs_confirmation" for i in items) or marker_in_other
    if needs_confirmation:
        warnings.append(t(lang, "confirm_warning"))
        for item in items:
            label = item.name or item.source_text
            for flag in item.flags:
                warnings.append(f"{label}: {flag}")
        if marker_in_other:
            warnings.append(t(lang, "flag_marker"))

    notes = [t(lang, "general_note")]
    if not items:
        notes.insert(0, t(lang, "no_medicines"))

    general_info: dict[str, str] = {}
    general_info_note = None
    if include_general_info and settings.enable_general_info and settings.gemini_api_key:
        names = sorted({i.name for i in items if i.name and not MARKER_RE.search(i.source_text)})
        if names:
            try:
                general_info = fetch_general_info(names, lang)
            except AppError:
                logger.info("General information step failed; continuing without it.")
                general_info_note = "unavailable"

    return ExplainResponse(
        language=lang,
        labels=label_set(lang),
        transcription="\n".join(lines),
        items=items,
        other_text=other,
        general_info=general_info,
        general_info_note=general_info_note,
        warnings=warnings,
        notes=notes,
        disclaimer=t(lang, "disclaimer"),
    )

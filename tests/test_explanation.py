"""Tests for the safety-critical explanation logic."""

import json

import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.services import explanation_service as ex
from app.services import gemini_client


def one(line, lang="en"):
    """Explain one line and return its item."""
    result = ex.explain_text(line, lang, include_general_info=False)
    assert len(result.items) == 1, f"expected one medicine line for: {line!r}"
    return result.items[0]


# ---------- the normal, clearly written cases ----------

def test_clear_line_is_explained():
    item = one("Tab Paracetamol 500mg 1-0-1 after food x 5 days")
    assert item.status == "explained"
    assert item.name == "Paracetamol"
    assert item.strength == "500mg"
    assert item.form == "Tablet"
    text = " ".join(item.explanation)
    assert "1 tablet in the morning, 1 tablet at night" in text
    assert "after food" in text
    assert "for 5 days" in text
    assert item.flags == []


@pytest.mark.parametrize(
    "line, expected",
    [
        ("Cap Omeprazole 20 mg OD before breakfast", "once a day"),
        ("Syp Cough syrup 5ml TDS", "three times a day"),
        ("Tab Metformin 500mg BD", "twice a day"),
        ("Tab Atorvastatin 10mg HS", "at bedtime"),
        ("Tab Dolo 650mg SOS", "only when needed"),
        ("Inj Ceftriaxone 1 g BD x 5 days", "twice a day"),
        ("Tab Vitamin D3 60000 IU once a week", "once a week"),
        ("Paracetamol 500 mg tds", "three times a day"),
    ],
)
def test_frequency_abbreviations(line, expected):
    item = one(line)
    assert expected in " ".join(item.explanation)


@pytest.mark.parametrize(
    "line, key_text",
    [
        ("Tab X 5mg 1-0-1 AC", "before food"),
        ("Tab X 5mg 1-0-1 PC", "after food"),
        ("Tab X 5mg 1-0-1 after meals", "after food"),
        ("Tab X 5mg 1-0-0 empty stomach", "empty stomach"),
        ("Tab X 5mg 1-0-1 with food", "with food"),
    ],
)
def test_timing(line, key_text):
    assert key_text in " ".join(one(line).explanation)


def test_four_slot_pattern():
    item = one("Tab Cetirizine 10mg 1-0-1-0 AC")
    assert "1 tablet in the morning, 1 tablet in the evening" in " ".join(item.explanation)


def test_capsule_and_syrup_units():
    assert "1 capsule in the morning" in " ".join(one("Cap Doxycycline 100 mg 1-0-1").explanation)
    assert "2 doses in the morning" in " ".join(one("Syp Cough 5ml 2-0-0").explanation)


# ---------- regression tests for bugs found while testing ----------

def test_half_tablet_is_not_read_as_two():
    """1/2-0-1 once became 2-0-1 (double dose). It must be half a tablet."""
    item = one("Tab Folic acid 5mg 1/2-0-1 for 2 weeks")
    text = " ".join(item.explanation)
    assert "1/2 tablet in the morning, 1 tablet at night" in text
    assert "2 tablets in the morning" not in text
    assert item.schedule == "1/2-0-1"


def test_unicode_half_and_one_and_a_half():
    assert "1/2 tablet in the morning" in " ".join(one("Tab X 5mg ½-0-1").explanation)
    assert "1 1/2 tablets in the morning" in " ".join(one("Tab X 5mg 1½-0-1").explanation)


def test_list_numbers_are_not_part_of_the_name():
    assert one("15. Paracetamol 500 mg tds").name == "Paracetamol"
    assert one("3) Tab Metformin 500mg 1-0-1").name == "Metformin"


def test_decimal_strength_is_not_mistaken_for_a_list_number():
    item = one("Eye drops Moxifloxacin 0.5% BD")
    assert item.strength == "0.5%"
    assert item.name == "Moxifloxacin"


def test_singular_duration():
    assert "for 1 month" in " ".join(one("Tab X 5mg OD for 1 month").explanation)
    assert "for 1 day" in " ".join(one("Tab X 5mg OD x 1 day").explanation)
    assert "for 3 days" in " ".join(one("Tab X 5mg OD x 3d").explanation)


# ---------- safety: uncertain, missing or conflicting information ----------

def test_line_with_unsure_marker_is_not_explained_at_all():
    item = one("Tab [?Pantop?] 40mg OD")
    assert item.status == "needs_confirmation"
    assert item.explanation == []
    assert item.name is None and item.strength is None
    assert "NOT explained" in item.flags[0]


def test_marker_anywhere_blocks_the_line():
    item = one("Tab Paracetamol 500mg 1-0-1 [?after food?]")
    assert item.status == "needs_confirmation" and item.explanation == []


def test_missing_strength_is_flagged_not_guessed():
    item = one("Tab Dolo 650 SOS")
    assert item.status == "needs_confirmation"
    assert item.strength is None
    assert any("strength" in f.lower() for f in item.flags)


def test_missing_frequency_is_flagged():
    item = one("Tab Paracetamol 500mg after food")
    assert item.status == "needs_confirmation"
    assert any("how often" in f.lower() for f in item.flags)
    assert not any("means" in line and "after food" not in line for line in item.explanation)


def test_pattern_and_abbreviation_conflict_is_flagged():
    item = one("Tab Amlodipine 5mg BD 1-0-0")
    assert item.status == "needs_confirmation"
    assert any("do not match" in f for f in item.flags)
    assert not any("morning" in line for line in item.explanation)  # schedule NOT explained


def test_unusual_number_is_flagged():
    item = one("Tab Paracetamol 500mg 9-0-1")
    assert item.status == "needs_confirmation"
    assert any("unusual number" in f for f in item.flags)


def test_all_zero_pattern_is_flagged():
    assert one("Tab Paracetamol 500mg 0-0-0").status == "needs_confirmation"


def test_od_for_eye_drops_is_ambiguous_and_not_explained():
    item = one("Eye drops Moxifloxacin 0.5% OD")
    assert item.status == "needs_confirmation"
    assert any("right eye" in f for f in item.flags)
    assert not any("once a day" in line for line in item.explanation)


def test_od_with_eye_word_in_line_is_ambiguous():
    assert one("Tab X 5mg OD right eye").status == "needs_confirmation"


def test_dates_and_doctor_lines_are_other_text():
    result = ex.explain_text(
        "Dr. A. Kumar, MBBS Date: 12/10/2026\nPatient: Test Person Age: 30\nReview after 1 week\n"
        "Tab Paracetamol 500mg 1-0-1 after food",
        "en",
        include_general_info=False,
    )
    assert len(result.items) == 1
    assert len(result.other_text) == 3


def test_date_is_not_mistaken_for_a_schedule():
    result = ex.explain_text("Date: 1-1-2026", "en", include_general_info=False)
    assert result.items == []


def test_no_medicines_gives_a_note():
    result = ex.explain_text("hello world", "en", include_general_info=False)
    assert result.items == []
    assert "No medicine lines" in result.notes[0]


def test_warning_block_only_when_something_needs_confirmation():
    clean = ex.explain_text("Tab Paracetamol 500mg 1-0-1 after food", "en", include_general_info=False)
    assert clean.warnings == []
    unclear = ex.explain_text("Tab Paracetamol 500mg 1-0-1\nTab [?Pantop?] 40mg OD", "en", include_general_info=False)
    assert "pharmacist" in unclear.warnings[0]
    assert len(unclear.warnings) > 1


def test_marker_in_non_medicine_line_still_warns():
    result = ex.explain_text("Dr [?Kumr?]\nTab Paracetamol 500mg 1-0-1", "en", include_general_info=False)
    assert result.warnings, "an unsure word anywhere must trigger the confirmation warning"


def test_disclaimer_and_general_note_always_present():
    result = ex.explain_text("Tab Paracetamol 500mg 1-0-1", "en", include_general_info=False)
    assert "does not replace advice" in result.disclaimer
    assert "Do not change the amount" in " ".join(result.notes)


def test_transcription_is_exactly_the_confirmed_text():
    text = "Tab Paracetamol 500mg 1-0-1\nTab Metformin 500mg BD"
    assert ex.explain_text(text, "en", include_general_info=False).transcription == text


def test_never_invents_medicine_names_or_numbers():
    """Whatever the input, every name, strength and schedule we show must appear in the input."""
    lines = [
        "Tab Paracetamol 500mg 1-0-1 after food x 5 days",
        "Cap Omeprazole 20 mg OD before breakfast",
        "Syp Cough syrup 5ml TDS",
        "Tab Dolo 650 SOS",
        "Tab Folic acid 5mg 1/2-0-1",
        "12. Eye drops Moxifloxacin 0.5% BD",
        "Tab Amlodipine 5mg BD 1-0-0",
        "Tab Vitamin D3 60000 IU once a week",
        "Tab Ibuprofen 400mg 9-9-9",
        "tab    zzzzqx   10 MG   1 - 0 - 1",
    ]
    result = ex.explain_text("\n".join(lines), "en", include_general_info=False)
    for item in result.items:
        for value in (item.name, item.strength, item.schedule, item.timing, item.duration):
            if value:
                assert value in item.source_text, f"{value!r} was not written in {item.source_text!r}"


def test_line_limit():
    text = "\n".join(f"Tab Drug{i} 10mg OD" for i in range(100))
    result = ex.explain_text(text, "en", include_general_info=False)
    assert len(result.items) == ex.MAX_LINES


# ---------- Kannada ----------

def test_kannada_explanation_keeps_names_numbers_and_units():
    item = one("Tab Paracetamol 500mg 1-0-1 after food x 5 days", lang="kn")
    text = " ".join(item.explanation)
    assert "Paracetamol" in text and "500mg" in text and "1-0-1" in text
    assert "ಬೆಳಿಗ್ಗೆ 1 ಮಾತ್ರೆ" in text and "ರಾತ್ರಿ 1 ಮಾತ್ರೆ" in text
    assert "ಊಟದ ನಂತರ" in text
    assert "5 ದಿನಗಳ ಕಾಲ" in text
    assert item.status_label == "ವಿವರಿಸಲಾಗಿದೆ"


def test_kannada_half_and_singular():
    assert "ಅರ್ಧ ಮಾತ್ರೆ" in " ".join(one("Tab X 5mg 1/2-0-1", lang="kn").explanation)
    assert "1 ದಿನದ ಕಾಲ" in " ".join(one("Tab X 5mg OD x 1 day", lang="kn").explanation)


def test_kannada_warnings_and_disclaimer():
    result = ex.explain_text("Tab [?Pantop?] 40mg OD", "kn", include_general_info=False)
    assert "ವೈದ್ಯರು" in result.warnings[0]
    assert "ಪರ್ಯಾಯವಲ್ಲ" in result.disclaimer
    assert result.items[0].status_label == "ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಬೇಕು"
    assert result.labels["lbl_warnings"].startswith("ದಯವಿಟ್ಟು")


# ---------- optional AI "general information" is validated ----------

NAMES = ["Paracetamol", "Metformin"]


def test_validator_accepts_a_safe_sentence():
    data = {"Paracetamol": "Commonly used to lower fever and relieve mild pain."}
    assert ex.validate_general_info(data, NAMES, "en") == data


@pytest.mark.parametrize(
    "sentence",
    [
        "Usually taken as 500 mg for pain.",  # number
        "Take it twice a day with water 2 times.",  # number
        "You can stop it when you feel better.",  # advice: stop
        "You have an infection.",  # diagnosis
        "A common dosage is one tablet.",  # dosage word
        "Use instead of Ibuprofen.",  # replacement advice
        "",  # empty
        "x" * 400,  # too long
    ],
)
def test_validator_rejects_unsafe_sentences(sentence):
    assert ex.validate_general_info({"Paracetamol": sentence}, NAMES, "en") == {}


def test_validator_drops_invented_medicine_names_and_wrong_types():
    data = {"Ibuprofen": "Used for pain.", "Paracetamol": 5, "Metformin": "Used for blood sugar control."}
    assert ex.validate_general_info(data, NAMES, "en") == {"Metformin": "Used for blood sugar control."}
    assert ex.validate_general_info(["not", "a", "dict"], NAMES, "en") == {}


def test_validator_kannada_rules():
    ok = {"Paracetamol": "ಜ್ವರ ಮತ್ತು ಸಣ್ಣ ನೋವಿಗೆ ಸಾಮಾನ್ಯವಾಗಿ ಬಳಸಲಾಗುತ್ತದೆ."}
    assert ex.validate_general_info(ok, NAMES, "kn") == ok
    other_latin = {"Paracetamol": "ಇದು Ibuprofen ಗೆ ಹೋಲುತ್ತದೆ."}
    assert ex.validate_general_info(other_latin, NAMES, "kn") == {}
    kn_digit = {"Paracetamol": "ದಿನಕ್ಕೆ ೩ ಬಾರಿ."}
    assert ex.validate_general_info(kn_digit, NAMES, "kn") == {}
    kn_banned = {"Paracetamol": "ಇದನ್ನು ನಿಲ್ಲಿಸಿ."}
    assert ex.validate_general_info(kn_banned, NAMES, "kn") == {}


def _fake_gemini(monkeypatch, reply):
    calls = []

    def fake(parts, *, system=None, json_mode=False):
        calls.append(parts)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(gemini_client, "generate_text", fake)
    return calls


def test_general_info_added_and_unsafe_parts_removed(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    reply = json.dumps({"Paracetamol": "Commonly used to lower fever.", "Metformin": "Take 500 mg daily."})
    calls = _fake_gemini(monkeypatch, reply)
    result = ex.explain_text("Tab Paracetamol 500mg 1-0-1\nTab Metformin 500mg BD", "en")
    assert result.general_info == {"Paracetamol": "Commonly used to lower fever."}
    # only the confirmed names are sent to the AI, never the doses or schedule
    sent = calls[0][0]["text"]
    assert "Paracetamol" in sent and "500" not in sent and "1-0-1" not in sent


def test_general_info_never_requested_for_uncertain_lines(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls = _fake_gemini(monkeypatch, "{}")
    ex.explain_text("Tab [?Pantop?] 40mg OD", "en")
    assert calls == []


def test_general_info_failure_does_not_break_the_explanation(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    _fake_gemini(monkeypatch, AppError("down"))
    result = ex.explain_text("Tab Paracetamol 500mg 1-0-1", "en")
    assert result.items[0].status == "explained"
    assert result.general_info == {} and result.general_info_note == "unavailable"


def test_general_info_garbage_reply_is_ignored(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    _fake_gemini(monkeypatch, "this is not json")
    assert ex.explain_text("Tab Paracetamol 500mg 1-0-1", "en").general_info == {}


def test_general_info_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "enable_general_info", False)
    calls = _fake_gemini(monkeypatch, "{}")
    ex.explain_text("Tab Paracetamol 500mg 1-0-1", "en")
    assert calls == []

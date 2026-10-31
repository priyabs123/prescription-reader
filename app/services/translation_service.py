"""Languages and all user-facing explanation text.

To add a new language (for example Hindi):
  1. Add it to SUPPORTED_LANGUAGES and LLM_LANGUAGE_NAMES.
  2. Add a new dictionary to STRINGS with exactly the same keys as "en".
The test suite checks that every language has every key.

Medicine names, strengths, numbers and abbreviations are NEVER translated.
They are inserted into these sentences exactly as the user confirmed them.
"""

SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "kn": "ಕನ್ನಡ (Kannada)",
}

LLM_LANGUAGE_NAMES: dict[str, str] = {"en": "English", "kn": "Kannada"}

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # Messages
        "disclaimer": (
            "This tool only helps you read and understand a prescription. "
            "It does not replace advice from your doctor or pharmacist."
        ),
        "confirm_warning": (
            "Before taking any medicine, please confirm unclear details with your "
            "prescribing doctor or a qualified pharmacist."
        ),
        "general_note": (
            "Take medicines exactly as your doctor wrote. Do not change the amount "
            "or stop a medicine without asking your doctor."
        ),
        "no_medicines": (
            "No medicine lines were recognised. A line is recognised when it looks like "
            "'Tab Paracetamol 500mg 1-0-1 after food'. Please check the text above."
        ),
        # Section labels
        "lbl_transcription": "Text you confirmed (from the prescription)",
        "lbl_medicines": "Medicines (explained from your confirmed text)",
        "lbl_other": "Other text on the prescription (not explained)",
        "lbl_warnings": "Please confirm with your doctor or pharmacist",
        "lbl_general_info": "General information (AI-written, NOT from your prescription)",
        "lbl_general_info_caption": (
            "This is general knowledge written by an AI. It can be wrong or incomplete. "
            "It is not advice for you personally."
        ),
        "lbl_notes": "Notes",
        "status_explained": "Explained",
        "status_needs_confirmation": "Needs confirmation",
        # Lines inside one medicine
        "line_name": "Medicine name (as you confirmed): {value}",
        "line_form": "Form: {value}",
        "line_strength": "Strength (as written): {value}",
        "line_schedule": "\"{raw}\" means: {meaning}",
        "line_timing": "\"{raw}\" means: {meaning}",
        "line_duration": "How long: {value}",
        # Flags
        "flag_marker": (
            "This line still has text marked as unsure, so it is NOT explained. "
            "Please confirm it with your doctor or pharmacist."
        ),
        "flag_no_name": "The medicine name could not be found. Please confirm it with your doctor or pharmacist.",
        "flag_no_strength": (
            "No strength (like 500 mg) was found. Please confirm it with your doctor or pharmacist."
        ),
        "flag_no_frequency": (
            "How often to take it was not found. Please confirm it with your doctor or pharmacist."
        ),
        "flag_od_eye": (
            "\"OD\" can mean 'once a day' or 'right eye'. It is NOT explained here. "
            "Please confirm it with your doctor or pharmacist."
        ),
        "flag_unusual_number": (
            "The schedule \"{value}\" has an unusual number, so it is NOT explained. "
            "Please confirm it with your doctor or pharmacist."
        ),
        "flag_conflict": (
            "The schedule and the abbreviation on this line do not match, so the schedule is "
            "NOT explained. Please confirm it with your doctor or pharmacist."
        ),
        # Forms
        "form_tablet": "Tablet",
        "form_capsule": "Capsule",
        "form_syrup": "Syrup",
        "form_injection": "Injection",
        "form_drops": "Drops",
        "form_ointment": "Ointment",
        "form_cream": "Cream",
        "form_gel": "Gel",
        "form_suspension": "Suspension",
        # Units
        "unit_tablet": "tablet",
        "unit_tablets": "tablets",
        "unit_capsule": "capsule",
        "unit_capsules": "capsules",
        "unit_dose": "dose",
        "unit_doses": "doses",
        # Slots of the day for patterns such as 1-0-1
        "slot_morning": "{n} {unit} in the morning",
        "slot_afternoon": "{n} {unit} in the afternoon",
        "slot_evening": "{n} {unit} in the evening",
        "slot_night": "{n} {unit} at night",
        # Frequency abbreviations
        "freq_weekly": "once a week",
        "freq_od": "once a day",
        "freq_bd": "twice a day",
        "freq_tds": "three times a day",
        "freq_qid": "four times a day",
        "freq_hs": "at bedtime",
        "freq_sos": "only when needed",
        "freq_stat": "immediately, one time",
        # Timing
        "timing_ac": "before food (take it before a meal)",
        "timing_pc": "after food (take it after you have eaten a meal)",
        "timing_empty": "on an empty stomach (when you have not eaten)",
        "timing_with_food": "with food (take it together with a meal)",
        # Duration
        "duration_day": "for {n} day",
        "duration_days": "for {n} days",
        "duration_week": "for {n} week",
        "duration_weeks": "for {n} weeks",
        "duration_month": "for {n} month",
        "duration_months": "for {n} months",
        # Quantity
        "qty_half": "1/2",
    },
    "kn": {
        "disclaimer": (
            "ಈ ಸಾಧನವು ಪ್ರಿಸ್ಕ್ರಿಪ್ಷನ್ ಅನ್ನು ಓದಲು ಮತ್ತು ಅರ್ಥಮಾಡಿಕೊಳ್ಳಲು ಮಾತ್ರ ಸಹಾಯ ಮಾಡುತ್ತದೆ. "
            "ಇದು ನಿಮ್ಮ ವೈದ್ಯರ ಅಥವಾ ಔಷಧಿಕಾರರ ಸಲಹೆಗೆ ಪರ್ಯಾಯವಲ್ಲ."
        ),
        "confirm_warning": (
            "ಯಾವುದೇ ಔಷಧಿ ತೆಗೆದುಕೊಳ್ಳುವ ಮೊದಲು, ಅಸ್ಪಷ್ಟವಾಗಿರುವ ವಿವರಗಳನ್ನು ಔಷಧಿ ಬರೆದ ವೈದ್ಯರು "
            "ಅಥವಾ ಅರ್ಹ ಔಷಧಿಕಾರರಿಂದ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ."
        ),
        "general_note": (
            "ವೈದ್ಯರು ಬರೆದಂತೆಯೇ ಔಷಧಿಗಳನ್ನು ತೆಗೆದುಕೊಳ್ಳಿ. ವೈದ್ಯರನ್ನು ಕೇಳದೆ ಪ್ರಮಾಣವನ್ನು "
            "ಬದಲಾಯಿಸಬೇಡಿ ಅಥವಾ ಔಷಧಿಯನ್ನು ನಿಲ್ಲಿಸಬೇಡಿ."
        ),
        "no_medicines": (
            "ಯಾವುದೇ ಔಷಧಿಯ ಸಾಲು ಗುರುತಿಸಲಾಗಲಿಲ್ಲ. 'Tab Paracetamol 500mg 1-0-1 after food' "
            "ಎಂಬಂತೆ ಇರುವ ಸಾಲು ಗುರುತಿಸಲ್ಪಡುತ್ತದೆ. ದಯವಿಟ್ಟು ಮೇಲಿನ ಪಠ್ಯವನ್ನು ಪರಿಶೀಲಿಸಿ."
        ),
        "lbl_transcription": "ನೀವು ದೃಢೀಕರಿಸಿದ ಪಠ್ಯ (ಪ್ರಿಸ್ಕ್ರಿಪ್ಷನ್‌ನಿಂದ)",
        "lbl_medicines": "ಔಷಧಿಗಳು (ನೀವು ದೃಢೀಕರಿಸಿದ ಪಠ್ಯದ ವಿವರಣೆ)",
        "lbl_other": "ಪ್ರಿಸ್ಕ್ರಿಪ್ಷನ್‌ನಲ್ಲಿರುವ ಇತರ ಪಠ್ಯ (ವಿವರಿಸಿಲ್ಲ)",
        "lbl_warnings": "ದಯವಿಟ್ಟು ವೈದ್ಯರು ಅಥವಾ ಔಷಧಿಕಾರರಿಂದ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ",
        "lbl_general_info": "ಸಾಮಾನ್ಯ ಮಾಹಿತಿ (AI ಬರೆದದ್ದು, ನಿಮ್ಮ ಪ್ರಿಸ್ಕ್ರಿಪ್ಷನ್‌ನಲ್ಲಿರುವುದಲ್ಲ)",
        "lbl_general_info_caption": (
            "ಇದು AI ಬರೆದ ಸಾಮಾನ್ಯ ಮಾಹಿತಿ ಮಾತ್ರ. ಇದರಲ್ಲಿ ತಪ್ಪು ಅಥವಾ ಕೊರತೆ ಇರಬಹುದು. "
            "ಇದು ನಿಮಗಾಗಿ ನೀಡಿದ ಸಲಹೆಯಲ್ಲ."
        ),
        "lbl_notes": "ಸೂಚನೆಗಳು",
        "status_explained": "ವಿವರಿಸಲಾಗಿದೆ",
        "status_needs_confirmation": "ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಬೇಕು",
        "line_name": "ಔಷಧದ ಹೆಸರು (ನೀವು ದೃಢೀಕರಿಸಿದಂತೆ): {value}",
        "line_form": "ರೂಪ: {value}",
        "line_strength": "ಪ್ರಮಾಣ (ಬರೆದಂತೆ): {value}",
        "line_schedule": "\"{raw}\" ಎಂದರೆ: {meaning}",
        "line_timing": "\"{raw}\" ಎಂದರೆ: {meaning}",
        "line_duration": "ಎಷ್ಟು ಕಾಲ: {value}",
        "flag_marker": (
            "ಈ ಸಾಲಿನಲ್ಲಿ ಖಚಿತವಿಲ್ಲದ ಪಠ್ಯ ಇನ್ನೂ ಇದೆ, ಆದ್ದರಿಂದ ಇದನ್ನು ವಿವರಿಸಿಲ್ಲ. "
            "ವೈದ್ಯರು ಅಥವಾ ಔಷಧಿಕಾರರಿಂದ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ."
        ),
        "flag_no_name": "ಔಷಧದ ಹೆಸರು ಸಿಗಲಿಲ್ಲ. ವೈದ್ಯರು ಅಥವಾ ಔಷಧಿಕಾರರಿಂದ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ.",
        "flag_no_strength": (
            "ಔಷಧದ ಪ್ರಮಾಣ (ಉದಾಹರಣೆಗೆ 500 mg) ಸಿಗಲಿಲ್ಲ. ವೈದ್ಯರು ಅಥವಾ ಔಷಧಿಕಾರರಿಂದ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ."
        ),
        "flag_no_frequency": (
            "ಎಷ್ಟು ಬಾರಿ ತೆಗೆದುಕೊಳ್ಳಬೇಕು ಎಂಬುದು ಸಿಗಲಿಲ್ಲ. ವೈದ್ಯರು ಅಥವಾ ಔಷಧಿಕಾರರಿಂದ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ."
        ),
        "flag_od_eye": (
            "\"OD\" ಎಂದರೆ 'ದಿನಕ್ಕೆ ಒಂದು ಬಾರಿ' ಅಥವಾ 'ಬಲಗಣ್ಣು' ಎರಡೂ ಆಗಬಹುದು. ಇದನ್ನು ಇಲ್ಲಿ ವಿವರಿಸಿಲ್ಲ. "
            "ವೈದ್ಯರು ಅಥವಾ ಔಷಧಿಕಾರರಿಂದ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ."
        ),
        "flag_unusual_number": (
            "ವೇಳಾಪಟ್ಟಿ \"{value}\" ನಲ್ಲಿ ಅಸಾಮಾನ್ಯ ಸಂಖ್ಯೆ ಇದೆ, ಆದ್ದರಿಂದ ಅದನ್ನು ವಿವರಿಸಿಲ್ಲ. "
            "ವೈದ್ಯರು ಅಥವಾ ಔಷಧಿಕಾರರಿಂದ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ."
        ),
        "flag_conflict": (
            "ಈ ಸಾಲಿನಲ್ಲಿರುವ ವೇಳಾಪಟ್ಟಿ ಮತ್ತು ಸಂಕ್ಷೇಪಣ ಹೊಂದಿಕೆಯಾಗುತ್ತಿಲ್ಲ, ಆದ್ದರಿಂದ ವೇಳಾಪಟ್ಟಿಯನ್ನು "
            "ವಿವರಿಸಿಲ್ಲ. ವೈದ್ಯರು ಅಥವಾ ಔಷಧಿಕಾರರಿಂದ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ."
        ),
        "form_tablet": "ಮಾತ್ರೆ (Tablet)",
        "form_capsule": "ಕ್ಯಾಪ್ಸೂಲ್ (Capsule)",
        "form_syrup": "ಸಿರಪ್ (Syrup)",
        "form_injection": "ಚುಚ್ಚುಮದ್ದು (Injection)",
        "form_drops": "ಹನಿಗಳು (Drops)",
        "form_ointment": "ಮುಲಾಮು (Ointment)",
        "form_cream": "ಕ್ರೀಮ್ (Cream)",
        "form_gel": "ಜೆಲ್ (Gel)",
        "form_suspension": "ಸಸ್ಪೆನ್ಷನ್ (Suspension)",
        "unit_tablet": "ಮಾತ್ರೆ",
        "unit_tablets": "ಮಾತ್ರೆ",
        "unit_capsule": "ಕ್ಯಾಪ್ಸೂಲ್",
        "unit_capsules": "ಕ್ಯಾಪ್ಸೂಲ್",
        "unit_dose": "ಡೋಸ್",
        "unit_doses": "ಡೋಸ್",
        "slot_morning": "ಬೆಳಿಗ್ಗೆ {n} {unit}",
        "slot_afternoon": "ಮಧ್ಯಾಹ್ನ {n} {unit}",
        "slot_evening": "ಸಂಜೆ {n} {unit}",
        "slot_night": "ರಾತ್ರಿ {n} {unit}",
        "freq_weekly": "ವಾರಕ್ಕೆ ಒಂದು ಬಾರಿ",
        "freq_od": "ದಿನಕ್ಕೆ ಒಂದು ಬಾರಿ",
        "freq_bd": "ದಿನಕ್ಕೆ ಎರಡು ಬಾರಿ",
        "freq_tds": "ದಿನಕ್ಕೆ ಮೂರು ಬಾರಿ",
        "freq_qid": "ದಿನಕ್ಕೆ ನಾಲ್ಕು ಬಾರಿ",
        "freq_hs": "ರಾತ್ರಿ ಮಲಗುವ ಮುನ್ನ",
        "freq_sos": "ಅಗತ್ಯವಿದ್ದಾಗ ಮಾತ್ರ",
        "freq_stat": "ತಕ್ಷಣ, ಒಂದು ಬಾರಿ",
        "timing_ac": "ಊಟಕ್ಕೆ ಮೊದಲು (ಊಟಕ್ಕೆ ಮುಂಚೆ ತೆಗೆದುಕೊಳ್ಳಿ)",
        "timing_pc": "ಊಟದ ನಂತರ (ಊಟ ಮಾಡಿದ ಮೇಲೆ ತೆಗೆದುಕೊಳ್ಳಿ)",
        "timing_empty": "ಖಾಲಿ ಹೊಟ್ಟೆಯಲ್ಲಿ (ಏನೂ ತಿನ್ನದೆ ಇರುವಾಗ)",
        "timing_with_food": "ಆಹಾರದ ಜೊತೆಗೆ (ಊಟದ ಜೊತೆಯಲ್ಲಿ ತೆಗೆದುಕೊಳ್ಳಿ)",
        "duration_day": "{n} ದಿನದ ಕಾಲ",
        "duration_days": "{n} ದಿನಗಳ ಕಾಲ",
        "duration_week": "{n} ವಾರದ ಕಾಲ",
        "duration_weeks": "{n} ವಾರಗಳ ಕಾಲ",
        "duration_month": "{n} ತಿಂಗಳ ಕಾಲ",
        "duration_months": "{n} ತಿಂಗಳ ಕಾಲ",
        "qty_half": "ಅರ್ಧ",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    """Look up a sentence in the chosen language and fill in the {placeholders}."""
    table = STRINGS.get(lang) or STRINGS["en"]
    text = table.get(key) or STRINGS["en"][key]
    return text.format(**kwargs) if kwargs else text


def label_set(lang: str) -> dict[str, str]:
    """The section titles the frontend shows, in the chosen language."""
    keys = [
        "lbl_transcription",
        "lbl_medicines",
        "lbl_other",
        "lbl_warnings",
        "lbl_general_info",
        "lbl_general_info_caption",
        "lbl_notes",
    ]
    return {k: t(lang, k) for k in keys}

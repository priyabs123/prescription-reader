import re

from app.services import translation_service as tr

PLACEHOLDER = re.compile(r"\{(\w+)\}")


def test_every_language_has_every_key():
    english = set(tr.STRINGS["en"])
    for code in tr.SUPPORTED_LANGUAGES:
        assert code in tr.STRINGS, f"{code} has no strings"
        assert set(tr.STRINGS[code]) == english, f"{code} keys differ from English"


def test_placeholders_match_between_languages():
    for key, english in tr.STRINGS["en"].items():
        wanted = set(PLACEHOLDER.findall(english))
        for code in tr.SUPPORTED_LANGUAGES:
            assert set(PLACEHOLDER.findall(tr.STRINGS[code][key])) == wanted, f"{code}:{key}"


def test_no_empty_strings():
    for code, table in tr.STRINGS.items():
        for key, value in table.items():
            assert value.strip(), f"{code}:{key} is empty"


def test_kannada_strings_contain_kannada_script():
    kannada = re.compile(r"[ಀ-೿]")
    for key, value in tr.STRINGS["kn"].items():
        if key.startswith(("line_", "form_")) or key == "qty_half":
            continue  # these may be mostly placeholders
        assert kannada.search(value), f"kn:{key} has no Kannada text"


def test_t_fills_placeholders_and_falls_back_to_english():
    assert tr.t("en", "duration_days", n=5) == "for 5 days"
    assert tr.t("xx", "duration_days", n=5) == "for 5 days"  # unknown language -> English


def test_label_set_in_both_languages():
    en, kn = tr.label_set("en"), tr.label_set("kn")
    assert set(en) == set(kn) and len(en) == 7
    assert en != kn


def test_llm_language_names_cover_all_languages():
    assert set(tr.LLM_LANGUAGE_NAMES) == set(tr.SUPPORTED_LANGUAGES)

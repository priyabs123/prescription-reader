# Prescription Reader (AI-Powered Prescription Reader and Explainer)

Upload a photo of a prescription, check the text the reader found, and get a simple explanation in
English or Kannada. Built with FastAPI, Pillow and plain HTML/CSS/JavaScript.

> **This is a college prototype. It is not clinically validated and does not replace a doctor or pharmacist.**

## Run it (Windows)

```
cd prescription_reader
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000. (Mac/Linux: `source venv/bin/activate` and `cp .env.example .env`.)

It works with **no keys**: type or paste the text, or press "load a sample prescription". To read photos,
put ONE of these in `.env` (never commit `.env`):

| Key | What it gives |
|---|---|
| `GOOGLE_VISION_API_KEY` | Best choice. Google Cloud Vision gives a confidence score per word, so unsure words are marked `[?word?]`. Create the key in Google Cloud Console (enable "Cloud Vision API"; a billing card is needed; set a budget alert). |
| `GEMINI_API_KEY` | Free tier from Google AI Studio. Reads the image but gives no confidence scores. Also enables the optional "general information" box. |

Restart the server after editing `.env`. If Google retires the model, change `GEMINI_MODEL`.

## Run the tests
```
pip install -r requirements-dev.txt
python -m pytest
```
No test needs internet or a key.

## How it works
1. **Upload** (`/api/upload`): validate type, size and real content, fix rotation, check quality (dark, blank, blurry, cut-off), re-encode as a clean JPEG in memory, run OCR.
2. **Review**: unsure words appear as `[?word?]`. The user edits the text and ticks "I have compared this text". Editing again clears the tick.
3. **Explain** (`/api/explain`): plain code (regular expressions and fixed tables) finds form, name, strength, schedule, timing and duration, and explains abbreviations such as `1-0-1`, `OD`, `AC`, `PC`.

## Safety rules built in
- Any line containing `[?...?]` is **never** explained.
- Missing strength or frequency, conflicts (`BD 1-0-0`), unusual numbers (`9-0-1`) and ambiguous `OD` for eye drops are flagged, not guessed.
- Names, strengths and schedules are copied exactly as written. A test checks nothing is invented.
- Fractions (`1/2-0-1`) are read as half a tablet, never as 2.
- No diagnosis, no dose changes, no medicine suggestions. The disclaimer is shown every time.
- The optional AI "general information" box sends only confirmed medicine names, is validated (no numbers, no advice words, no other medicines) and is labelled "NOT from your prescription".

## Privacy
Images are processed in memory and never saved. Prescription text and OCR output are never logged. API responses are `no-store`.
EXIF/GPS data is stripped from photos. If you use Google services, the image or text is sent to Google.

## Folder guide
| File | Purpose |
|---|---|
| `app/main.py` | Creates the app, security headers, friendly error handlers |
| `app/routes/prescription.py` | HTTP endpoints only |
| `app/services/image_processing.py` | Validation and photo quality checks |
| `app/services/ocr_service.py` | Google Vision / Gemini OCR, unsure-word marking |
| `app/services/gemini_client.py` | Small Gemini HTTP wrapper |
| `app/services/explanation_service.py` | Parser, safety flags, validated AI info |
| `app/services/translation_service.py` | All English and Kannada text |
| `app/schemas/prescription.py` | Pydantic request/response models |
| `app/core/config.py`, `errors.py` | Settings from `.env`; user-safe errors |
| `templates/index.html`, `static/` | The one-page interface |
| `tests/` | Automated tests |

(`result.html` from the original plan is not needed: results appear on the same page.)

## Add a language
In `translation_service.py`, add the language to `SUPPORTED_LANGUAGES` and `LLM_LANGUAGE_NAMES`, and add a dictionary to `STRINGS` with the same keys as `"en"`. A test checks that all keys and placeholders match.

## Limitations (say these in your viva)
- Handwriting OCR is unreliable; the user-correction step is the main safety feature.
- Quality thresholds were tuned on synthetic images only; test with real, de-identified photos.
- The parser understands common Indian prescription styles (`Tab X 500mg 1-0-1 after food x 5 days`). Other styles are flagged or listed as "other text".
- No drug database, dose checking or interaction checking.
- The Kannada wording was written by an AI assistant; have a Kannada-speaking doctor or pharmacist review it.
- No login, no rate limiting, no database. Add these before any public deployment.

## Deploy (Render / Railway)
Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Set the keys as environment variables on the host, not in files.

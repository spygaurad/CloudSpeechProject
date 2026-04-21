# Cloud Speech Project (FastAPI)

FastAPI backend for the Azure speech pipeline assignment (CSC 391 / CSC 691).

**Pipeline:** audio upload → Azure Speech STT → Azure AI Language → Neural TTS summary → single JSON response

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/transcribe` | Speech-to-text via Azure Speech SDK |
| `POST` | `/analyze` | Key phrases, NER, sentiment, linked entities |
| `POST` | `/process` | Full pipeline: transcribe → analyze → TTS |
| `GET` | `/summary-audio` | Binary MP3 TTS stream |
| `GET` | `/voices` | Available Neural TTS voices |
| `GET` | `/health` | Liveness check |

---

## 1. Environment Setup

**Activate the virtual environment:**

```bash
source ../cloud_venv/bin/activate
```

**Install dependencies:**

```bash
pip install -r requirements.txt
```

> `ffmpeg` must be available on PATH for MP3/OGG/M4A transcription (`brew install ffmpeg` on macOS).

**Create `.env` in the project root:**

```env
AZURE_SPEECH_KEY=<your-speech-key>
AZURE_SPEECH_REGION=<region, e.g. eastus2>
AZURE_LANGUAGE_KEY=<your-language-key>
AZURE_LANGUAGE_ENDPOINT=https://<your-language-resource>.cognitiveservices.azure.com/
```

---

## 2. Run the API

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive docs: `http://127.0.0.1:8000/docs`

---

## 3. Endpoint Reference

### B3 — `POST /transcribe`

Accepts a multipart `audio` field. Converts non-WAV files to 16 kHz/16-bit/mono PCM WAV
via `ffmpeg` before sending to Azure Speech SDK (ensures cross-platform compressed-format support).

| Format | Support | Notes |
|--------|---------|-------|
| WAV (PCM) | Full | Sent directly to SDK |
| MP3 | Full | ffmpeg → WAV, then SDK |
| OGG / Opus | Full | ffmpeg → WAV, then SDK |
| AAC / M4A | Full | ffmpeg → WAV, then SDK |
| Corrupted file | — | HTTP 415 |
| FLAC, MP4, MOV, … | — | HTTP 415 |

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/transcribe \
  -F "audio=@sample.wav"
```

**Response (HTTP 200):**
```json
{
  "transcript": "Hi we are testing Azure ASR and TTS services.",
  "language": "en-US",
  "confidence": 0.5987509,
  "words": [
    {"word": "hi",       "confidence": 0.8532638},
    {"word": "we",       "confidence": 0.4860277},
    {"word": "are",      "confidence": 0.2032354},
    {"word": "testing",  "confidence": 0.8773377},
    {"word": "azure",    "confidence": 0.6593656},
    {"word": "ASR",      "confidence": 0.5251484},
    {"word": "and",      "confidence": 0.7133810},
    {"word": "TTS",      "confidence": 0.1819523},
    {"word": "services", "confidence": 0.8890462}
  ]
}
```

**Format error (HTTP 415):**
```json
{
  "detail": "Unsupported or invalid audio media format. Supported: WAV (PCM), MP3, OGG/Opus, AAC/M4A. Ensure the file is a valid audio file and not corrupted."
}
```

---

### C1 — `POST /analyze`

Calls Azure AI Language for all four analyses in sequence and returns them in a single object.

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "Hi we are testing Azure ASR and TTS services."}'
```

**Live response (HTTP 200):**
```json
{
  "key_phrases": ["Azure ASR", "TTS services"],
  "named_entities": [
    {"text": "Azure ASR", "category": "Product", "subcategory": "ComputingProduct", "confidence": 0.8},
    {"text": "TTS",       "category": "Product", "subcategory": null,                "confidence": 0.46}
  ],
  "sentiment": {
    "label": "neutral",
    "confidence": {"positive": 0.0, "neutral": 1.0, "negative": 0.0}
  },
  "linked_entities": [
    {
      "name": "Microsoft Azure",
      "url": "https://en.wikipedia.org/wiki/Microsoft_Azure",
      "data_source": "Wikipedia",
      "entity_id": "Microsoft Azure",
      "matches": [{"text": "Azure", "offset": 18, "length": 5, "confidenceScore": 0.16}]
    }
  ]
}
```

---

### C2 — `POST /process` (Combined Pipeline)

Executes the complete pipeline in one request:
1. Accept audio file upload
2. Transcribe with Azure Speech → transcript
3. Analyze transcript with Azure AI Language → entities, phrases, sentiment
4. Generate human-readable summary string (D1)
5. Synthesize Neural TTS MP3 (D2)
6. Return all results in a single JSON response

Optional form field `voice` selects the TTS voice (default: `en-US-JennyNeural`).

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/process \
  -F "audio=@sample.mp3" \
  -F "voice=en-US-JennyNeural"
```

**Live response (HTTP 200) — `asr_tts_test.mp3`:**
```json
{
  "transcription": {
    "transcript": "Hi we are testing Azure ASR and TTS services.",
    "language": "en-US",
    "confidence": 0.5987509,
    "words": [
      {"word": "hi",       "confidence": 0.8532638},
      {"word": "testing",  "confidence": 0.8773377},
      {"word": "services", "confidence": 0.8890462}
    ]
  },
  "analysis": {
    "key_phrases": ["Azure ASR", "TTS services"],
    "named_entities": [
      {"text": "Azure ASR", "category": "Product", "subcategory": "ComputingProduct", "confidence": 0.8},
      {"text": "TTS",       "category": "Product", "subcategory": null,                "confidence": 0.46}
    ],
    "sentiment": {
      "label": "neutral",
      "confidence": {"positive": 0.0, "neutral": 1.0, "negative": 0.0}
    },
    "linked_entities": [
      {
        "name": "Microsoft Azure",
        "url": "https://en.wikipedia.org/wiki/Microsoft_Azure",
        "data_source": "Wikipedia",
        "entity_id": "Microsoft Azure"
      }
    ]
  },
  "summary_text": "Your memo mentions 2 key topics: Azure ASR, TTS services. The overall tone is neutral. I detected entity types including 2 Product.",
  "tts": {
    "voice": "en-US-JennyNeural",
    "format": "Audio16Khz32KBitRateMonoMp3",
    "audio_base64": "<base64-encoded MP3 — 61056 chars>"
  }
}
```

---

### D1 — Summary Generator

`summary_text` is built from the analysis results before TTS synthesis. Format:

```
"Your memo mentions <N> key topics: <topic1>, <topic2>, ...
The overall tone is <sentiment>.
I detected entity types including <count> <Category>, ..."
```

Example from live run:
```
"Your memo mentions 2 key topics: Azure ASR, TTS services.
The overall tone is neutral.
I detected entity types including 2 Product."
```

---

### D2 — `GET /summary-audio`

Returns a binary `audio/mpeg` stream playable directly in an HTML5 `<audio>` element.

- Voice: Neural only (`en-US-JennyNeural`, `en-US-GuyNeural`, `en-US-AriaNeural`)
- Format: `Audio16Khz32KBitRateMonoMp3`

```bash
curl "http://127.0.0.1:8000/summary-audio?text=Hello+world&voice=en-US-AriaNeural" \
  --output summary.mp3
```

---

### D3 — `GET /voices`

Returns the three available Neural TTS voices with distinct personas.

```bash
curl http://127.0.0.1:8000/voices
```

```json
{
  "voices": [
    {"name": "en-US-AriaNeural",  "persona": "energetic"},
    {"name": "en-US-GuyNeural",   "persona": "casual"},
    {"name": "en-US-JennyNeural", "persona": "formal"}
  ]
}
```

---

## 4. Test Results — All 16 Tests Pass

```
pytest -v
```

```
tests/test_api.py::test_transcribe_rejects_unsupported_format[sample.flac-audio/flac]   PASSED
tests/test_api.py::test_transcribe_rejects_unsupported_format[sample.mp4-video/mp4]     PASSED
tests/test_api.py::test_transcribe_rejects_unsupported_format[sample.mov-video/quicktime] PASSED
tests/test_api.py::test_transcribe_rejects_unsupported_format[sample.pdf-application/pdf] PASSED
tests/test_api.py::test_transcribe_success_shape                                         PASSED
tests/test_api.py::test_analyze_returns_all_sections                                     PASSED
tests/test_api.py::test_process_combined_pipeline                                        PASSED
tests/test_api.py::test_voices_has_three_or_more                                         PASSED
tests/test_api.py::test_summary_audio_binary                                             PASSED
tests/test_custom_audio_integration.py::test_custom_audio_fixtures_exist                 PASSED
tests/test_custom_audio_integration.py::test_transcribe_with_custom_audio_fixture[asr_tts_test.mp3]           PASSED
tests/test_custom_audio_integration.py::test_transcribe_with_custom_audio_fixture[asr_tts_test_corrupted.mp3] PASSED
tests/test_custom_audio_integration.py::test_transcribe_with_custom_audio_fixture[asr_tts_test_m4a.m4a]       PASSED
tests/test_custom_audio_integration.py::test_transcribe_with_custom_audio_fixture[asr_tts_test_ogg.opus]      PASSED
tests/test_custom_audio_integration.py::test_transcribe_with_custom_audio_fixture[asr_tts_test_wav.wav]       PASSED
tests/test_custom_audio_integration.py::test_process_with_first_custom_audio_fixture                          PASSED

16 passed in 11.15s
```

**Unit tests** (`test_api.py`, 9 tests) — mock Azure services, verify endpoint contracts and error codes.

**Integration tests** (`test_custom_audio_integration.py`, 7 tests) — call live Azure Speech and Language endpoints using fixture files.

Run only unit tests (no Azure credentials required):

```bash
pytest -q -m "not integration"
```

Run full suite including live Azure calls:

```bash
pytest -v
```

---

## 5. Project Structure

```
app/
  main.py                      # FastAPI app, all route handlers
  config.py                    # Env vars, voice list, accepted extensions
  schemas.py                   # Pydantic request/response models
  services/
    audio_service.py           # Upload validation, temp file save/cleanup
    transcription_service.py   # Azure Speech SDK + ffmpeg format conversion
    language_service.py        # Azure AI Language REST calls (4 analyses)
    summary_service.py         # D1 human-readable summary builder
    tts_service.py             # Azure Neural TTS synthesis
tests/
  conftest.py
  test_api.py                  # Unit tests (mocked)
  test_custom_audio_integration.py  # Live integration tests
  fixtures/
    audio/                     # Drop real audio files here for live tests
requirements.txt
.env                           # Not committed — add your Azure keys here
README.md
```

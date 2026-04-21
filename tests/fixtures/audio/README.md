# Audio Fixtures for Live Integration Tests

Drop real audio files into this folder to run live Azure Speech + Language tests.

---

## Accepted Extensions

| Extension | Format | Support |
|-----------|--------|---------|
| `.wav` | PCM WAV | Full — sent directly to Azure Speech SDK |
| `.mp3` | MPEG Audio | Full — converted to WAV via ffmpeg first |
| `.ogg` / `.opus` | OGG/Opus | Full — converted to WAV via ffmpeg first |
| `.aac` / `.m4a` | AAC | Full — converted to WAV via ffmpeg first |

Files with any other extension (`.flac`, `.mp4`, `.mov`, etc.) are ignored by the test collector.

**Recommended WAV spec for best recognition quality:**
- Encoding: PCM
- Sample rate: 16 kHz
- Bit depth: 16-bit
- Channels: mono

---

## Current Fixture Files

| File | Description | Expected Behaviour |
|------|-------------|-------------------|
| `asr_tts_test_wav.wav` | Clean speech, WAV PCM | HTTP 200 — transcript returned |
| `asr_tts_test.mp3` | Same speech, MP3 | HTTP 200 — transcript returned |
| `asr_tts_test_ogg.opus` | Same speech, OGG/Opus | HTTP 200 — transcript returned |
| `asr_tts_test_m4a.m4a` | Same speech, M4A | HTTP 200 — transcript returned |
| `asr_tts_test_corrupted.mp3` | Corrupted/invalid MP3 | HTTP 415 — format error returned |
| `asr_tts_test_flac.flac` | FLAC (unsupported) | Skipped by test collector |

### Live Transcript Output (all working formats)

All four valid files produce the same transcript against Azure Speech:

```
"Hi we are testing Azure ASR and TTS services."
```

Confidence scores observed:

| File | Confidence |
|------|-----------|
| `asr_tts_test_wav.wav` | 0.609 |
| `asr_tts_test.mp3` | 0.599 |
| `asr_tts_test_ogg.opus` | 0.617 |
| `asr_tts_test_m4a.m4a` | 0.615 |

---

## Running the Tests

**Run all custom-audio integration tests:**
```bash
pytest -m custom_audio -q
```

**With full per-test input/step/output logs:**
```bash
pytest -s -m custom_audio
```

**Only transcription tests, one per fixture file:**
```bash
pytest -s -v -m custom_audio -k transcribe_with_custom_audio_fixture
```

**Save transcription logs to file:**
```bash
pytest -s -m custom_audio -k transcribe_with_custom_audio_fixture | tee transcription_test_output.txt
```

**Run only unit tests (no Azure credentials needed):**
```bash
pytest -q -m "not integration"
```

**Run all 16 tests (unit + integration):**
```bash
pytest -v
```

---

## Test Results — 16/16 Pass

```
tests/test_custom_audio_integration.py::test_custom_audio_fixtures_exist                              PASSED
tests/test_custom_audio_integration.py::test_transcribe_with_custom_audio_fixture[asr_tts_test.mp3]           PASSED
tests/test_custom_audio_integration.py::test_transcribe_with_custom_audio_fixture[asr_tts_test_corrupted.mp3] PASSED  (→ 415)
tests/test_custom_audio_integration.py::test_transcribe_with_custom_audio_fixture[asr_tts_test_m4a.m4a]       PASSED
tests/test_custom_audio_integration.py::test_transcribe_with_custom_audio_fixture[asr_tts_test_ogg.opus]      PASSED
tests/test_custom_audio_integration.py::test_transcribe_with_custom_audio_fixture[asr_tts_test_wav.wav]       PASSED
tests/test_custom_audio_integration.py::test_process_with_first_custom_audio_fixture                          PASSED
```

`test_process_with_first_custom_audio_fixture` runs the full pipeline on `asr_tts_test.mp3`:
- Transcription → `"Hi we are testing Azure ASR and TTS services."` (confidence 0.599)
- Key phrases → `["Azure ASR", "TTS services"]`
- Sentiment → `neutral` (1.0 confidence)
- Named entities → `Azure ASR` (Product), `TTS` (Product)
- Linked entities → Microsoft Azure (Wikipedia)
- Summary → `"Your memo mentions 2 key topics: Azure ASR, TTS services. The overall tone is neutral. I detected entity types including 2 Product."`
- TTS audio → `en-US-JennyNeural`, `Audio16Khz32KBitRateMonoMp3`, 61 056 base64 chars

---

## Adding Your Own Files

1. Copy your audio file into this directory.
2. Use any of the accepted extensions above.
3. Re-run `pytest -m custom_audio` — the file is picked up automatically.
4. Expected status codes the tests accept: `200` (success), `415` (bad format), `422` (no speech detected).

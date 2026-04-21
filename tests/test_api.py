from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.schemas import TranscribeResponse, TranscriptionWord

client = TestClient(app)


def _log_case(test_name: str, step: str, data) -> None:
    print(f"[{test_name}] {step}: {data}")


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("sample.flac", "audio/flac"),
        ("sample.mp4", "video/mp4"),
        ("sample.mov", "video/quicktime"),
        ("sample.pdf", "application/pdf"),
    ],
)
def test_transcribe_rejects_unsupported_format(filename: str, content_type: str) -> None:
    test_name = "test_transcribe_rejects_unsupported_format"
    _log_case(test_name, "input", {"filename": filename, "content_type": content_type})
    _log_case(test_name, "step", "POST /transcribe")
    response = client.post(
        "/transcribe",
        files={"audio": (filename, b"fake", content_type)},
    )
    _log_case(test_name, "output", {"status_code": response.status_code, "body": response.json()})

    assert response.status_code == 415
    assert "Unsupported audio format" in response.json()["detail"]


def test_transcribe_success_shape(monkeypatch) -> None:
    test_name = "test_transcribe_success_shape"
    async def fake_save_upload(upload, suffix):
        return "/tmp/mock.wav"

    monkeypatch.setattr("app.main.save_upload_to_temp", fake_save_upload)
    monkeypatch.setattr("app.main.cleanup_temp_file", lambda path: None)
    monkeypatch.setattr(
        "app.main.transcribe_file_with_sdk",
        lambda path, **kwargs: TranscribeResponse(
            transcript="hello world",
            language="en-US",
            confidence=0.92,
            words=[
                TranscriptionWord(word="hello", confidence=0.98),
                TranscriptionWord(word="world", confidence=0.96),
            ],
        ),
    )

    _log_case(test_name, "input", {"filename": "sample.wav", "content_type": "audio/wav"})
    _log_case(test_name, "step", "POST /transcribe with mocked SDK result")
    response = client.post(
        "/transcribe",
        files={"audio": ("sample.wav", b"RIFF....", "audio/wav")},
    )

    assert response.status_code == 200
    payload = response.json()
    _log_case(test_name, "output", {"status_code": response.status_code, "body": payload})
    assert payload["transcript"] == "hello world"
    assert payload["language"] == "en-US"
    assert payload["confidence"] == 0.92
    assert payload["words"][0]["word"] == "hello"


def test_analyze_returns_all_sections(monkeypatch) -> None:
    test_name = "test_analyze_returns_all_sections"
    monkeypatch.setattr(
        "app.main.analyze_text",
        lambda text: {
            "key_phrases": ["project deadline"],
            "named_entities": [{"text": "Alice", "category": "Person"}],
            "sentiment": {"label": "neutral", "confidence": {"neutral": 0.9}},
            "linked_entities": [{"name": "Alice", "url": "https://example.com"}],
        },
    )

    _log_case(test_name, "input", {"text": "Alice discussed the project deadline."})
    _log_case(test_name, "step", "POST /analyze with mocked language service")
    response = client.post("/analyze", json={"text": "Alice discussed the project deadline."})

    assert response.status_code == 200
    payload = response.json()
    _log_case(test_name, "output", {"status_code": response.status_code, "body": payload})
    assert "key_phrases" in payload
    assert "named_entities" in payload
    assert "sentiment" in payload
    assert "linked_entities" in payload


def test_process_combined_pipeline(monkeypatch) -> None:
    test_name = "test_process_combined_pipeline"
    async def fake_save_upload(upload, suffix):
        return "/tmp/mock.mp3"

    monkeypatch.setattr("app.main.save_upload_to_temp", fake_save_upload)
    monkeypatch.setattr("app.main.cleanup_temp_file", lambda path: None)
    monkeypatch.setattr(
        "app.main.transcribe_file_with_sdk",
        lambda path, **kwargs: TranscribeResponse(
            transcript="Budget review with Alice.",
            language="en-US",
            confidence=0.95,
            words=[TranscriptionWord(word="Budget", confidence=0.97)],
        ),
    )
    monkeypatch.setattr(
        "app.main.analyze_text",
        lambda text: {
            "key_phrases": ["budget", "review"],
            "named_entities": [{"text": "Alice", "category": "Person"}],
            "sentiment": {"label": "positive", "confidence": {"positive": 0.88}},
            "linked_entities": [],
        },
    )
    monkeypatch.setattr(
        "app.main.build_summary_text",
        lambda analysis: "Summary here.",
    )
    monkeypatch.setattr(
        "app.main.synthesize_speech_base64",
        lambda text, voice: {
            "voice": voice,
            "format": "Audio16Khz32KBitRateMonoMp3",
            "audio_base64": "ZmFrZS1hdWRpbw==",
        },
    )

    _log_case(
        test_name,
        "input",
        {"filename": "sample.mp3", "content_type": "audio/mpeg", "voice": "en-US-JennyNeural"},
    )
    _log_case(test_name, "step", "POST /process with mocked pipeline services")
    response = client.post(
        "/process",
        files={"audio": ("sample.mp3", b"ID3fake", "audio/mpeg")},
        data={"voice": "en-US-JennyNeural"},
    )

    assert response.status_code == 200
    payload = response.json()
    _log_case(test_name, "output", {"status_code": response.status_code, "body": payload})
    assert payload["transcription"]["transcript"]
    assert payload["analysis"]["sentiment"]["label"] == "positive"
    assert payload["tts"]["format"] == "Audio16Khz32KBitRateMonoMp3"


def test_voices_has_three_or_more() -> None:
    test_name = "test_voices_has_three_or_more"
    _log_case(test_name, "step", "GET /voices")
    response = client.get("/voices")
    assert response.status_code == 200
    voices = response.json()["voices"]
    _log_case(test_name, "output", {"status_code": response.status_code, "voices": voices})
    assert len(voices) >= 3


def test_summary_audio_binary(monkeypatch) -> None:
    test_name = "test_summary_audio_binary"
    monkeypatch.setattr("app.main.synthesize_speech_bytes", lambda text, voice: (voice, b"fake-bytes"))

    _log_case(test_name, "input", {"text": "hello", "voice": "en-US-GuyNeural"})
    _log_case(test_name, "step", "GET /summary-audio")
    response = client.get("/summary-audio", params={"text": "hello", "voice": "en-US-GuyNeural"})

    _log_case(
        test_name,
        "output",
        {
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
            "bytes_len": len(response.content),
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.content == b"fake-bytes"

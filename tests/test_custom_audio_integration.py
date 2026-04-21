import mimetypes
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

AUDIO_DIR = Path(__file__).parent / "fixtures" / "audio"
SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".opus", ".aac", ".m4a"}

client = TestClient(app)


def _log_case(test_name: str, step: str, data) -> None:
    print(f"[{test_name}] {step}: {data}")


def _has_azure_env() -> bool:
    required = [
        "AZURE_SPEECH_KEY",
        "AZURE_SPEECH_REGION",
        "AZURE_LANGUAGE_KEY",
        "AZURE_LANGUAGE_ENDPOINT",
    ]
    return all(os.getenv(name) for name in required)


def _audio_files() -> list[Path]:
    if not AUDIO_DIR.exists():
        return []
    files = [
        path
        for path in AUDIO_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(files)


CUSTOM_AUDIO_FILES = _audio_files()


@pytest.mark.integration
@pytest.mark.custom_audio
@pytest.mark.skipif(not _has_azure_env(), reason="Azure environment variables are not fully configured")
def test_custom_audio_fixtures_exist() -> None:
    test_name = "test_custom_audio_fixtures_exist"
    _log_case(test_name, "step", "List fixture files")
    _log_case(test_name, "output", [path.name for path in CUSTOM_AUDIO_FILES])
    assert CUSTOM_AUDIO_FILES, (
        "No custom audio files found. Add audio files under tests/fixtures/audio/ "
        "with .wav/.mp3/.ogg/.opus/.aac/.m4a extension."
    )


@pytest.mark.integration
@pytest.mark.custom_audio
@pytest.mark.skipif(not _has_azure_env(), reason="Azure environment variables are not fully configured")
@pytest.mark.parametrize("audio_path", CUSTOM_AUDIO_FILES, ids=lambda p: p.name)
def test_transcribe_with_custom_audio_fixture(audio_path: Path) -> None:
    test_name = "test_transcribe_with_custom_audio_fixture"
    guessed_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
    _log_case(
        test_name,
        "input",
        {"filename": audio_path.name, "content_type": guessed_type, "path": str(audio_path)},
    )
    _log_case(test_name, "step", "POST /transcribe")

    with audio_path.open("rb") as file_obj:
        response = client.post(
            "/transcribe",
            files={"audio": (audio_path.name, file_obj, guessed_type)},
        )

    assert response.status_code in {200, 415, 422}, response.text
    payload = response.json()
    _log_case(test_name, "output", {"status_code": response.status_code, "body": payload})
    if response.status_code == 200:
        assert isinstance(payload.get("transcript"), str)
        assert payload["transcript"].strip()
        assert "language" in payload
        assert "confidence" in payload
        assert "words" in payload
    else:
        assert "detail" in payload
        assert (
            "Unsupported or invalid audio media format" in payload["detail"]
            or "No recognizable speech" in payload["detail"]
        )


@pytest.mark.integration
@pytest.mark.custom_audio
@pytest.mark.skipif(not _has_azure_env(), reason="Azure environment variables are not fully configured")
def test_process_with_first_custom_audio_fixture() -> None:
    test_name = "test_process_with_first_custom_audio_fixture"
    if not CUSTOM_AUDIO_FILES:
        pytest.skip("No custom audio fixtures available")

    first_audio = CUSTOM_AUDIO_FILES[0]
    guessed_type = mimetypes.guess_type(first_audio.name)[0] or "application/octet-stream"
    _log_case(
        test_name,
        "input",
        {
            "filename": first_audio.name,
            "content_type": guessed_type,
            "voice": "en-US-JennyNeural",
            "path": str(first_audio),
        },
    )
    _log_case(test_name, "step", "POST /process")

    with first_audio.open("rb") as file_obj:
        response = client.post(
            "/process",
            files={"audio": (first_audio.name, file_obj, guessed_type)},
            data={"voice": "en-US-JennyNeural"},
        )

    assert response.status_code in {200, 415, 422}, response.text
    payload = response.json()
    _log_case(test_name, "output", {"status_code": response.status_code, "body": payload})
    if response.status_code == 200:
        assert payload["transcription"]["transcript"].strip()
        assert payload["analysis"]["sentiment"]["label"] in {"positive", "neutral", "negative", "mixed"}
        assert payload["tts"]["format"] == "Audio16Khz32KBitRateMonoMp3"
        assert payload["tts"]["audio_base64"]
    else:
        assert "detail" in payload

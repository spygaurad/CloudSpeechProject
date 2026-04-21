import os
import tempfile
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import ALL_ACCEPTED_AUDIO_EXTENSIONS, MAX_UPLOAD_BYTES, PARTIAL_SUPPORTED_AUDIO_EXTENSIONS


class AudioValidationResult:
    def __init__(self, suffix: str, partial_support: bool):
        self.suffix = suffix
        self.partial_support = partial_support


def validate_audio_file(upload: UploadFile) -> AudioValidationResult:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALL_ACCEPTED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported audio format '{suffix or 'unknown'}'. Supported formats: "
                "WAV, MP3, OGG/Opus. Partial support: AAC/M4A (may require conversion)."
            ),
        )

    return AudioValidationResult(suffix=suffix, partial_support=suffix in PARTIAL_SUPPORTED_AUDIO_EXTENSIONS)


async def save_upload_to_temp(upload: UploadFile, suffix: str) -> str:
    temp_name = f"upload-{uuid.uuid4().hex}{suffix}"
    temp_path = os.path.join(tempfile.gettempdir(), temp_name)
    total_bytes = 0

    with open(temp_path, "wb") as output:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_BYTES:
                try:
                    output.close()
                    os.remove(temp_path)
                except OSError:
                    pass
                raise HTTPException(status_code=413, detail="File exceeds 25MB limit.")
            output.write(chunk)

    await upload.close()
    return temp_path


def cleanup_temp_file(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass

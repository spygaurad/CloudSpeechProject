import os

from dotenv import load_dotenv

load_dotenv()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
DEFAULT_LANGUAGE = "en-US"
DEFAULT_TTS_VOICE = "en-US-JennyNeural"
SUPPORTED_TTS_VOICES = {
    "en-US-JennyNeural": "formal",
    "en-US-GuyNeural": "casual",
    "en-US-AriaNeural": "energetic",
}

FULLY_SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".opus"}
PARTIAL_SUPPORTED_AUDIO_EXTENSIONS = {".aac", ".m4a"}
ALL_ACCEPTED_AUDIO_EXTENSIONS = (
    FULLY_SUPPORTED_AUDIO_EXTENSIONS | PARTIAL_SUPPORTED_AUDIO_EXTENSIONS
)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value

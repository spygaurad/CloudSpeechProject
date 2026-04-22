import os

from dotenv import load_dotenv

load_dotenv()

PORT = int(os.getenv("WEBSITES_PORT", "8000"))
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
DEFAULT_LANGUAGE = "en-US"
RETRY_LANGUAGE = "en-GB"
LOW_WORD_CONFIDENCE_THRESHOLD = 0.70   # flag individual words below this
RETRY_CONFIDENCE_THRESHOLD = 0.85      # re-submit transcript if overall below this
STATS_DB_PATH = os.getenv("STATS_DB_PATH", "transcription_stats.db")
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

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1)


class TranscriptionWord(BaseModel):
    word: str
    confidence: float | None = None


class TranscribeResponse(BaseModel):
    transcript: str
    language: str
    confidence: float | None = None
    words: list[TranscriptionWord]
    low_confidence_words: list[str] = []   # word texts with confidence < threshold
    retry_attempted: bool = False


class VoiceInfo(BaseModel):
    name: str
    persona: str


class TTSPayload(BaseModel):
    voice: str
    format: str
    audio_base64: str


class ProcessResponse(BaseModel):
    transcription: TranscribeResponse
    analysis: dict
    summary_text: str
    tts: TTSPayload

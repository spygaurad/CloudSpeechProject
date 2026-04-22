import gradio as gr
import uvicorn
from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.responses import RedirectResponse, Response

from app.config import DEFAULT_TTS_VOICE, PORT
from app.gradio_app import gradio_app
from app.schemas import AnalyzeRequest, ProcessResponse, TranscribeResponse
from app.services.audio_service import cleanup_temp_file, save_upload_to_temp, validate_audio_file
from app.services.language_service import analyze_text
from app.services.summary_service import build_summary_text
from app.services.stats_service import get_stats, log_transcription  # noqa: F401 (init_db runs on import)
from app.services.transcription_service import transcribe_file_with_sdk, transcribe_with_confidence_retry
from app.services.tts_service import get_voices, synthesize_speech_base64, synthesize_speech_bytes

app = FastAPI(title="Cloud Speech Project API", version="1.0.0")

# Mount the Gradio UI at /ui  (visit http://localhost:8000/ui in your browser)
app = gr.mount_gradio_app(app, gradio_app, path="/ui")


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(audio: UploadFile = File(...)) -> TranscribeResponse:
    validation = validate_audio_file(audio)
    temp_path = await save_upload_to_temp(audio, validation.suffix)

    try:
        return transcribe_file_with_sdk(temp_path, content_type=audio.content_type)
    finally:
        cleanup_temp_file(temp_path)


@app.post("/analyze")
def analyze(payload: AnalyzeRequest) -> dict:
    return analyze_text(payload.text)


@app.post("/process", response_model=ProcessResponse)
async def process(
    audio: UploadFile = File(...),
    voice: str = Form(DEFAULT_TTS_VOICE),
) -> ProcessResponse:
    validation = validate_audio_file(audio)
    temp_path = await save_upload_to_temp(audio, validation.suffix)

    try:
        transcription, retry_attempted, retry_language = transcribe_with_confidence_retry(
            temp_path, content_type=audio.content_type
        )
        log_transcription(
            language=transcription.language,
            overall_confidence=transcription.confidence,
            total_words=len(transcription.words),
            low_confidence_words=len(transcription.low_confidence_words),
            retry_attempted=retry_attempted,
            retry_language=retry_language,
            final_confidence=transcription.confidence if retry_attempted else None,
        )
        analysis = analyze_text(transcription.transcript)
        summary = build_summary_text(analysis)
        tts_payload = synthesize_speech_base64(summary, voice)

        if validation.partial_support:
            analysis["audio_format_note"] = (
                "AAC/M4A is partially supported by Azure Speech. "
                "If recognition quality is low, pre-convert to WAV PCM 16kHz/16-bit/mono."
            )

        return ProcessResponse(
            transcription=transcription,
            analysis=analysis,
            summary_text=summary,
            tts=tts_payload,
        )
    finally:
        cleanup_temp_file(temp_path)


@app.get("/stats")
def stats() -> dict:
    return get_stats()


@app.get("/voices")
def voices() -> dict:
    return {"voices": get_voices()}


@app.get("/summary-audio")
def summary_audio(
    text: str = Query(..., min_length=1),
    voice: str = Query(DEFAULT_TTS_VOICE),
) -> Response:
    _, audio_bytes = synthesize_speech_bytes(text=text, voice=voice)
    return Response(content=audio_bytes, media_type="audio/mpeg")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT)

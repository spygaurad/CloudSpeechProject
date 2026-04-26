# Application Insights MUST be initialized before any Azure SDK imports
from dotenv import load_dotenv
load_dotenv()  # load .env before everything else

from telemetry import init_telemetry
init_telemetry()  # initialize before FastAPI or any Azure SDK imports

import uvicorn
from pathlib import Path
from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response

from app.config import DEFAULT_TTS_VOICE, PORT
from app.schemas import AnalyzeRequest, ProcessResponse, TranscribeResponse
from app.services.audio_service import cleanup_temp_file, save_upload_to_temp, validate_audio_file
from app.services.language_service import analyze_text
from app.services.summary_service import build_summary_text
from app.metrics import emit_pipeline_event, emit_pipeline_metrics, timed_stage, tracer
from app.services.stats_service import get_stats, log_transcription  # noqa: F401 (init_db runs on import)
from app.services.transcription_service import transcribe_file_with_sdk, transcribe_with_confidence_retry
from app.services.tts_service import get_voices, synthesize_speech_base64, synthesize_speech_bytes

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Cloud Speech Project API", version="1.0.0")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


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
        with tracer.start_as_current_span("pipeline.process") as root_span:
            root_span.set_attribute("audio.format", validation.suffix)

            current_stage: str | None = None
            try:
                # --- Stage 1: Speech-to-Text ---
                current_stage = "stt"
                with tracer.start_as_current_span("stage.speech_to_text") as stt_span:
                    (transcription, retry_attempted, retry_language), stt_ms = timed_stage(
                        transcribe_with_confidence_retry, temp_path, content_type=audio.content_type
                    )
                    stt_span.set_attribute("stt.confidence", transcription.confidence or 0.0)
                    stt_span.set_attribute("stt.word_count", len(transcription.transcript.split()))
                    stt_span.set_attribute("stt.language", transcription.language)
                    stt_span.set_attribute("duration_ms", stt_ms)

                log_transcription(
                    language=transcription.language,
                    overall_confidence=transcription.confidence,
                    total_words=len(transcription.words),
                    low_confidence_words=len(transcription.low_confidence_words),
                    retry_attempted=retry_attempted,
                    retry_language=retry_language,
                    final_confidence=transcription.confidence if retry_attempted else None,
                )

                # --- Stage 2: Language Analysis ---
                current_stage = "language"
                with tracer.start_as_current_span("stage.language_analysis") as lang_span:
                    analysis, language_ms = timed_stage(analyze_text, transcription.transcript)
                    lang_span.set_attribute("entity_count", len(analysis.get("named_entities", [])))
                    lang_span.set_attribute("keyphrase_count", len(analysis.get("key_phrases", [])))
                    lang_span.set_attribute(
                        "sentiment", analysis.get("sentiment", {}).get("label", "neutral")
                    )
                    lang_span.set_attribute("duration_ms", language_ms)

                summary = build_summary_text(analysis)

                # --- Stage 3: Text-to-Speech ---
                current_stage = "tts"
                with tracer.start_as_current_span("stage.text_to_speech") as tts_span:
                    tts_payload, tts_ms = timed_stage(synthesize_speech_base64, summary, voice)
                    tts_span.set_attribute("char_count", len(summary))
                    tts_span.set_attribute("tts.voice", voice)
                    tts_span.set_attribute("duration_ms", tts_ms)

                emit_pipeline_metrics(
                    stt_result=transcription,
                    language_result=analysis,
                    tts_char_count=len(summary),
                    stage_timings={"stt_ms": stt_ms, "language_ms": language_ms, "tts_ms": tts_ms},
                    audio_format=validation.suffix,
                )
                emit_pipeline_event(
                    audio_format=validation.suffix,
                    success=True,
                    stt_result=transcription,
                    lang_result=analysis,
                )

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

            except Exception as exc:
                # Annotate the root span before it closes, then re-raise
                emit_pipeline_event(
                    audio_format=validation.suffix,
                    success=False,
                    error_stage=current_stage,
                    error_msg=str(exc),
                )
                raise

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

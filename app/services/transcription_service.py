import json
import os
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

import azure.cognitiveservices.speech as speechsdk
from fastapi import HTTPException

from app.config import (
    DEFAULT_LANGUAGE,
    LOW_WORD_CONFIDENCE_THRESHOLD,
    RETRY_CONFIDENCE_THRESHOLD,
    RETRY_LANGUAGE,
    require_env,
)
from app.schemas import TranscribeResponse, TranscriptionWord


class UnsupportedAudioMediaError(Exception):
    pass


def _sdk_media_type_error() -> HTTPException:
    return HTTPException(
        status_code=415,
        detail=(
            "Unsupported audio format. "
            "Accepted formats: WAV (PCM), MP3, OGG/Opus, AAC/M4A."
        ),
    )


def _corrupt_audio_error() -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=(
            "The uploaded audio file could not be decoded. "
            "It appears to be corrupted, truncated, or not a valid audio file. "
            "Please verify the file and try again."
        ),
    )


def _server_error(message: str) -> HTTPException:
    return HTTPException(status_code=500, detail=message)


def _is_media_runtime_error(exc: RuntimeError) -> bool:
    detail = str(exc).lower()
    return (
        "audio" in detail
        and (
            "format" in detail
            or "codec" in detail
            or "header" in detail
            or "unsupported" in detail
        )
    )


# Keywords in Azure Speech SDK cancellation messages that indicate the file is
# corrupted or invalid rather than simply an unsupported format.
_CORRUPTION_KEYWORDS = frozenset({
    "corrupt", "damaged", "truncat", "unexpected end",
    "invalid data", "no audio", "empty", "decod",
})


def _is_corruption_error(detail: str) -> bool:
    lower = detail.lower()
    return any(kw in lower for kw in _CORRUPTION_KEYWORDS)


def _ffmpeg_convert_to_wav(input_path: str) -> str | None:
    """Convert any audio file to 16 kHz / 16-bit / mono PCM WAV using ffmpeg.

    Returns the path of the new WAV file on success, or None if ffmpeg is not
    installed (caller should fall back to the SDK compressed-stream path).

    Raises:
        HTTPException(422): ffmpeg is installed but failed to decode the file —
            the file is corrupted, truncated, or not a valid audio file.
    """
    out_path = os.path.join(tempfile.gettempdir(), f"converted-{uuid.uuid4().hex}.wav")
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", input_path,
                "-ar", "16000",
                "-ac", "1",
                "-acodec", "pcm_s16le",
                out_path,
            ],
            capture_output=True,
            timeout=60,
        )
    except FileNotFoundError:
        # ffmpeg is not installed — caller falls back to SDK compressed stream.
        return None
    except (subprocess.TimeoutExpired, OSError):
        try:
            os.remove(out_path)
        except OSError:
            pass
        return None

    if result.returncode == 0 and Path(out_path).stat().st_size > 0:
        return out_path

    # ffmpeg ran but returned a non-zero exit code: the file cannot be decoded.
    # This means it is corrupted, truncated, or masquerading as a supported format.
    try:
        os.remove(out_path)
    except OSError:
        pass
    raise _corrupt_audio_error()


def _resolve_container_format(
    suffix: str,
    content_type: str | None,
) -> speechsdk.audio.AudioStreamContainerFormat | None:
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()

    # WAV stays on file-based AudioConfig for reliable PCM autodetection.
    if suffix == ".wav" or normalized_type in {"audio/wav", "audio/x-wav", "audio/wave"}:
        return None

    mime_map = {
        "audio/mpeg": speechsdk.audio.AudioStreamContainerFormat.MP3,
        "audio/mp3": speechsdk.audio.AudioStreamContainerFormat.MP3,
        "audio/ogg": speechsdk.audio.AudioStreamContainerFormat.OGG_OPUS,
        "audio/opus": speechsdk.audio.AudioStreamContainerFormat.OGG_OPUS,
        "application/ogg": speechsdk.audio.AudioStreamContainerFormat.OGG_OPUS,
        "audio/aac": speechsdk.audio.AudioStreamContainerFormat.ANY,
        "audio/mp4": speechsdk.audio.AudioStreamContainerFormat.ANY,
        "audio/mp4a-latm": speechsdk.audio.AudioStreamContainerFormat.ANY,
        "audio/x-m4a": speechsdk.audio.AudioStreamContainerFormat.ANY,
    }
    if normalized_type in mime_map:
        return mime_map[normalized_type]

    extension_map = {
        ".mp3": speechsdk.audio.AudioStreamContainerFormat.MP3,
        ".ogg": speechsdk.audio.AudioStreamContainerFormat.OGG_OPUS,
        ".opus": speechsdk.audio.AudioStreamContainerFormat.OGG_OPUS,
        ".aac": speechsdk.audio.AudioStreamContainerFormat.ANY,
        ".m4a": speechsdk.audio.AudioStreamContainerFormat.ANY,
    }
    if suffix in extension_map:
        return extension_map[suffix]

    raise UnsupportedAudioMediaError()


def _create_audio_config(
    file_path: str,
    content_type: str | None,
) -> tuple[speechsdk.audio.AudioConfig, Any | None]:
    suffix = Path(file_path).suffix.lower()

    container = _resolve_container_format(suffix=suffix, content_type=content_type)
    if container is None:
        return speechsdk.audio.AudioConfig(filename=file_path), None

    try:
        compressed_format = speechsdk.audio.AudioStreamFormat(compressed_stream_format=container)
        push_stream = speechsdk.audio.PushAudioInputStream(stream_format=compressed_format)
        with open(file_path, "rb") as audio_file:
            push_stream.write(audio_file.read())
        # Keep stream open until recognition finishes.
        return speechsdk.audio.AudioConfig(stream=push_stream), push_stream
    except RuntimeError as exc:
        raise UnsupportedAudioMediaError() from exc


class _RecognitionAccumulator:
    def __init__(self, default_language: str):
        self.transcript_chunks: list[str] = []
        self.word_entries: list[TranscriptionWord] = []
        self.segment_confidences: list[float] = []
        self.language = default_language

    def add_from_result_json(self, result_json: str, fallback_text: str | None = None) -> None:
        payload = json.loads(result_json)
        nbest = payload.get("NBest") or []
        if not nbest:
            if fallback_text:
                self.transcript_chunks.append(fallback_text)
            return

        top = nbest[0]
        display = top.get("Display") or payload.get("DisplayText") or fallback_text
        if display:
            self.transcript_chunks.append(display)

        lang = payload.get("PrimaryLanguage", {}).get("Language")
        if lang:
            self.language = lang

        segment_confidence = top.get("Confidence")
        if isinstance(segment_confidence, (int, float)):
            self.segment_confidences.append(float(segment_confidence))

        for item in top.get("Words", []):
            self.word_entries.append(
                TranscriptionWord(
                    word=item.get("Word", ""),
                    confidence=item.get("Confidence"),
                )
            )

    def build_response(self) -> TranscribeResponse:
        transcript = " ".join(piece.strip() for piece in self.transcript_chunks if piece.strip()).strip()
        if not transcript:
            raise HTTPException(status_code=422, detail="No recognizable speech found in audio.")

        overall_confidence = None
        if self.segment_confidences:
            overall_confidence = sum(self.segment_confidences) / len(self.segment_confidences)
        elif self.word_entries:
            scored = [w.confidence for w in self.word_entries if isinstance(w.confidence, (float, int))]
            if scored:
                overall_confidence = sum(float(v) for v in scored) / len(scored)

        return TranscribeResponse(
            transcript=transcript,
            language=self.language,
            confidence=overall_confidence,
            words=self.word_entries,
        )


def _run_recognition(
    speech_config: speechsdk.SpeechConfig,
    audio_path: str,
    content_type: str | None,
    language: str,
) -> TranscribeResponse:
    """Build an audio config, create a recognizer, and run continuous recognition."""
    _stream_handle = None
    try:
        audio_config, _stream_handle = _create_audio_config(audio_path, content_type=content_type)
    except UnsupportedAudioMediaError as exc:
        raise _sdk_media_type_error() from exc
    except RuntimeError as exc:
        if _is_corruption_error(str(exc)):
            raise _corrupt_audio_error() from exc
        raise _sdk_media_type_error() from exc

    is_compressed = _stream_handle is not None
    try:
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )
    except RuntimeError as exc:
        if is_compressed or _is_media_runtime_error(exc):
            raise _sdk_media_type_error() from exc
        raise _server_error("Failed to initialize Azure Speech recognizer.") from exc

    done_event = threading.Event()
    collector = _RecognitionAccumulator(default_language=language)
    recognition_error: dict[str, str] = {}

    def recognized(event: Any) -> None:
        if event.result.reason != speechsdk.ResultReason.RecognizedSpeech:
            return
        try:
            collector.add_from_result_json(event.result.json, fallback_text=event.result.text)
        except (json.JSONDecodeError, KeyError, TypeError):
            if event.result.text:
                collector.transcript_chunks.append(event.result.text)

    def stop_callback(event: Any) -> None:
        if getattr(event, "reason", None) == speechsdk.CancellationReason.Error:
            details = (getattr(event, "error_details", None) or "").strip()
            if details:
                recognition_error["detail"] = details
        done_event.set()

    recognizer.recognized.connect(recognized)
    recognizer.session_stopped.connect(stop_callback)
    recognizer.canceled.connect(stop_callback)

    try:
        recognizer.start_continuous_recognition()
    except RuntimeError as exc:
        raise _server_error("Azure Speech recognition failed to start.") from exc

    done_event.wait()
    recognizer.stop_continuous_recognition()
    if _stream_handle is not None:
        _stream_handle.close()

    if recognition_error:
        detail = recognition_error["detail"]
        detail_lower = detail.lower()
        # Check corruption first — a corrupted file of a supported type should
        # return 422 (Unprocessable Entity), not 415 (Unsupported Media Type).
        if _is_corruption_error(detail_lower):
            raise _corrupt_audio_error()
        if "audio" in detail_lower and (
            "format" in detail_lower
            or "header" in detail_lower
            or "codec" in detail_lower
            or "unsupported" in detail_lower
        ):
            raise _sdk_media_type_error()
        raise _server_error(f"Azure Speech recognition canceled: {detail}")

    return collector.build_response()


def transcribe_file_with_sdk(
    file_path: str,
    language: str = DEFAULT_LANGUAGE,
    content_type: str | None = None,
) -> TranscribeResponse:
    try:
        speech_key = require_env("AZURE_SPEECH_KEY")
        speech_region = require_env("AZURE_SPEECH_REGION")
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_recognition_language = language
    speech_config.request_word_level_timestamps()
    speech_config.output_format = speechsdk.OutputFormat.Detailed

    suffix = Path(file_path).suffix.lower()
    is_wav = suffix == ".wav" or (content_type or "").lower() in {
        "audio/wav", "audio/x-wav", "audio/wave"
    }

    # For WAV, go directly to the SDK — no conversion needed.
    if is_wav:
        return _run_recognition(speech_config, file_path, content_type, language)

    # For all other formats, first attempt an ffmpeg → WAV conversion so that
    # the SDK can use its reliable PCM path regardless of GStreamer availability.
    converted_path = _ffmpeg_convert_to_wav(file_path)
    if converted_path is not None:
        try:
            return _run_recognition(speech_config, converted_path, "audio/wav", language)
        finally:
            try:
                os.remove(converted_path)
            except OSError:
                pass

    # ffmpeg unavailable or conversion failed — fall back to SDK compressed stream.
    return _run_recognition(speech_config, file_path, content_type, language)


def _flag_low_confidence_words(result: TranscribeResponse) -> TranscribeResponse:
    """Annotate result.low_confidence_words with texts below threshold."""
    flagged = [
        w.word
        for w in result.words
        if isinstance(w.confidence, float) and w.confidence < LOW_WORD_CONFIDENCE_THRESHOLD
    ]
    return result.model_copy(update={"low_confidence_words": flagged})


def transcribe_with_confidence_retry(
    file_path: str,
    content_type: str | None = None,
) -> tuple[TranscribeResponse, bool, str | None]:
    """
    Run transcription with automatic confidence-based retry.

    Returns:
        (best_result, retry_attempted, retry_language_used)
    """
    first = transcribe_file_with_sdk(file_path, language=DEFAULT_LANGUAGE, content_type=content_type)
    first = _flag_low_confidence_words(first)

    retry_attempted = False
    retry_language: str | None = None

    if first.confidence is not None and first.confidence < RETRY_CONFIDENCE_THRESHOLD:
        retry_attempted = True
        retry_language = RETRY_LANGUAGE
        second = transcribe_file_with_sdk(file_path, language=RETRY_LANGUAGE, content_type=content_type)
        second = _flag_low_confidence_words(second)

        # Keep whichever attempt scored higher
        first_conf = first.confidence or 0.0
        second_conf = second.confidence or 0.0
        best = second if second_conf > first_conf else first
        best = best.model_copy(update={"retry_attempted": True})
        return best, retry_attempted, retry_language

    return first, retry_attempted, retry_language

import json
import threading
from typing import Any

import azure.cognitiveservices.speech as speechsdk
from fastapi import HTTPException

from app.config import DEFAULT_LANGUAGE, require_env
from app.schemas import TranscribeResponse, TranscriptionWord


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


def transcribe_file_with_sdk(file_path: str, language: str = DEFAULT_LANGUAGE) -> TranscribeResponse:
    try:
        speech_key = require_env("AZURE_SPEECH_KEY")
        speech_region = require_env("AZURE_SPEECH_REGION")
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_recognition_language = language
    speech_config.request_word_level_timestamps()
    speech_config.output_format = speechsdk.OutputFormat.Detailed

    recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=speechsdk.audio.AudioConfig(filename=file_path),
    )

    done_event = threading.Event()
    collector = _RecognitionAccumulator(default_language=language)

    def recognized(event: Any) -> None:
        if event.result.reason != speechsdk.ResultReason.RecognizedSpeech:
            return
        try:
            collector.add_from_result_json(event.result.json, fallback_text=event.result.text)
        except (json.JSONDecodeError, KeyError, TypeError):
            if event.result.text:
                collector.transcript_chunks.append(event.result.text)

    def stop_callback(event: Any) -> None:
        done_event.set()

    recognizer.recognized.connect(recognized)
    recognizer.session_stopped.connect(stop_callback)
    recognizer.canceled.connect(stop_callback)

    recognizer.start_continuous_recognition()
    done_event.wait()
    recognizer.stop_continuous_recognition()

    return collector.build_response()

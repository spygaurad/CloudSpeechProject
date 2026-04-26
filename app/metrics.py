"""Custom OpenTelemetry metrics and trace events for every pipeline stage.

Import this module AFTER init_telemetry() has been called so that the
Azure Monitor exporter is already registered with the metrics and trace SDKs.
"""

import time
from typing import Any, Callable, TypeVar

from opentelemetry import metrics, trace

from app.schemas import TranscribeResponse

_T = TypeVar("_T")

# ---------------------------------------------------------------------------
# Meter and tracer — one per service, created once at import time
# ---------------------------------------------------------------------------
meter = metrics.get_meter("memo-analyzer")
tracer = trace.get_tracer("memo-analyzer")

# ---------------------------------------------------------------------------
# Metric instruments — module-level singletons
# ---------------------------------------------------------------------------

# STT
stt_confidence_gauge = meter.create_gauge("stt_confidence")
stt_duration_gauge = meter.create_gauge("stt_duration_seconds")
stt_word_count_gauge = meter.create_gauge("stt_word_count")

# Language Analysis
entity_count_gauge = meter.create_gauge("language_entity_count")
keyphrase_count_gauge = meter.create_gauge("language_keyphrase_count")
sentiment_gauge = meter.create_gauge("language_sentiment")

# TTS
tts_char_count_gauge = meter.create_gauge("tts_char_count")

# Per-stage wall-clock latency (histograms give percentile data in Azure Monitor)
stage_stt_hist = meter.create_histogram("stage_stt_ms")
stage_language_hist = meter.create_histogram("stage_language_ms")
stage_tts_hist = meter.create_histogram("stage_tts_ms")

# Metrics as histograms (for guaranteed export to customMetrics)
stt_confidence_hist = meter.create_histogram("stt_confidence")
entity_count_hist = meter.create_histogram("entity_count")
keyphrase_count_hist = meter.create_histogram("keyphrase_count")
sentiment_hist = meter.create_histogram("sentiment")
tts_char_count_hist = meter.create_histogram("tts_char_count")
stt_word_count_hist = meter.create_histogram("stt_word_count")

# ---------------------------------------------------------------------------
# Sentiment mapping
# ---------------------------------------------------------------------------
_SENTIMENT_MAP: dict[str, float] = {
    "positive": 1.0,
    "neutral": 0.0,
    "negative": -1.0,
}


# ---------------------------------------------------------------------------
# Emit function — call once at the end of every successful /process request
# ---------------------------------------------------------------------------
def emit_pipeline_metrics(
    stt_result: dict,
    language_result: dict,
    tts_result: dict,
    stage_timings: dict[str, float],
    audio_format: str,
) -> None:
    """Call this at the end of /process after all three stages complete.

    Args:
        stt_result:      dict with keys: confidence, duration_seconds, transcript, language
        language_result: dict with keys: entities, key_phrases, sentiment
        tts_result:      dict with key: char_count
        stage_timings:   {"stt_ms": float, "language_ms": float, "tts_ms": float}
        audio_format:    File extension of the uploaded audio (e.g. ".wav").
    """
    attrs: dict[str, str] = {
        "audio_format": audio_format,
        "language": stt_result["language"],
    }

    # --- STT metrics (gauges + histograms) ---
    confidence = stt_result["confidence"]
    stt_confidence_gauge.set(confidence, attrs)
    stt_confidence_hist.record(confidence, attrs)  # Also record as histogram for reliable export
    stt_duration_gauge.set(stt_result["duration_seconds"], attrs)
    word_count = len(stt_result["transcript"].split())
    stt_word_count_gauge.set(word_count, attrs)
    stt_word_count_hist.record(word_count, attrs)

    # --- Language metrics (gauges + histograms) ---
    entity_count = len(language_result["entities"])
    entity_count_gauge.set(entity_count, attrs)
    entity_count_hist.record(entity_count, attrs)

    keyphrase_count = len(language_result["key_phrases"])
    keyphrase_count_gauge.set(keyphrase_count, attrs)
    keyphrase_count_hist.record(keyphrase_count, attrs)

    sentiment_label = language_result["sentiment"]["label"]
    sentiment_value = _SENTIMENT_MAP.get(sentiment_label, 0.0)
    sentiment_gauge.set(sentiment_value, attrs)
    sentiment_hist.record(sentiment_value, attrs)

    # --- TTS metrics (gauges + histograms) ---
    char_count = tts_result["char_count"]
    tts_char_count_gauge.set(char_count, attrs)
    tts_char_count_hist.record(char_count, attrs)

    # --- Per-stage latency histograms (these always export) ---
    stage_stt_hist.record(stage_timings["stt_ms"], attrs)
    stage_language_hist.record(stage_timings["language_ms"], attrs)
    stage_tts_hist.record(stage_timings["tts_ms"], attrs)


# ---------------------------------------------------------------------------
# Timing utility
# ---------------------------------------------------------------------------

def timed_stage(fn: Callable[..., _T], *args: Any, **kwargs: Any) -> tuple[_T, float]:
    """Run fn(*args, **kwargs) and return (result, elapsed_ms)."""
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return result, elapsed_ms


# ---------------------------------------------------------------------------
# Pipeline trace events
# ---------------------------------------------------------------------------

def emit_pipeline_event(
    audio_format: str,
    success: bool,
    stt_result: TranscribeResponse | None = None,
    lang_result: dict | None = None,
    error_stage: str | None = None,
    error_msg: str | None = None,
) -> None:
    """Set span attributes on the active span for pipeline_completed / pipeline_error.

    Call once per /process request — after emit_pipeline_metrics on success,
    or inside the except block on failure.
    """
    span = trace.get_current_span()

    if success and stt_result is not None and lang_result is not None:
        span.set_attribute("event.name", "pipeline_completed")
        span.set_attribute("audio.format", audio_format)
        span.set_attribute("stt.confidence", stt_result.confidence or 0.0)
        span.set_attribute("stt.language", stt_result.language)
        span.set_attribute("entities.count", len(lang_result.get("named_entities", [])))
        span.set_attribute("sentiment", lang_result.get("sentiment", {}).get("label", "neutral"))
    else:
        span.set_attribute("event.name", "pipeline_error")
        span.set_attribute("audio.format", audio_format)
        if error_stage:
            span.set_attribute("error.stage", error_stage)
        if error_msg:
            span.set_attribute("error.message", error_msg)
            span.record_exception(Exception(error_msg))

"""Custom OpenTelemetry metrics for every pipeline stage.

Import this module AFTER init_telemetry() has been called so that the
Azure Monitor exporter is already registered with the metrics SDK.
"""

from opentelemetry import metrics

from app.schemas import TranscribeResponse

# ---------------------------------------------------------------------------
# Meter — one per service, created once at import time
# ---------------------------------------------------------------------------
meter = metrics.get_meter("memo-analyzer")

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
    stt_result: TranscribeResponse,
    language_result: dict,
    tts_char_count: int,
    stage_timings: dict[str, float],
    audio_format: str,
) -> None:
    """Emit custom metrics for all three pipeline stages.

    Args:
        stt_result:      TranscribeResponse returned by the STT stage.
        language_result: dict returned by analyze_text().
        tts_char_count:  Number of characters synthesized by TTS (len of summary text).
        stage_timings:   {"stt_ms": float, "language_ms": float, "tts_ms": float}
        audio_format:    File extension of the uploaded audio (e.g. ".wav").
    """
    attrs: dict[str, str] = {
        "audio_format": audio_format,
        "language": stt_result.language,
    }

    # --- STT metrics ---
    stt_confidence_gauge.set(stt_result.confidence or 0.0, attrs)
    # duration_seconds: the Azure Speech SDK does not surface clip duration in the
    # current TranscribeResponse schema; emitted as 0.0 until the schema is extended.
    stt_duration_gauge.set(0.0, attrs)
    stt_word_count_gauge.set(len(stt_result.transcript.split()), attrs)

    # --- Language metrics ---
    entity_count_gauge.set(len(language_result.get("named_entities", [])), attrs)
    keyphrase_count_gauge.set(len(language_result.get("key_phrases", [])), attrs)
    sentiment_label = language_result.get("sentiment", {}).get("label", "neutral")
    sentiment_gauge.set(_SENTIMENT_MAP.get(sentiment_label, 0.0), attrs)

    # --- TTS metrics ---
    tts_char_count_gauge.set(tts_char_count, attrs)

    # --- Per-stage latency histograms ---
    stage_stt_hist.record(stage_timings["stt_ms"], attrs)
    stage_language_hist.record(stage_timings["language_ms"], attrs)
    stage_tts_hist.record(stage_timings["tts_ms"], attrs)

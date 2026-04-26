"""In-memory session log for pipeline calls.

Records each /process execution and provides summary statistics.
"""

import statistics
from datetime import datetime

# In-memory session log
session_log = []


def log_pipeline_call(
    stt_result: dict,
    lang_result: dict,
    stage_timings: dict[str, float],
) -> None:
    """Log a pipeline call with its metrics.

    Args:
        stt_result: dict with confidence, language, transcript
        lang_result: dict with entities, key_phrases, sentiment
        stage_timings: dict with stt_ms, language_ms, tts_ms
    """
    session_log.append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "confidence": stt_result.get("confidence", 0.0),
        "language": stt_result.get("language", "unknown"),
        "entity_count": len(lang_result.get("entities", [])),
        "keyphrase_count": len(lang_result.get("key_phrases", [])),
        "sentiment": lang_result.get("sentiment", {}).get("label", "unknown"),
        "stt_ms": stage_timings.get("stt_ms", 0.0),
        "language_ms": stage_timings.get("language_ms", 0.0),
        "tts_ms": stage_timings.get("tts_ms", 0.0),
    })


def get_telemetry_summary() -> dict:
    """Return summary statistics of all logged pipeline calls."""
    if not session_log:
        return {"message": "No calls logged yet", "total_calls": 0}

    confidences = [e["confidence"] for e in session_log if e["confidence"] > 0]
    stt_times = [e["stt_ms"] for e in session_log]
    lang_times = [e["language_ms"] for e in session_log]
    tts_times = [e["tts_ms"] for e in session_log]

    # Calculate percentiles
    sorted_stt = sorted(stt_times)
    sorted_lang = sorted(lang_times)
    sorted_tts = sorted(tts_times)

    n = len(session_log)
    p95_idx = max(0, int(n * 0.95) - 1)

    # Sentiment breakdown
    sentiment_counts = {}
    for e in session_log:
        s = e["sentiment"]
        sentiment_counts[s] = sentiment_counts.get(s, 0) + 1

    return {
        "total_calls": n,
        "avg_confidence": round(statistics.mean(confidences), 3) if confidences else 0.0,
        "min_confidence": round(min(confidences), 3) if confidences else 0.0,
        "max_confidence": round(max(confidences), 3) if confidences else 0.0,
        "avg_stt_ms": round(statistics.mean(stt_times), 1),
        "avg_language_ms": round(statistics.mean(lang_times), 1),
        "avg_tts_ms": round(statistics.mean(tts_times), 1),
        "p95_stt_ms": round(sorted_stt[p95_idx], 1) if sorted_stt else 0.0,
        "p95_language_ms": round(sorted_lang[p95_idx], 1) if sorted_lang else 0.0,
        "p95_tts_ms": round(sorted_tts[p95_idx], 1) if sorted_tts else 0.0,
        "sentiment_breakdown": sentiment_counts,
        "recent_calls": session_log[-10:],  # Last 10 calls
    }


def clear_log() -> None:
    """Clear the session log."""
    global session_log
    session_log = []

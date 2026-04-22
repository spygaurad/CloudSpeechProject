"""SQLite-backed transcription confidence stats."""

import sqlite3
from datetime import datetime, timezone

from app.config import STATS_DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(STATS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transcription_logs (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp             TEXT    NOT NULL,
                language              TEXT    NOT NULL,
                overall_confidence    REAL,
                total_words           INTEGER DEFAULT 0,
                low_confidence_words  INTEGER DEFAULT 0,
                retry_attempted       INTEGER DEFAULT 0,
                retry_language        TEXT,
                final_confidence      REAL
            )
        """)


# Auto-init when the module is imported
init_db()


def log_transcription(
    *,
    language: str,
    overall_confidence: float | None,
    total_words: int,
    low_confidence_words: int,
    retry_attempted: bool,
    retry_language: str | None = None,
    final_confidence: float | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO transcription_logs
                (timestamp, language, overall_confidence, total_words,
                 low_confidence_words, retry_attempted, retry_language, final_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                language,
                overall_confidence,
                total_words,
                low_confidence_words,
                int(retry_attempted),
                retry_language,
                final_confidence,
            ),
        )


def get_stats() -> dict:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM transcription_logs ORDER BY timestamp DESC"
        ).fetchall()

    if not rows:
        return {
            "total_transcriptions": 0,
            "average_confidence": None,
            "retry_rate": 0.0,
            "average_low_confidence_word_rate": 0.0,
            "recent": [],
        }

    total = len(rows)
    retries = sum(1 for r in rows if r["retry_attempted"])

    final_confs = [
        r["final_confidence"] if r["final_confidence"] is not None else r["overall_confidence"]
        for r in rows
        if (r["final_confidence"] is not None or r["overall_confidence"] is not None)
    ]
    avg_conf = sum(final_confs) / len(final_confs) if final_confs else None

    word_rates = [
        r["low_confidence_words"] / r["total_words"]
        for r in rows
        if r["total_words"] and r["total_words"] > 0
    ]
    avg_low_conf_rate = sum(word_rates) / len(word_rates) if word_rates else 0.0

    recent = [
        {
            "Timestamp": r["timestamp"][:19].replace("T", " "),
            "Language": r["language"],
            "Confidence": f"{r['overall_confidence']:.2%}" if r["overall_confidence"] is not None else "N/A",
            "Low-Conf Words": r["low_confidence_words"],
            "Total Words": r["total_words"],
            "Retried": "Yes" if r["retry_attempted"] else "No",
            "Retry Lang": r["retry_language"] or "—",
            "Final Confidence": f"{r['final_confidence']:.2%}" if r["final_confidence"] is not None else "—",
        }
        for r in rows[:20]
    ]

    return {
        "total_transcriptions": total,
        "average_confidence": round(avg_conf, 4) if avg_conf is not None else None,
        "retry_rate": round(retries / total, 4),
        "average_low_confidence_word_rate": round(avg_low_conf_rate, 4),
        "recent": recent,
    }

"""Gradio frontend mounted on the FastAPI app at /ui."""

import os
import tempfile
import uuid
from pathlib import Path

import gradio as gr
import pandas as pd
from fastapi import HTTPException

from app.config import DEFAULT_TTS_VOICE, LOW_WORD_CONFIDENCE_THRESHOLD, SUPPORTED_TTS_VOICES
from app.services.language_service import analyze_text
from app.services.stats_service import get_stats, log_transcription
from app.services.summary_service import build_summary_text
from app.services.transcription_service import transcribe_with_confidence_retry
from app.services.tts_service import synthesize_speech_bytes

# ---------------------------------------------------------------------------
# Voice choices for the dropdown
# ---------------------------------------------------------------------------
VOICE_CHOICES = {
    f"{persona.capitalize()} — {name}": name
    for name, persona in sorted(SUPPORTED_TTS_VOICES.items(), key=lambda kv: kv[1])
}
DEFAULT_VOICE_LABEL = next(
    label for label, name in VOICE_CHOICES.items() if name == DEFAULT_TTS_VOICE
)

# ---------------------------------------------------------------------------
# Content-type lookup
# ---------------------------------------------------------------------------
_EXT_TO_CONTENT_TYPE: dict[str, str] = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".aac": "audio/aac",
    ".m4a": "audio/mp4",
    ".webm": "audio/webm",
    ".flac": "audio/flac",
}

_EMPTY_TRANSCRIPT_HTML = (
    '<p style="color:#6b7280;font-style:italic">Transcript will appear here…</p>'
)
_EMPTY_HINT = '<p style="color:#6b7280;font-style:italic">Submit an audio file to see results.</p>'


# ---------------------------------------------------------------------------
# Highlighted transcript builder
# ---------------------------------------------------------------------------
def _build_transcript_html(transcript: str, words: list, low_conf_set: set[str]) -> str:
    """
    Render the transcript with low-confidence words highlighted in amber.
    Uses word objects when available, falls back to plain text split.
    """
    if not words:
        return f'<p style="font-size:15px;line-height:1.8">{transcript}</p>'

    parts: list[str] = []
    for w in words:
        text = w.word
        conf = w.confidence
        is_low = (
            isinstance(conf, float) and conf < LOW_WORD_CONFIDENCE_THRESHOLD
        ) or text in low_conf_set

        if is_low:
            title = f"confidence: {conf:.0%}" if isinstance(conf, float) else "low confidence"
            parts.append(
                f'<mark style="background:#fef08a;border-radius:3px;padding:1px 4px;" '
                f'title="{title}">{text}</mark>'
            )
        else:
            parts.append(text)

    body = " ".join(parts)
    note = ""
    if low_conf_set:
        note = (
            '<p style="font-size:12px;color:#92400e;margin-top:6px">'
            f'⚠ {len(low_conf_set)} word(s) highlighted in amber had confidence '
            f'below {LOW_WORD_CONFIDENCE_THRESHOLD:.0%}.</p>'
        )
    return f'<p style="font-size:15px;line-height:1.8">{body}</p>{note}'


# ---------------------------------------------------------------------------
# Core processing function (Analyzer tab)
# ---------------------------------------------------------------------------
def _process(audio_path: str | None, voice_label: str) -> tuple:
    if audio_path is None:
        raise gr.Error("Please record or upload an audio file before submitting.")

    voice = VOICE_CHOICES.get(voice_label, DEFAULT_TTS_VOICE)
    suffix = Path(audio_path).suffix.lower()
    content_type = _EXT_TO_CONTENT_TYPE.get(suffix)

    try:
        transcription, retry_attempted, retry_language = transcribe_with_confidence_retry(
            audio_path, content_type=content_type
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
    except HTTPException as exc:
        raise gr.Error(f"Transcription failed: {exc.detail}") from exc

    try:
        analysis = analyze_text(transcription.transcript)
    except HTTPException as exc:
        raise gr.Error(f"Language analysis failed: {exc.detail}") from exc

    summary = build_summary_text(analysis)

    try:
        _, tts_bytes = synthesize_speech_bytes(summary, voice)
    except HTTPException as exc:
        raise gr.Error(f"TTS synthesis failed: {exc.detail}") from exc

    tts_path = os.path.join(tempfile.gettempdir(), f"tts-{uuid.uuid4().hex}.mp3")
    with open(tts_path, "wb") as fh:
        fh.write(tts_bytes)

    # --- Highlighted transcript ---
    low_conf_set = set(transcription.low_confidence_words)
    transcript_html = _build_transcript_html(transcription.transcript, transcription.words, low_conf_set)

    retry_banner = ""
    if retry_attempted:
        retry_banner = (
            f'<p style="font-size:12px;color:#1d4ed8;margin-top:4px">'
            f'ℹ️ Low overall confidence — automatically retried with {retry_language}.</p>'
        )
    transcript_html = transcript_html + retry_banner

    # --- Key-phrase tags ---
    key_phrases: list[str] = analysis.get("key_phrases", [])
    if key_phrases:
        spans = " ".join(
            f'<span style="display:inline-block;background:#dbeafe;color:#1e40af;'
            f'border-radius:12px;padding:3px 12px;margin:3px 2px;font-size:13px;">'
            f"{phrase}</span>"
            for phrase in key_phrases
        )
        kp_html = f'<div style="line-height:2.2">{spans}</div>'
    else:
        kp_html = '<p style="color:#6b7280;font-style:italic">No key phrases detected.</p>'

    # --- Named-entity table ---
    raw_entities: list[dict] = analysis.get("named_entities", [])
    if raw_entities:
        rows = [
            {
                "Text": e.get("text", ""),
                "Category": e.get("category", ""),
                "Subcategory": e.get("subcategory") or "—",
                "Confidence": (
                    f"{e['confidence']:.1%}" if isinstance(e.get("confidence"), float) else "N/A"
                ),
            }
            for e in raw_entities
        ]
        entities_df = pd.DataFrame(rows)
    else:
        entities_df = pd.DataFrame(columns=["Text", "Category", "Subcategory", "Confidence"])

    # --- Sentiment bars ---
    sentiment = analysis.get("sentiment", {})
    label = sentiment.get("label", "unknown").capitalize()
    conf = sentiment.get("confidence", {})
    pos = conf.get("positive", 0)
    neu = conf.get("neutral", 0)
    neg = conf.get("negative", 0)
    color_map = {"Positive": "#16a34a", "Neutral": "#d97706", "Negative": "#dc2626"}
    label_color = color_map.get(label, "#374151")

    sentiment_html = (
        f'<div style="padding:12px;border-radius:8px;background:#f8fafc;border:1px solid #e2e8f0">'
        f'<p style="margin:0 0 8px;font-size:15px">Overall sentiment: '
        f'<strong style="color:{label_color}">{label}</strong></p>'
        f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0">'
        f'<span style="width:70px;font-size:12px">Positive</span>'
        f'<div style="width:{max(int(pos*200),2)}px;height:12px;background:#16a34a;border-radius:4px"></div>'
        f'<span style="font-size:12px">{pos:.1%}</span></div>'
        f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0">'
        f'<span style="width:70px;font-size:12px">Neutral</span>'
        f'<div style="width:{max(int(neu*200),2)}px;height:12px;background:#d97706;border-radius:4px"></div>'
        f'<span style="font-size:12px">{neu:.1%}</span></div>'
        f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0">'
        f'<span style="width:70px;font-size:12px">Negative</span>'
        f'<div style="width:{max(int(neg*200),2)}px;height:12px;background:#dc2626;border-radius:4px"></div>'
        f'<span style="font-size:12px">{neg:.1%}</span></div>'
        f"</div>"
    )

    return transcript_html, kp_html, entities_df, sentiment_html, tts_path


# ---------------------------------------------------------------------------
# Stats refresh function (Stats tab)
# ---------------------------------------------------------------------------
def _load_stats() -> tuple:
    data = get_stats()
    total = data["total_transcriptions"]

    if total == 0:
        summary_html = '<p style="color:#6b7280;font-style:italic">No transcriptions recorded yet.</p>'
        return summary_html, pd.DataFrame()

    avg_conf = data["average_confidence"]
    retry_rate = data["retry_rate"]
    avg_lcw = data["average_low_confidence_word_rate"]

    summary_html = (
        f'<div style="display:flex;gap:24px;flex-wrap:wrap;padding:8px 0">'
        f'<div style="text-align:center"><p style="font-size:24px;font-weight:700;margin:0">{total}</p>'
        f'<p style="font-size:12px;color:#6b7280;margin:0">Total</p></div>'
        f'<div style="text-align:center"><p style="font-size:24px;font-weight:700;margin:0">'
        f'{avg_conf:.1%}</p><p style="font-size:12px;color:#6b7280;margin:0">Avg Confidence</p></div>'
        f'<div style="text-align:center"><p style="font-size:24px;font-weight:700;margin:0">'
        f'{retry_rate:.1%}</p><p style="font-size:12px;color:#6b7280;margin:0">Retry Rate</p></div>'
        f'<div style="text-align:center"><p style="font-size:24px;font-weight:700;margin:0">'
        f'{avg_lcw:.1%}</p><p style="font-size:12px;color:#6b7280;margin:0">Low-Conf Word Rate</p></div>'
        f'</div>'
    ) if avg_conf is not None else (
        f'<p>Total transcriptions: {total} — confidence data not available.</p>'
    )

    recent_df = pd.DataFrame(data["recent"]) if data["recent"] else pd.DataFrame()
    return summary_html, recent_df


# ---------------------------------------------------------------------------
# Gradio Blocks layout
# ---------------------------------------------------------------------------
_CSS = """
    #submit-btn { font-size: 15px; }
    .section-header { font-size: 14px; font-weight: 600; color: #374151;
                      border-bottom: 1px solid #e5e7eb; padding-bottom: 6px; }
"""

with gr.Blocks(title="Cloud Speech Memo Analyzer") as gradio_app:
    gradio_app.theme = gr.themes.Soft()
    gradio_app.css = _CSS

    gr.Markdown("# Cloud Speech Memo Analyzer")

    with gr.Tabs():
        # ================================================================
        # TAB 1 — Analyzer
        # ================================================================
        with gr.Tab("Analyzer"):
            with gr.Row():
                # ---- Left: input ----
                with gr.Column(scale=1):
                    gr.HTML('<p class="section-header">Input</p>')

                    audio_input = gr.Audio(
                        label="Record or Upload Audio",
                        sources=["microphone", "upload"],
                        type="filepath",
                        format="wav",   # forces WAV for mic recordings → fixes post-record playback
                    )

                    voice_selector = gr.Dropdown(
                        label="TTS Voice",
                        choices=list(VOICE_CHOICES.keys()),
                        value=DEFAULT_VOICE_LABEL,
                    )

                    submit_btn = gr.Button("Submit", variant="primary", elem_id="submit-btn")

                # ---- Right: results ----
                with gr.Column(scale=2):
                    gr.HTML('<p class="section-header">Results</p>')

                    with gr.Accordion("Transcript", open=True):
                        transcript_html = gr.HTML(
                            value=_EMPTY_TRANSCRIPT_HTML,
                            label="Transcript",
                        )

                    with gr.Accordion("Key Phrases", open=True):
                        kp_output = gr.HTML(value=_EMPTY_HINT)

                    with gr.Accordion("Named Entities", open=True):
                        entities_table = gr.Dataframe(
                            headers=["Text", "Category", "Subcategory", "Confidence"],
                            interactive=False,
                            wrap=True,
                        )

                    with gr.Accordion("Sentiment", open=True):
                        sentiment_output = gr.HTML(value=_EMPTY_HINT)

                    with gr.Accordion("TTS Summary Audio", open=True):
                        tts_player = gr.Audio(
                            label="Spoken Summary",
                            type="filepath",
                            interactive=False,
                        )

            submit_btn.click(
                fn=_process,
                inputs=[audio_input, voice_selector],
                outputs=[transcript_html, kp_output, entities_table, sentiment_output, tts_player],
                api_name=False,
            )

        # ================================================================
        # TAB 2 — Stats
        # ================================================================
        with gr.Tab("Stats"):
            gr.Markdown("### Transcription Confidence Statistics")
            gr.Markdown(
                "Aggregated across all transcriptions logged to the local SQLite database. "
                "Amber-highlighted words in the Analyzer tab had word-level confidence below "
                f"{LOW_WORD_CONFIDENCE_THRESHOLD:.0%}."
            )

            refresh_btn = gr.Button("Refresh", variant="secondary")

            stats_summary = gr.HTML(
                value='<p style="color:#6b7280;font-style:italic">Click Refresh to load stats.</p>'
            )

            stats_table = gr.Dataframe(
                headers=[
                    "Timestamp", "Language", "Confidence", "Low-Conf Words",
                    "Total Words", "Retried", "Retry Lang", "Final Confidence",
                ],
                label="Recent Transcriptions (last 20)",
                interactive=False,
                wrap=True,
            )

            refresh_btn.click(
                fn=_load_stats,
                inputs=[],
                outputs=[stats_summary, stats_table],
                api_name=False,
            )

"""Gradio frontend mounted on the FastAPI app at /ui."""

import os
import tempfile
import uuid
from pathlib import Path

import gradio as gr
import pandas as pd
from fastapi import HTTPException

from app.config import DEFAULT_TTS_VOICE, SUPPORTED_TTS_VOICES
from app.services.language_service import analyze_text
from app.services.summary_service import build_summary_text
from app.services.transcription_service import transcribe_file_with_sdk
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
# Content-type lookup used when a file is uploaded (not a mic recording)
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


# ---------------------------------------------------------------------------
# Core processing function
# ---------------------------------------------------------------------------
def _process(audio_path: str | None, voice_label: str) -> tuple:
    """Run the full pipeline and return Gradio component values."""
    if audio_path is None:
        raise gr.Error("Please record or upload an audio file before submitting.")

    voice = VOICE_CHOICES.get(voice_label, DEFAULT_TTS_VOICE)
    suffix = Path(audio_path).suffix.lower()
    content_type = _EXT_TO_CONTENT_TYPE.get(suffix)

    try:
        transcription = transcribe_file_with_sdk(audio_path, content_type=content_type)
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

    # Persist TTS audio so Gradio can serve it from a filepath
    tts_path = os.path.join(tempfile.gettempdir(), f"tts-{uuid.uuid4().hex}.mp3")
    with open(tts_path, "wb") as fh:
        fh.write(tts_bytes)

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

    # --- Sentiment ---
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

    return transcription.transcript, kp_html, entities_df, sentiment_html, tts_path


# ---------------------------------------------------------------------------
# Gradio Blocks layout
# ---------------------------------------------------------------------------
_CSS = """
    #submit-btn { background: #2563eb; color: white; font-size: 15px; }
    .section-header { font-size: 14px; font-weight: 600; color: #374151;
                      border-bottom: 1px solid #e5e7eb; padding-bottom: 6px; }
"""

with gr.Blocks(title="Cloud Speech Memo Analyzer") as gradio_app:
    gradio_app.theme = gr.themes.Soft()
    gradio_app.css = _CSS

    gr.Markdown(
        """
        # Cloud Speech Memo Analyzer
        Record a voice memo or upload an audio file to get a full transcript,
        key-phrase tags, named entities, sentiment analysis, and a spoken summary.
        """
    )

    with gr.Row():
        # ---- Left panel: input ----
        with gr.Column(scale=1):
            gr.HTML('<p class="section-header">Input</p>')

            audio_input = gr.Audio(
                label="Record or Upload Audio",
                sources=["microphone", "upload"],
                type="filepath",
            )

            voice_selector = gr.Dropdown(
                label="TTS Voice",
                choices=list(VOICE_CHOICES.keys()),
                value=DEFAULT_VOICE_LABEL,
            )

            submit_btn = gr.Button("Submit", variant="primary", elem_id="submit-btn")

        # ---- Right panel: results ----
        with gr.Column(scale=2):
            gr.HTML('<p class="section-header">Results</p>')

            transcript_box = gr.Textbox(
                label="Full Transcript",
                lines=5,
                interactive=False,
                placeholder="Transcript will appear here…",
            )

            with gr.Accordion("Key Phrases", open=True):
                kp_output = gr.HTML(
                    label="Key Phrases",
                    value='<p style="color:#6b7280;font-style:italic">Submit an audio file to see key phrases.</p>',
                )

            with gr.Accordion("Named Entities", open=True):
                entities_table = gr.Dataframe(
                    label="Named Entities",
                    headers=["Text", "Category", "Subcategory", "Confidence"],
                    interactive=False,
                    wrap=True,
                )

            with gr.Accordion("Sentiment", open=True):
                sentiment_output = gr.HTML(
                    label="Sentiment",
                    value='<p style="color:#6b7280;font-style:italic">Submit an audio file to see sentiment scores.</p>',
                )

            with gr.Accordion("TTS Summary Audio", open=True):
                tts_player = gr.Audio(
                    label="Spoken Summary",
                    type="filepath",
                    interactive=False,
                )

    submit_btn.click(
        fn=_process,
        inputs=[audio_input, voice_selector],
        outputs=[transcript_box, kp_output, entities_table, sentiment_output, tts_player],
        api_name=False,
    )

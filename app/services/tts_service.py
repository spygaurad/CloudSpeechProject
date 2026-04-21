import base64

import azure.cognitiveservices.speech as speechsdk
from fastapi import HTTPException

from app.config import DEFAULT_TTS_VOICE, SUPPORTED_TTS_VOICES, require_env


OUTPUT_FORMAT = "Audio16Khz32KBitRateMonoMp3"


def get_voices() -> list[dict[str, str]]:
    return [
        {"name": name, "persona": persona}
        for name, persona in sorted(SUPPORTED_TTS_VOICES.items())
    ]


def normalize_voice(voice: str | None) -> str:
    normalized = voice or DEFAULT_TTS_VOICE
    if normalized not in SUPPORTED_TTS_VOICES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported voice '{normalized}'. "
                f"Supported voices: {sorted(SUPPORTED_TTS_VOICES.keys())}"
            ),
        )
    return normalized


def synthesize_speech_base64(text: str, voice: str | None = None) -> dict[str, str]:
    selected_voice = normalize_voice(voice)
    try:
        speech_key = require_env("AZURE_SPEECH_KEY")
        speech_region = require_env("AZURE_SPEECH_REGION")
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_synthesis_voice_name = selected_voice
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
    )

    synth = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    result = synth.speak_text_async(text).get()

    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise HTTPException(status_code=502, detail=f"TTS synthesis failed: {result.reason}")

    return {
        "voice": selected_voice,
        "format": OUTPUT_FORMAT,
        "audio_base64": base64.b64encode(result.audio_data).decode("utf-8"),
    }


def synthesize_speech_bytes(text: str, voice: str | None = None) -> tuple[str, bytes]:
    selected_voice = normalize_voice(voice)
    try:
        speech_key = require_env("AZURE_SPEECH_KEY")
        speech_region = require_env("AZURE_SPEECH_REGION")
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_synthesis_voice_name = selected_voice
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
    )

    synth = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    result = synth.speak_text_async(text).get()

    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise HTTPException(status_code=502, detail=f"TTS synthesis failed: {result.reason}")

    return selected_voice, result.audio_data

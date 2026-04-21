from typing import Any

import requests
from fastapi import HTTPException

from app.config import require_env


def _language_url() -> str:
    try:
        endpoint = require_env("AZURE_LANGUAGE_ENDPOINT").rstrip("/")
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return f"{endpoint}/language/:analyze-text?api-version=2023-04-01"


def _language_headers() -> dict[str, str]:
    try:
        key = require_env("AZURE_LANGUAGE_KEY")
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/json",
    }


def _call_language(kind: str, text: str) -> dict[str, Any]:
    response = requests.post(
        _language_url(),
        headers=_language_headers(),
        json={
            "kind": kind,
            "analysisInput": {
                "documents": [{"id": "1", "text": text, "language": "en"}],
            },
        },
        timeout=30,
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Azure Language request failed for {kind}: {response.status_code} {response.text}",
        )

    return response.json()


def analyze_text(text: str) -> dict[str, Any]:
    key_phrases = _call_language("KeyPhraseExtraction", text)
    ner = _call_language("EntityRecognition", text)
    sentiment = _call_language("SentimentAnalysis", text)
    linked = _call_language("EntityLinking", text)

    kp_doc = key_phrases["results"]["documents"][0]
    ner_doc = ner["results"]["documents"][0]
    sentiment_doc = sentiment["results"]["documents"][0]
    linked_doc = linked["results"]["documents"][0]

    return {
        "key_phrases": kp_doc.get("keyPhrases", []),
        "named_entities": [
            {
                "text": item.get("text"),
                "category": item.get("category"),
                "subcategory": item.get("subcategory"),
                "confidence": item.get("confidenceScore"),
            }
            for item in ner_doc.get("entities", [])
        ],
        "sentiment": {
            "label": sentiment_doc.get("sentiment"),
            "confidence": sentiment_doc.get("confidenceScores", {}),
        },
        "linked_entities": [
            {
                "name": item.get("name"),
                "url": item.get("url"),
                "data_source": item.get("dataSource"),
                "entity_id": item.get("id"),
                "matches": item.get("matches", []),
            }
            for item in linked_doc.get("entities", [])
        ],
    }

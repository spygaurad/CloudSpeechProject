from collections import Counter


def build_summary_text(analysis: dict) -> str:
    key_phrases = analysis.get("key_phrases", [])
    sentiment_label = analysis.get("sentiment", {}).get("label", "unknown")
    named_entities = analysis.get("named_entities", [])

    if key_phrases:
        topics = ", ".join(key_phrases[:5])
        key_phrase_sentence = (
            f"Your memo mentions {len(key_phrases)} key topics: {topics}."
        )
    else:
        key_phrase_sentence = "I did not find strong key topics in the transcript."

    entity_counter = Counter(entity.get("category", "Unknown") for entity in named_entities)
    if entity_counter:
        ordered_types = [f"{count} {name}" for name, count in entity_counter.most_common()]
        entity_sentence = "I detected entity types including " + ", ".join(ordered_types) + "."
    else:
        entity_sentence = "I did not detect named entities."

    return (
        f"{key_phrase_sentence} "
        f"The overall tone is {sentiment_label}. "
        f"{entity_sentence}"
    )

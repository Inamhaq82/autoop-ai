from typing import Dict, Any


def summarize_text_local(text: str, max_sentences: int = 2) -> Dict[str, Any]:
    """
    Naive summarizer: takes first N sentences.
    Reason:
    - Deterministic tool for verifying routing & schemas without LLM variability.
    Benefit:
    - You can test tool calling reliably.
    """
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    summary = ". ".join(sentences[:max_sentences])
    key_points = sentences[:min(5, len(sentences))]
    return {
        "summary": summary + ("." if summary and not summary.endswith(".") else ""),
        "key_points": key_points,
    }

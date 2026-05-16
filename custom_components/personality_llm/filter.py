"""Heuristic false-activation filter for personality_llm.

Checks whether a voice input looks like background speech rather than
a command directed at the assistant. Returns (should_filter, reason)
so the caller can log and silently discard the input.
"""
from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)


def check_heuristic(text: str, min_words: int, phrases_raw: str) -> tuple[bool, str]:
    """Return (should_filter, reason). True means discard this input."""
    stripped = text.strip()

    words = stripped.split()
    if len(words) < min_words:
        return True, f"too short ({len(words)} word(s), min={min_words})"

    text_lower = stripped.lower()
    for phrase in (p.strip().lower() for p in phrases_raw.splitlines() if p.strip()):
        if phrase in text_lower:
            return True, f"matched phrase '{phrase}'"

    return False, ""

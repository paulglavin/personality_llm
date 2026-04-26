"""Prompt resolution logic for personality_llm."""
from __future__ import annotations

import logging

from .prompt_generator import generate_personality_prompt

_LOGGER = logging.getLogger(__name__)


def _combine(*parts: str) -> str:
    """Join non-empty prompt parts with a blank line between them."""
    return "\n\n".join(p for p in parts if p and p.strip())


def _build_speaker_header(user_config: dict) -> str:
    """Build a speaker identification line from user config (legacy path)."""
    name = (user_config.get("display_name") or "").strip()
    pronouns = (user_config.get("pronouns") or "").strip()
    if not name or name == "Guest":
        return ""
    if pronouns:
        return f"You are speaking with {name} ({pronouns}). Address them by name and use their preferred pronouns."
    return f"You are speaking with {name}. Address them by name."


def resolve_prompts(
    house_model_prompt: str,
    house_personality_prompt: str,
    user_config: dict | None,
    entry_options: dict,
) -> tuple[str, str]:
    """Resolve the final (system_prompt, extra_system_prompt) pair.

    Routing:
      - Structured mode  — 'personality_style' present in entry_options.
        Personality directives are generated and returned as extra_system_prompt,
        which HA injects after the entity list (recency advantage).
      - Legacy mode — no 'personality_style' key; all personality content is
        baked into system_prompt using the old layered logic.

    In both modes:
      - full_prompt_override (if allowed and set) short-circuits everything.
      - Per-user features are gated by 'enable_per_user_personality'.
    """
    is_structured = "personality_style" in entry_options

    if is_structured:
        return _resolve_structured(
            house_model_prompt, house_personality_prompt, user_config, entry_options
        )
    return _resolve_legacy(
        house_model_prompt, house_personality_prompt, user_config, entry_options
    ), ""


# ---------------------------------------------------------------------------
# Structured path
# ---------------------------------------------------------------------------

def _resolve_structured(
    house_model_prompt: str,
    house_personality_prompt: str,
    user_config: dict | None,
    entry_options: dict,
) -> tuple[str, str]:
    """Return (system_prompt, extra_system_prompt) in structured mode."""

    # Full prompt override — user takes full control; nothing extra needed.
    if (
        entry_options.get("allow_full_prompt_override")
        and user_config
        and user_config.get("full_prompt_override")
    ):
        _LOGGER.info("User using full prompt override (house prompts bypassed)")
        return user_config["full_prompt_override"], ""

    effective_user = (
        user_config
        if entry_options.get("enable_per_user_personality") and user_config
        else {}
    )

    extra = generate_personality_prompt(entry_options, effective_user)

    if extra:
        _LOGGER.debug(
            "Structured personality generated (first 80 chars): %s…", extra[:80]
        )
        return house_model_prompt, extra

    # All dropdowns are 'custom' or 'none' and no user content — fall back to
    # including house_personality_prompt in system_prompt so responses aren't
    # personality-free.
    _LOGGER.debug(
        "Structured mode active but generator returned empty; "
        "falling back to house_personality_prompt in system_prompt"
    )
    return _combine(house_model_prompt, house_personality_prompt), ""


# ---------------------------------------------------------------------------
# Legacy path (no structured fields — preserves existing behaviour exactly)
# ---------------------------------------------------------------------------

def _resolve_legacy(
    house_model_prompt: str,
    house_personality_prompt: str,
    user_config: dict | None,
    capabilities: dict,
) -> str:
    """Resolve a single system_prompt string using the original layered logic."""

    if not capabilities.get("enable_per_user_personality") or not user_config:
        _LOGGER.debug("Legacy: using house defaults only (per-user disabled or no config)")
        return _combine(house_model_prompt, house_personality_prompt)

    if (
        capabilities.get("allow_full_prompt_override")
        and user_config.get("full_prompt_override")
    ):
        _LOGGER.info("Legacy: user using full prompt override")
        return user_config["full_prompt_override"]

    speaker_header = _build_speaker_header(user_config)

    if (
        capabilities.get("allow_personality_override")
        and user_config.get("override_house_personality")
        and user_config.get("personality_override_prompt")
    ):
        _LOGGER.debug("Legacy: user personality override replacing house personality")
        return _combine(house_model_prompt, speaker_header, user_config["personality_override_prompt"])

    if speaker_header or user_config.get("personality_prompt"):
        _LOGGER.debug("Legacy: user personality appended to house defaults")
        return _combine(
            house_model_prompt,
            house_personality_prompt,
            speaker_header,
            user_config.get("personality_prompt", ""),
        )

    _LOGGER.debug("Legacy: no active user personality, using house defaults")
    return _combine(house_model_prompt, house_personality_prompt)

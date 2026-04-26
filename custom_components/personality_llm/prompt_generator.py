"""Generate extra_system_prompt from structured personality configuration.

Structured fields (dropdowns, short text) map to bulleted directive blocks
that models follow more reliably than narrative prose.  The output is
injected as extra_system_prompt so it lands after the HA entity list,
giving it recency advantage over the main system_prompt.

Entry point: generate_personality_prompt(house_opts, user_config) -> str
"""
from __future__ import annotations

from .const import (
    ADDRESS_STYLE_CUSTOM,
    ADDRESS_STYLE_DIRECTIVES,
    DEFAULT_ADDRESS_STYLE,
    DEFAULT_HUMOR_LEVEL,
    DEFAULT_PERSONALITY_STYLE,
    DEFAULT_RESPONSE_STYLE,
    HUMOR_LEVEL_DIRECTIVES,
    HUMOR_LEVEL_NONE,
    PERSONAL_CONTEXT_MAX_LENGTH,
    PERSONALITY_STYLE_CUSTOM,
    PERSONALITY_STYLE_DIRECTIVES,
    RESPONSE_STYLE_DIRECTIVES,
    SECTION_HEADER_ADDRESSING,
    SECTION_HEADER_CONTEXT,
    SECTION_HEADER_HUMOR,
    SECTION_HEADER_PERSONALITY,
    SECTION_HEADER_RESPONSE_STYLE,
)


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def _section(header: str, bullet_block: str) -> str:
    return f"{header}\n{bullet_block}"


def _speaker_header(user_config: dict) -> str:
    """Build the 'You are speaking with…' line from display_name and pronouns."""
    name = (user_config.get("display_name") or "").strip()
    pronouns = (user_config.get("pronouns") or "").strip()
    if not name or name == "Guest":
        return ""
    if pronouns:
        return (
            f"You are speaking with {name} ({pronouns}). "
            "Address them by name and use their preferred pronouns."
        )
    return f"You are speaking with {name}. Address them by name."


def generate_personality_prompt(house_opts: dict, user_config: dict) -> str:
    """Return the assembled extra_system_prompt for the current speaker.

    Returns an empty string when nothing is configured (all values default
    or 'custom'/'none'), so the caller can skip the injection entirely.

    The resolver decides whether to call this function at all (structured
    vs. advanced-raw-prompt routing); this function is purely generative.
    """
    parts: list[str] = []

    # Speaker identification — always first if a known user
    header = _speaker_header(user_config)
    if header:
        parts.append(header)

    # ── House-level sections ────────────────────────────────────────────────

    personality_style = house_opts.get("personality_style", DEFAULT_PERSONALITY_STYLE)
    if personality_style != PERSONALITY_STYLE_CUSTOM:
        directives = PERSONALITY_STYLE_DIRECTIVES.get(personality_style, [])
        if directives:
            parts.append(_section(SECTION_HEADER_PERSONALITY, _bullets(directives)))

    humor_level = house_opts.get("humor_level", DEFAULT_HUMOR_LEVEL)
    if humor_level != HUMOR_LEVEL_NONE:
        directives = HUMOR_LEVEL_DIRECTIVES.get(humor_level, [])
        if directives:
            parts.append(_section(SECTION_HEADER_HUMOR, _bullets(directives)))

    response_style = house_opts.get("response_style", DEFAULT_RESPONSE_STYLE)
    directives = RESPONSE_STYLE_DIRECTIVES.get(response_style, [])
    if directives:
        parts.append(_section(SECTION_HEADER_RESPONSE_STYLE, _bullets(directives)))

    # ── Per-user sections ───────────────────────────────────────────────────

    name = (user_config.get("display_name") or "").strip()
    has_name = bool(name and name != "Guest")

    address_style = user_config.get("address_style", DEFAULT_ADDRESS_STYLE)
    if address_style != ADDRESS_STYLE_CUSTOM:
        directives = ADDRESS_STYLE_DIRECTIVES.get(address_style, [])
        if directives:
            addr_header = (
                SECTION_HEADER_ADDRESSING.format(name=name)
                if has_name
                else "## Addressing the user"
            )
            parts.append(_section(addr_header, _bullets(directives)))

    personal_context = (user_config.get("personal_context") or "").strip()
    if personal_context:
        # Silently truncate to soft cap; the UI already warns at save time.
        if len(personal_context) > PERSONAL_CONTEXT_MAX_LENGTH:
            personal_context = personal_context[:PERSONAL_CONTEXT_MAX_LENGTH]
        ctx_header = (
            SECTION_HEADER_CONTEXT.format(name=name)
            if has_name
            else "## Additional context about the user"
        )
        ctx_intro = (
            f"The following is provided by {name} as background:"
            if has_name
            else "The following is provided as background:"
        )
        parts.append(f"{ctx_header}\n{ctx_intro}\n{personal_context}")

    return "\n\n".join(parts)

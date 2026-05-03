"""Generate extra_system_prompt from structured personality configuration.

Example-driven approach: personality styles map to concrete User/Assistant
exchange examples rather than abstract directive bullets. Small models learn
from input→output pairs far more reliably than meta-instructions.

Multiple state variants per style (all_on / none_on / some_on) teach the
model that it must reflect actual tool results, not copy example content.

Entry point: generate_personality_prompt(house_opts, user_config) -> str
"""
from __future__ import annotations

from .const import (
    ADDRESS_STYLE_BY_NAME,
    ADDRESS_STYLE_CASUAL,
    CONF_ASSISTANT_NAME,
    DEFAULT_ADDRESS_STYLE,
    DEFAULT_ASSISTANT_NAME,
    DEFAULT_HUMOR_LEVEL,
    DEFAULT_PERSONALITY_STYLE,
    DEFAULT_RESPONSE_STYLE,
    GOOD_BAD_EXAMPLES,
    HUMOR_LEVEL_EXAMPLES,
    HUMOR_LEVEL_NONE,
    PERSONAL_CONTEXT_MAX_LENGTH,
    PERSONALITY_STYLE_CUSTOM,
    PERSONALITY_STYLE_EXAMPLES,
    PERSONALITY_STYLE_PLAYFUL,
    PERSONALITY_STYLE_PROFESSIONAL,
    PERSONALITY_STYLE_SARCASTIC,
    PERSONALITY_STYLE_WITTY,
    USER_STYLE_INHERIT,
)


def _resolve_style(user_val: str | None, house_val: str | None, default: str) -> str:
    """Return user value when set and not 'inherit', otherwise fall back to house."""
    if user_val and user_val != USER_STYLE_INHERIT:
        return user_val
    return house_val or default


def _format_example(example: str, user_config: dict, house_opts: dict) -> str:
    """Replace {name}, {assistant_name}, {partner_name} placeholders."""
    name = (user_config.get("display_name") or "").strip() or "there"
    assistant_name = house_opts.get(CONF_ASSISTANT_NAME, DEFAULT_ASSISTANT_NAME)

    spouse_name = "someone"
    personal_context = (user_config.get("personal_context") or "").lower()
    for marker in ("married to", "partner is", "partnered with", "husband is", "wife is"):
        if marker in personal_context:
            after = personal_context.split(marker, 1)[1]
            candidate = after.split(",")[0].split(".")[0].strip()
            if candidate:
                spouse_name = candidate.title()
                break

    return (
        example
        .replace("{name}", name)
        .replace("{assistant_name}", assistant_name)
        .replace("{partner_name}", spouse_name)
    )


def _build_style_examples(
    personality_style: str,
    humor_level: str,
    user_config: dict,
    house_opts: dict,
) -> str:
    """Generate micro-examples showing both empty and full states, plus general tone."""
    examples = []

    personality_examples = PERSONALITY_STYLE_EXAMPLES.get(personality_style, {})
    if personality_examples:
        # Show both "none on" and "all on" so the model learns to reflect actual results
        for key in ("device_query_none_on", "device_query_all_on"):
            if key in personality_examples:
                examples.append(_format_example(personality_examples[key], user_config, house_opts))
        if "general_query" in personality_examples:
            examples.append(_format_example(personality_examples["general_query"], user_config, house_opts))

    if humor_level != HUMOR_LEVEL_NONE:
        humor_example = HUMOR_LEVEL_EXAMPLES.get(humor_level)
        if humor_example:
            examples.append(_format_example(humor_example, user_config, house_opts))

    return "\n\n".join(examples)


def _build_good_bad_examples(personality_style: str, user_config: dict) -> str:
    """Generate contrastive examples for complex styles."""
    template = GOOD_BAD_EXAMPLES.get(personality_style)
    if not template:
        return ""
    name = (user_config.get("display_name") or "User").strip() or "User"
    return template.replace("{name}", name)


def generate_personality_prompt(house_opts: dict, user_config: dict) -> str:
    """Return the assembled extra_system_prompt for the current speaker.

    Returns an empty string when nothing is configured, so the caller can
    skip injection entirely.
    """
    parts: list[str] = []

    assistant_name = house_opts.get(CONF_ASSISTANT_NAME, DEFAULT_ASSISTANT_NAME)
    if assistant_name and assistant_name != DEFAULT_ASSISTANT_NAME:
        parts.append(f"# Active session\nYou are {assistant_name.rstrip('.')}.")

    name = (user_config.get("display_name") or "").strip()
    pronouns = (user_config.get("pronouns") or "").strip()
    has_name = bool(name and name != "Guest")

    if has_name:
        if pronouns:
            parts.append(f"Speaking with: {name} ({pronouns})")
        else:
            parts.append(f"Speaking with: {name}")

    personal_context = (user_config.get("personal_context") or "").strip()
    if personal_context:
        if len(personal_context) > PERSONAL_CONTEXT_MAX_LENGTH:
            personal_context = personal_context[:PERSONAL_CONTEXT_MAX_LENGTH]
        if has_name:
            parts.append(f"# About {name}\n{personal_context}")
        else:
            parts.append(f"# User Context\n{personal_context}")

        # Suppress the common failure mode of defaulting to family references.
        _ctx = personal_context.lower()
        _has_family = any(
            m in _ctx
            for m in ("married to", "partner is", "partnered with", "husband is", "wife is", "father to", "mother to", "child", "son", "daughter")
        )
        if _has_family:
            parts.append(
                "# Family context\n"
                "Mention family members only when it adds something genuinely amusing — "
                "not as a default punchline. Most responses should stand on their own "
                "without referencing them."
            )

    personality_style = _resolve_style(
        user_config.get("personality_style"),
        house_opts.get("personality_style"),
        DEFAULT_PERSONALITY_STYLE,
    )
    humor_level = _resolve_style(
        user_config.get("humor_level"),
        house_opts.get("humor_level"),
        DEFAULT_HUMOR_LEVEL,
    )

    if personality_style != PERSONALITY_STYLE_CUSTOM:
        style_examples = _build_style_examples(
            personality_style, humor_level, user_config, house_opts
        )
        if style_examples:
            parts.append(f"# Response Examples\n{style_examples}")

        good_bad = _build_good_bad_examples(personality_style, user_config)
        if good_bad:
            parts.append(good_bad)

        post_tool_reminder = (
            "# After tool calls\n"
            "Tool results are just data. Your personality is how you deliver them.\n"
            'BAD: "Turned off the lights in the front room, {name}."\n'
            'GOOD: "Front room lights out, {name}. Saves me the embarrassment of reporting them on again in an hour."'
        )
        parts.append(_format_example(post_tool_reminder, user_config, house_opts))

    voice_map = {
        PERSONALITY_STYLE_SARCASTIC: "dry, ironic",
        PERSONALITY_STYLE_WITTY: "clever, observant",
        PERSONALITY_STYLE_PLAYFUL: "energetic, fun",
        PERSONALITY_STYLE_PROFESSIONAL: "polished, efficient",
    }
    voice = voice_map.get(personality_style, "")
    priority_items = [
        f"ALWAYS respond in {assistant_name} voice ({voice}) — never revert to a generic assistant tone, especially after tool calls" if voice else f"ALWAYS respond in {assistant_name} voice — never revert to a generic assistant tone",
        'Base responses on actual tool results — check each entity\'s "state" field. If state="off" say it\'s off; if state="on" say it\'s on. Never contradict tool results.',
        "Use tools for device/state queries",
        "Format for speech (spelled numbers, no symbols)",
    ]

    address_style = user_config.get("address_style", DEFAULT_ADDRESS_STYLE)
    if address_style == ADDRESS_STYLE_BY_NAME and has_name:
        priority_items.append(f"Address {name} by name in most responses")
    elif address_style == ADDRESS_STYLE_CASUAL and has_name:
        priority_items.append(f"Use {name}'s name when natural")

    numbered = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(priority_items))
    parts.append(f"# Priority\n{numbered}")

    return "\n\n".join(parts)

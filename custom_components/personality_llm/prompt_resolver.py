"""Prompt resolution logic for personality_llm."""
from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)


def resolve_system_prompt(
    house_model_prompt: str,
    house_personality_prompt: str,
    user_config: dict | None,
    capabilities: dict,
) -> str:
    """
    Resolve the final system prompt using layered precedence.

    Priority (highest to lowest):
    1. User full prompt override (if allowed and provided)
    2. User personality replacing house personality (if allowed)
    3. User personality appended to house prompts
    4. House prompts only (default)

    Args:
        house_model_prompt: Global model instructions (safety, scope, tools).
        house_personality_prompt: Global tone and style.
        user_config: Per-user settings dict, or None if not applicable.
        capabilities: Admin-level capability flags.

    Returns:
        Assembled system prompt string.
    """
    # Base case: no per-user features or no user config
    if not capabilities.get("enable_per_user_personality") or not user_config:
        _LOGGER.debug("Using house defaults only (per-user disabled or no user config)")
        return f"{house_model_prompt}\n\n{house_personality_prompt}"

    # Full override (highest precedence, most dangerous)
    if (
        capabilities.get("allow_full_prompt_override")
        and user_config.get("full_prompt_override")
    ):
        _LOGGER.info("User using full prompt override (house prompts bypassed)")
        return user_config["full_prompt_override"]

    # User personality enabled and provided
    if user_config.get("enabled") and user_config.get("personality_prompt"):
        if (
            capabilities.get("allow_personality_override")
            and user_config.get("override_house_personality")
        ):
            # User personality replaces house personality
            _LOGGER.debug("User personality replacing house personality")
            return f"{house_model_prompt}\n\n{user_config['personality_prompt']}"

        # Additive: user personality appended to house prompts
        _LOGGER.debug("User personality appended to house defaults")
        return (
            f"{house_model_prompt}\n\n"
            f"{house_personality_prompt}\n\n"
            f"{user_config['personality_prompt']}"
        )

    # Fallback: house defaults
    _LOGGER.debug("User has no active personality, using house defaults")
    return f"{house_model_prompt}\n\n{house_personality_prompt}"
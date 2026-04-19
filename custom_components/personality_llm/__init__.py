"""The personality_llm integration."""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from aiohttp import web
from homeassistant.components import webhook
from homeassistant.components.conversation import DOMAIN as CONVERSATION_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import service
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.typing import ConfigType
from openai import AsyncOpenAI, AuthenticationError, OpenAIError

from .const import (
    CONF_BASE_URL,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
    LOGGER,
    WEBHOOK_ID,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.AI_TASK, Platform.CONVERSATION]

# Validation regex for speaker_id
SPEAKER_ID_REGEX = re.compile(r"^[a-zA-Z0-9_]{1,50}$")

type LocalAiConfigEntry = ConfigEntry[AsyncOpenAI]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up is called when Home Assistant is loading our component."""
    service.async_register_platform_entity_service(
        hass=hass,
        service_domain=DOMAIN,
        service_name="add_to_weaviate",
        entity_domain=CONVERSATION_DOMAIN,
        schema={
            vol.Required("query"): str,
            vol.Required("content"): str,
            vol.Optional("identifier"): str,
        },
        func=upsert_data_in_weaviate,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LocalAiConfigEntry) -> bool:
    """Set up personality_llm from a config entry."""
    
    # ========== EXISTING: OpenAI client setup ==========
    client = AsyncOpenAI(
        base_url=entry.data[CONF_BASE_URL],
        api_key=entry.data.get(CONF_API_KEY, ""),
        http_client=get_async_client(hass),
    )

    _ = await hass.async_add_executor_job(client.platform_headers)

    try:
        async for _ in client.with_options(timeout=10.0).models.list():
            break
    except AuthenticationError as err:
        _LOGGER.error("Invalid API key: %s", err)
        raise ConfigEntryError("Invalid API key") from err
    except OpenAIError as err:
        raise ConfigEntryNotReady(err) from err

    entry.runtime_data = client
    
    # ========== NEW: Speaker Awareness Setup (Phase 1) ==========
    # Initialize speaker infrastructure BEFORE platforms load
    # This makes speaker_cache and config_manager available to conversation.py
    
    hass.data.setdefault(DOMAIN, {})
    
    # Speaker cache (ephemeral, 2s TTL)
    from .speaker_cache import SpeakerCache
    speaker_cache = SpeakerCache(hass)
    hass.data[DOMAIN]["speaker_cache"] = speaker_cache
    
    # User config manager (persistent, per-speaker settings)
    from .user_config import UserConfigManager
    config_manager = UserConfigManager(hass)
    await config_manager.async_load()
    hass.data[DOMAIN]["config_manager"] = config_manager
    
    # Webhook for VoicePipeline (config-entry scoped, optional secret)
    webhook_secret = entry.data.get(CONF_WEBHOOK_SECRET)
    hass.data[DOMAIN]["webhook_secret"] = webhook_secret
    
    webhook.async_register(
        hass,
        DOMAIN,
        "Personality LLM",
        WEBHOOK_ID,
        async_webhook_handler,
        allowed_methods=["POST"],
    )
    
    _LOGGER.info("Speaker awareness initialized (webhook: %s)", WEBHOOK_ID)
    
    # ========== EXISTING: Platform loading ==========
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ========== EXISTING: Update listener ==========
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: LocalAiConfigEntry
) -> None:
    """Handle update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: LocalAiConfigEntry) -> bool:
    """Unload personality_llm."""
    
    # NEW: Unregister webhook
    webhook.async_unregister(hass, WEBHOOK_ID)
    
    # NEW: Clean up speaker data
    hass.data.get(DOMAIN, {}).clear()

    # EXISTING: Unload platforms
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def upsert_data_in_weaviate(entity, service_call):
    """Service action to add content to Weaviate."""
    await entity.upsert_data_in_weaviate(
        query=service_call.data.get("query"),
        content=service_call.data.get("content"),
        identifier=service_call.data.get("identifier"),
    )


# ========== NEW: Webhook Handler ==========

async def async_webhook_handler(
    hass: HomeAssistant,
    webhook_id: str,
    request: web.Request,
) -> web.Response:
    """
    Handle webhook from VoicePipeline.
    
    Expected payload:
    {
        "speaker_id": "paul",
        "confidence": 0.95,
        "timestamp": "2026-04-19T12:00:00Z",
        "interaction_id": "uuid..." (optional),
        "secret": "shared_secret" (optional, if configured)
    }
    """
    # Parse JSON payload
    try:
        data = await request.json()
    except Exception as e:
        _LOGGER.warning("Invalid JSON in webhook: %s", e)
        return web.json_response(
            {"success": False, "error": "Invalid JSON"},
            status=400,
        )
    
    # Validate secret (if configured)
    webhook_secret = hass.data[DOMAIN].get("webhook_secret")
    if webhook_secret:
        provided_secret = data.get("secret")
        if provided_secret != webhook_secret:
            _LOGGER.warning("Webhook authentication failed")
            return web.json_response(
                {"success": False, "error": "Invalid secret"},
                status=401,
            )
    
    # Validate speaker_id
    speaker_id = data.get("speaker_id")
    if not speaker_id or not SPEAKER_ID_REGEX.match(speaker_id):
        _LOGGER.warning("Invalid speaker_id: %s", speaker_id)
        return web.json_response(
            {"success": False, "error": "Invalid speaker_id format"},
            status=400,
        )
    
    # Validate confidence
    confidence = data.get("confidence")
    if confidence is None:
        _LOGGER.warning("Missing confidence in webhook payload")
        return web.json_response(
            {"success": False, "error": "Missing confidence"},
            status=400,
        )
    
    try:
        confidence = float(confidence)
        if not (0.0 <= confidence <= 1.0):
            raise ValueError("out of range")
    except (TypeError, ValueError) as e:
        _LOGGER.warning("Invalid confidence value: %s", e)
        return web.json_response(
            {"success": False, "error": "Confidence must be 0.0-1.0"},
            status=400,
        )
    
    # Store in speaker cache
    try:
        speaker_cache = hass.data[DOMAIN]["speaker_cache"]
        await speaker_cache.async_put(
            speaker_id,
            confidence,
            data.get("interaction_id"),
        )
    except Exception as e:
        _LOGGER.error("Failed to store speaker cache: %s", e)
        return web.json_response(
            {"success": False, "error": "Internal error"},
            status=500,
        )
    
    # Map to HA user (create shadow user if needed)
    try:
        user_id = await _async_get_or_create_user_id(hass, speaker_id)
    except Exception as e:
        _LOGGER.error("Failed to create shadow user: %s", e)
        user_id = None
    
    return web.json_response({
        "success": True,
        "speaker_id": speaker_id,
        "user_id": user_id,
    })


async def _async_get_or_create_user_id(
    hass: HomeAssistant,
    speaker_id: str,
) -> str:
    """
    Get or create HA shadow user for a speaker.
    
    Args:
        hass: Home Assistant instance
        speaker_id: Speaker identifier
        
    Returns:
        HA user ID
    """
    user_name = f"voice_speaker_{speaker_id}"
    
    # Check if user already exists
    for user in await hass.auth.async_get_users():
        if user.name == user_name:
            return user.id
    
    # Create shadow user
    user = await hass.auth.async_create_user(
        name=user_name,
        system_generated=True,
    )
    
    _LOGGER.info("Created shadow user for speaker %s: %s", speaker_id, user.id)
    
    return user.id
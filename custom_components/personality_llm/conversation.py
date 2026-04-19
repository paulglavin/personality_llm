"""Conversation support for Local OpenAI LLM."""

import logging
from typing import Literal

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LocalAiConfigEntry
from .const import CONF_PARALLEL_TOOL_CALLS, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LocalAiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up conversation entities."""
    for subentry_id, subentry in config_entry.subentries.items():
        if subentry.subentry_type != "conversation":
            continue
        async_add_entities(
            [LocalAiConversationEntity(config_entry, subentry)],
            config_subentry_id=subentry_id,
        )


class LocalAiConversationEntity(LocalAiEntity, conversation.ConversationEntity):
    """Local OpenAI LLM conversation agent."""

    _attr_name = None
    _attr_supports_streaming = True

    def __init__(self, entry: LocalAiConfigEntry, subentry: ConfigSubentry) -> None:
        """Initialize the agent."""
        super().__init__(entry, subentry)
        if self.subentry.data.get(CONF_LLM_HASS_API):
            self._attr_supported_features = (
                conversation.ConversationEntityFeature.CONTROL
            )

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return a list of supported languages."""
        return MATCH_ALL

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Process the user input and call the API."""
        
        # ========== NEW: Speaker Resolution (Phase 1) ==========
        # Per-utterance speaker switching: cache → context → default
        
        speaker_cache = self.hass.data[DOMAIN]["speaker_cache"]
        cache_entry = await speaker_cache.async_get_recent()
        
        if cache_entry:
            # Fresh speaker from VoicePipeline (this utterance)
            speaker_id = cache_entry["speaker_id"]
            _LOGGER.debug(
                "Speaker from cache: %s (confidence=%.2f, conversation_id=%s)",
                speaker_id,
                cache_entry["confidence"],
                user_input.conversation_id,
            )
            
            # Detect speaker change in multi-turn
            if user_input.context.user_id:
                prev_speaker = self._get_speaker_from_user_id(user_input.context.user_id)
                if prev_speaker and prev_speaker != speaker_id:
                    _LOGGER.info(
                        "Speaker changed in conversation %s: %s → %s",
                        user_input.conversation_id,
                        prev_speaker,
                        speaker_id,
                    )
        
        elif user_input.context.user_id:
            # Restore speaker from previous turn
            speaker_id = self._get_speaker_from_user_id(user_input.context.user_id)
            if not speaker_id:
                speaker_id = "default"
            _LOGGER.debug(
                "Speaker from context (previous turn): %s (conversation_id=%s)",
                speaker_id,
                user_input.conversation_id,
            )
        
        else:
            # No speaker info available
            speaker_id = "default"
            _LOGGER.debug("No speaker info, using default")
        
        # Update context for next turn
        user_id = await self._get_user_id_from_speaker(speaker_id)
        # Note: context may be dataclass or dict depending on HA version
        if hasattr(user_input.context, 'as_dict'):
            user_input.context = user_input.context.as_dict()
        user_input.context["user_id"] = user_id
        
        # Load per-speaker configuration
        config_manager = self.hass.data[DOMAIN]["config_manager"]
        user_config = config_manager.get_user(speaker_id)
        
        _LOGGER.info(
            "Processing for speaker=%s, display_name=%s",
            speaker_id,
            user_config.get("display_name", "Unknown"),
        )
        
        # ========== END Speaker Resolution ==========
        
        # ========== EXISTING: Read config (MODIFIED) ==========
        options = self.subentry.data
        
        # NEW: Use per-speaker system prompt instead of global
        system_prompt = user_config["personality"]["system_prompt"]
        
        # EXISTING: parallel_tool_calls (unchanged)
        parallel_tool_calls = options.get(CONF_PARALLEL_TOOL_CALLS, True)

        # ========== EXISTING: LLM API filtering (UNCHANGED) ==========
        hass_apis = [api.id for api in llm.async_get_apis(self.hass)]

        # Filter out any tool providers that no longer exist
        llm_apis = options.get(CONF_LLM_HASS_API, [])
        llm_apis = [api for api in llm_apis if api in hass_apis]

        # ========== EXISTING: Provide LLM data (UNCHANGED) ==========
        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                llm_apis,
                system_prompt,  # ← Now per-speaker
                user_input.extra_system_prompt,
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()

        # ========== EXISTING: Handle chat log (UNCHANGED) ==========
        await self._async_handle_chat_log(
            chat_log, user_input=user_input, parallel_tool_calls=parallel_tool_calls
        )

        # ========== EXISTING: Return result (UNCHANGED) ==========
        return conversation.async_get_result_from_chat_log(user_input, chat_log)
    
    # ========== NEW: Helper Methods ==========
    
    def _get_speaker_from_user_id(self, user_id: str) -> str | None:
        """
        Map HA user_id to speaker_id.
        
        Args:
            user_id: HA user ID
            
        Returns:
            speaker_id or None if not found
        """
        # Shadow user naming pattern: voice_speaker_{speaker_id}
        try:
            for user in self.hass.auth._store._users.values():
                if user.id == user_id:
                    if user.name and user.name.startswith("voice_speaker_"):
                        return user.name.replace("voice_speaker_", "")
                    return None
        except Exception as e:
            _LOGGER.warning("Failed to map user_id to speaker: %s", e)
            return None
        
        return None
    
    async def _get_user_id_from_speaker(self, speaker_id: str) -> str:
        """
        Map speaker_id to HA user_id (create shadow user if needed).
        
        Args:
            speaker_id: Speaker identifier
            
        Returns:
            HA user ID
        """
        user_name = f"voice_speaker_{speaker_id}"
        
        # Find existing user
        for user in await self.hass.auth.async_get_users():
            if user.name == user_name:
                return user.id
        
        # Create shadow user
        user = await self.hass.auth.async_create_user(
            name=user_name,
            system_generated=True,
        )
        
        _LOGGER.info("Created shadow user for speaker %s: %s", speaker_id, user.id)
        
        return user.id
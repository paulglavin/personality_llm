"""Conversation support for Local OpenAI LLM."""
import logging
from typing import TYPE_CHECKING, Literal

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT, MATCH_ALL
from homeassistant.core import HomeAssistant, Context
from homeassistant.helpers import llm
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

if TYPE_CHECKING:
    from . import LocalAiConfigEntry

from .const import CONF_PARALLEL_TOOL_CALLS, DOMAIN
from .entity import LocalAiEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: "LocalAiConfigEntry",  # ← String literal for forward reference
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

    def __init__(self, entry: "LocalAiConfigEntry", subentry: ConfigSubentry) -> None:
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
        
        # ========== Speaker Resolution (Multi-Turn Support) ==========
        
        speaker_cache = self.hass.data[DOMAIN]["speaker_cache"]
        conversation_cache = self.hass.data[DOMAIN]["conversation_cache"]
        
        cache_entry = await speaker_cache.async_get_recent()
        speaker_from_webhook = False

        if cache_entry:
            # Fresh speaker from VoicePipeline (this utterance)
            speaker_id = cache_entry["speaker_id"]
            speaker_from_webhook = True
            _LOGGER.debug(
                "Speaker from cache: %s (confidence=%.2f, conversation_id=%s)",
                speaker_id,
                cache_entry["confidence"],
                user_input.conversation_id,
            )

        # Check conversation cache (multi-turn without fresh webhook)
        elif user_input.conversation_id:
            speaker_id = await conversation_cache.async_get(user_input.conversation_id)
            if speaker_id:
                _LOGGER.debug(
                    "Speaker from conversation history: %s (conversation_id=%s)",
                    speaker_id,
                    user_input.conversation_id,
                )
            else:
                _LOGGER.debug(
                    "No speaker in conversation cache, using default (conversation_id=%s)",
                    user_input.conversation_id,
                )
                speaker_id = "default"
        
        # No conversation context available
        else:
            speaker_id = "default"
            _LOGGER.debug("No conversation_id, using default")
        
        # Update context for HA internals (audit logs, permissions)
        user_id = await self._get_user_id_from_speaker(speaker_id)
        user_input.context = Context(
            user_id=user_id,
            parent_id=user_input.context.parent_id,
            id=user_input.context.id,
        )
        
        _LOGGER.debug("Updated context.user_id: %s", user_id)
        
        # ========== END Speaker Resolution ==========
        
        # Load per-speaker configuration
        config_manager = self.hass.data[DOMAIN]["config_manager"]
        user_config = config_manager.get_user(speaker_id)
        
        _LOGGER.info(
            "Processing for speaker=%s, display_name=%s",
            speaker_id,
            user_config.get("display_name", "Unknown"),
        )
        
        # Get configuration options
        options = self.subentry.data
        
        # Use per-speaker system prompt
        from .prompt_resolver import resolve_system_prompt

        # Retrieve global options from config entry
        opts = self.hass.config_entries.async_entries(DOMAIN)
        entry_options = opts[0].options if opts else {}
        house_model = entry_options.get("house_model_prompt", DEFAULT_HOUSE_MODEL_PROMPT)
        house_personality = entry_options.get("house_personality_prompt", DEFAULT_HOUSE_PERSONALITY_PROMPT)

        # Resolve per-user config (if feature is enabled)
        user_conf = None
        if entry_options.get("enable_per_user_personality"):
            config_manager = self.hass.data[DOMAIN]["config_manager"]
            user_conf = config_manager.get_user(speaker_id)

        # Build final system prompt using layered resolver
        system_prompt = resolve_system_prompt(
            house_model, house_personality, user_conf, entry_options
        )
        _LOGGER.debug("Resolved prompt for %s (first 100 chars): %s...", speaker_id, system_prompt[:100])
        
        parallel_tool_calls = options.get(CONF_PARALLEL_TOOL_CALLS, True)

        # Get available LLM APIs
        hass_apis = [api.id for api in llm.async_get_apis(self.hass)]

        # Filter out any tool providers that no longer exist
        llm_apis = options.get(CONF_LLM_HASS_API, [])
        llm_apis = [api for api in llm_apis if api in hass_apis]

        # Provide LLM data to chat log
        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                llm_apis,
                system_prompt,
                user_input.extra_system_prompt,
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()

        # Handle chat log (call LLM, execute tools)
        await self._async_handle_chat_log(
            chat_log, user_input=user_input, parallel_tool_calls=parallel_tool_calls
        )

        # Store speaker→conversation mapping after LLM processing: chat_log.conversation_id
        # is None at the start of turn 1 (user_input.conversation_id is also None), but HA
        # assigns it during chat log processing, so it's available here.
        if speaker_from_webhook:
            conv_id = user_input.conversation_id or chat_log.conversation_id
            if conv_id:
                await conversation_cache.async_put(conv_id, speaker_id)
                _LOGGER.debug("Stored speaker %s for conversation %s", speaker_id, conv_id)

        # Return result
        return conversation.async_get_result_from_chat_log(user_input, chat_log)
    
    # ========== Helper Methods for Speaker Management ==========
    
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
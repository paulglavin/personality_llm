"""Conversation support for Local OpenAI LLM."""

from typing import Literal

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LocalAiConfigEntry
from .const import CONF_PARALLEL_TOOL_CALLS, DOMAIN
from .entity import LocalAiEntity


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
        
        
        # TODO(PHASE1-VALIDATION-Q1): Log user_input fields here to validate speaker identity source
        # See: docs/VALIDATION_LOG.md Q1
        # Expected fields: device_id, context.user_id, conversation_id

        """Process the user input and call the API."""
        options = self.subentry.data
        
        # TODO(PHASE1-INJECTION): After validation, inject speaker resolution here
        # speaker_id = user_input.device_id or user_input.context.user_id
        # speaker_profile = await self._get_speaker_profile(speaker_id)

        system_prompt = options.get(CONF_PROMPT)
        
        # TODO(PHASE1-VALIDATION-Q2): Log system_prompt value to validate single injection point
        # See: docs/VALIDATION_LOG.md Q2
    
        # TODO(PHASE1-INJECTION): After validation, replace with per-speaker prompt
        # system_prompt = speaker_profile.prompt if speaker_profile else system_prompt

        parallel_tool_calls = options.get(CONF_PARALLEL_TOOL_CALLS, True)

        hass_apis = [api.id for api in llm.async_get_apis(self.hass)]

        # Filter out any tool providers that no longer exist
        llm_apis = options.get(CONF_LLM_HASS_API, [])
        llm_apis = [api for api in llm_apis if api in hass_apis]

        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                llm_apis,
                system_prompt,
                user_input.extra_system_prompt,
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()

        await self._async_handle_chat_log(
            chat_log, user_input=user_input, parallel_tool_calls=parallel_tool_calls
        )

        # TODO(PHASE1-VALIDATION-Q4): Log user_input.tts_options before building result
        # See: docs/VALIDATION_LOG.md Q4
    
        # TODO(PHASE1-INJECTION): After validation, inject per-speaker TTS voice
        # if speaker_profile and speaker_profile.tts_voice:
        #     user_input.tts_options = {**(user_input.tts_options or {}), "voice": speaker_profile.tts_voice}

        return conversation.async_get_result_from_chat_log(user_input, chat_log)

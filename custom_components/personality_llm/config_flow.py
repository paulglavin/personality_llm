"""Config flow for Local OpenAI LLM integration."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API, CONF_MODEL, CONF_PROMPT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import SectionConfig, section
from homeassistant.helpers import llm
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    ObjectSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TemplateSelector,
    TextSelector,
    TextSelectorConfig,
)
from openai import AsyncOpenAI, OpenAIError

from .const import (
    ADDRESS_STYLE_OPTIONS,
    CONF_ADDRESS_STYLE,
    CONF_AI_TASK_SUPPORTED_ATTRIBUTES,
    CONF_AI_TASK_TOOLS_SECTION,
    CONF_ASSISTANT_NAME,
    CONF_BASE_URL,
    CONF_CHAT_TEMPLATE_KWARGS,
    CONF_CHAT_TEMPLATE_OPTS,
    CONF_CONTENT_INJECTION_METHOD,
    CONF_CONTENT_INJECTION_METHODS,
    CONF_ENABLE_SMART_DISCOVERY,
    DEFAULT_ENABLE_SMART_DISCOVERY,
    CONF_HUMOR_LEVEL,
    CONF_MAX_MESSAGE_HISTORY,
    CONF_PARALLEL_TOOL_CALLS,
    CONF_PERSONAL_CONTEXT,
    CONF_PERSONALITY_STYLE,
    CONF_RESPONSE_STYLE,
    CONF_SERVER_NAME,
    CONF_STRIP_EMOJIS,
    CONF_TEMPERATURE,
    CONF_WEAVIATE_API_KEY,
    CONF_WEAVIATE_CLASS_NAME,
    CONF_WEAVIATE_DEFAULT_CLASS_NAME,
    CONF_WEAVIATE_DEFAULT_HYBRID_SEARCH_ALPHA,
    CONF_WEAVIATE_DEFAULT_MAX_RESULTS,
    CONF_WEAVIATE_DEFAULT_THRESHOLD,
    CONF_WEAVIATE_HOST,
    CONF_WEAVIATE_HYBRID_SEARCH_ALPHA,
    CONF_WEAVIATE_MAX_RESULTS,
    CONF_WEAVIATE_MAX_RESULTS_MAX,
    CONF_WEAVIATE_OPTIONS,
    CONF_WEAVIATE_THRESHOLD,
    DEFAULT_ADDRESS_STYLE,
    DEFAULT_ASSISTANT_NAME,
    USER_STYLE_INHERIT,
    DEFAULT_HOUSE_MODEL_PROMPT,
    DEFAULT_HOUSE_PERSONALITY_PROMPT,
    DEFAULT_HUMOR_LEVEL,
    DEFAULT_PERSONALITY_STYLE,
    DEFAULT_RESPONSE_STYLE,
    DOMAIN,
    HUMOR_LEVEL_OPTIONS,
    LOGGER,
    PERSONAL_CONTEXT_MAX_LENGTH,
    PERSONALITY_STYLE_OPTIONS,
    RECOMMENDED_CONVERSATION_OPTIONS,
    RESPONSE_STYLE_OPTIONS,
)
from .user_config import UserConfigManager
from .weaviate import WeaviateClient, WeaviateError


# ---------------------------------------------------------------------------
# Selector option lists — value keys match const.py, labels are display strings.
# Hard-coded English labels are intentional for a custom component; i18n can be
# layered in later via HA's selector translation mechanism if needed.
# ---------------------------------------------------------------------------
_PERSONALITY_STYLE_OPTIONS: list[SelectOptionDict] = [
    SelectOptionDict(value=v, label=l)
    for v, l in zip(
        PERSONALITY_STYLE_OPTIONS,
        ["Friendly", "Professional", "Witty", "Sarcastic", "Playful", "Concise", "Custom (advanced)"],
    )
]
_HUMOR_LEVEL_OPTIONS: list[SelectOptionDict] = [
    SelectOptionDict(value=v, label=l)
    for v, l in zip(HUMOR_LEVEL_OPTIONS, ["None", "Subtle", "Moderate", "Generous"])
]
_RESPONSE_STYLE_OPTIONS: list[SelectOptionDict] = [
    SelectOptionDict(value=v, label=l)
    for v, l in zip(
        RESPONSE_STYLE_OPTIONS,
        ["Conversational", "Formal", "Brief", "Detailed"],
    )
]
_ADDRESS_STYLE_OPTIONS: list[SelectOptionDict] = [
    SelectOptionDict(value=v, label=l)
    for v, l in zip(
        ADDRESS_STYLE_OPTIONS,
        ["Always by name", "Casually", "Formal", "Custom (advanced)"],
    )
]

# Per-user variants — same options with "Use house default" prepended.
_inherit = SelectOptionDict(value=USER_STYLE_INHERIT, label="Use house default")
_USER_PERSONALITY_STYLE_OPTIONS = [_inherit, *_PERSONALITY_STYLE_OPTIONS]
_USER_HUMOR_LEVEL_OPTIONS = [_inherit, *_HUMOR_LEVEL_OPTIONS]
_USER_RESPONSE_STYLE_OPTIONS = [_inherit, *_RESPONSE_STYLE_OPTIONS]


async def prepare_weaviate_class(hass: HomeAssistant, weaviate_opts: dict[str, Any]):
    """Prepare our object class."""
    host = weaviate_opts.get(CONF_WEAVIATE_HOST)
    if not host:
        # Just pass if we dont have a weaviate host defined
        return

    weaviate = WeaviateClient(
        hass=hass,
        host=host,
        api_key=weaviate_opts.get(CONF_WEAVIATE_API_KEY),
    )

    class_name = weaviate_opts.get(
        CONF_WEAVIATE_CLASS_NAME, CONF_WEAVIATE_DEFAULT_CLASS_NAME
    )

    # if the class already exists, we're good
    if await weaviate.does_class_exist(class_name):
        return

    await weaviate.create_class(class_name)
    LOGGER.debug("Weaviate connectivity confirmed and class is prepared")


def options_to_selections_dict(opts: dict) -> list[SelectOptionDict]:
    """Convert a dict to a list of select options."""
    return [SelectOptionDict(value=key, label=opts[key]) for key in opts]


class LocalAiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Local OpenAI LLM."""

    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this handler."""
        return {
            "conversation": ConversationFlowHandler,
            "ai_task_data": AITaskDataFlowHandler,
        }

    @staticmethod
    def get_schema():
        return vol.Schema(
            {
                vol.Required(
                    CONF_SERVER_NAME,
                    default="Local LLM Server",
                ): str,
                vol.Required(CONF_BASE_URL, default=""): str,
                vol.Optional(CONF_API_KEY, default=""): str,
                vol.Optional(CONF_WEAVIATE_OPTIONS): section(
                    schema=vol.Schema(
                        schema={
                            vol.Optional(
                                CONF_WEAVIATE_HOST,
                                default="",
                            ): str,
                            vol.Optional(
                                CONF_WEAVIATE_API_KEY,
                                default="",
                            ): str,
                        }
                    ),
                    options={"collapsed": True},
                ),
            }
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            self._async_abort_entries_match(user_input)
            LOGGER.debug(
                f"Initialising OpenAI client with base_url: {user_input[CONF_BASE_URL]}"
            )

            try:
                client = AsyncOpenAI(
                    base_url=user_input.get(CONF_BASE_URL),
                    api_key=user_input.get(CONF_API_KEY, ""),
                    http_client=get_async_client(self.hass),
                )

                LOGGER.debug("Retrieving model list to ensure server is accessible")
                await client.models.list()

                # Test connectivity with Weaviate
                await prepare_weaviate_class(
                    hass=self.hass,
                    weaviate_opts=user_input.get(CONF_WEAVIATE_OPTIONS, {}),
                )
            except WeaviateError as err:
                LOGGER.exception(f"Unexpected exception: {err}")
                errors["base"] = "cannot_connect_weaviate"
            except OpenAIError as err:
                LOGGER.exception(f"OpenAI Error: {err}")
                errors["base"] = "cannot_connect"
            except Exception as err:
                LOGGER.exception(f"Unexpected exception: {err}")
                errors["base"] = "unknown"
            else:
                LOGGER.debug("Server connection verified")

                return self.async_create_entry(
                    title=f"{user_input.get(CONF_SERVER_NAME, 'Local LLM Server')}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.get_schema(),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """User flow to create a sensor subentry."""
        errors = {}
        if user_input is not None:
            self._async_abort_entries_match(user_input)
            LOGGER.debug(
                f"Initialising OpenAI client with base_url: {user_input[CONF_BASE_URL]}"
            )

            try:
                client = AsyncOpenAI(
                    base_url=user_input.get(CONF_BASE_URL),
                    api_key=user_input.get(CONF_API_KEY, ""),
                    http_client=get_async_client(self.hass),
                )

                LOGGER.debug("Retrieving model list to ensure server is accessible")
                await client.models.list()

                # Test connectivity with Weaviate
                await prepare_weaviate_class(
                    hass=self.hass,
                    weaviate_opts=user_input.get(CONF_WEAVIATE_OPTIONS, {}),
                )
            except WeaviateError as err:
                LOGGER.exception(f"Unexpected exception: {err}")
                errors["base"] = "cannot_connect_weaviate"
            except OpenAIError as err:
                LOGGER.exception(f"OpenAI Error: {err}")
                errors["base"] = "cannot_connect"
            except Exception as err:
                LOGGER.exception(f"Unexpected exception: {err}")
                errors["base"] = "unknown"
            else:
                LOGGER.debug("Server connection verified")

                return self.async_update_reload_and_abort(
                    entry=self._get_reconfigure_entry(),
                    title=f"{user_input.get(CONF_SERVER_NAME, 'Local LLM Server')}",
                    data=user_input,
                )

        options = self._get_reconfigure_entry().data.copy()
        schema = self.add_suggested_values_to_schema(self.get_schema(), options)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )

    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Return the options flow handler for this integration."""
        return PersonalityLLMOptionsFlowHandler()

class LocalAiSubentryFlowHandler(ConfigSubentryFlow):
    """Handle subentry flow for Local OpenAI LLM."""

    def get_llm_apis(self) -> list[SelectOptionDict]:
        return [
            SelectOptionDict(
                label=api.name,
                value=api.id,
            )
            for api in llm.async_get_apis(self.hass)
        ]

    @staticmethod
    def strip_model_pathing(model_name: str) -> str:
        """llama.cpp at the very least will keep the full model file path supplied from the CLI so lets look to strip that and any .gguf extension."""
        matches = re.search(r"([^\/]*)\.gguf$", model_name.strip())
        return matches[1] if matches else model_name


class ConversationFlowHandler(LocalAiSubentryFlowHandler):
    """Handle subentry flow."""

    async def get_schema(self):
        llm_apis = self.get_llm_apis()
        entry = self._get_entry()
        client = entry.runtime_data

        try:
            response = await client.models.list()
            downloaded_models: list[SelectOptionDict] = [
                SelectOptionDict(
                    label=model.id,
                    value=model.id,
                )
                for model in response.data
            ]
        except OpenAIError as err:
            LOGGER.exception(f"OpenAI Error retrieving models list: {err}")
            downloaded_models = []
        except Exception as err:
            LOGGER.exception(f"Unexpected exception retrieving models list: {err}")
            downloaded_models = []

        schema = {
            vol.Required(
                CONF_MODEL,
            ): SelectSelector(
                SelectSelectorConfig(options=downloaded_models, custom_value=True)
            ),
            vol.Optional(
                CONF_PROMPT,
                default=RECOMMENDED_CONVERSATION_OPTIONS[CONF_PROMPT],
            ): TemplateSelector(),
            vol.Optional(
                CONF_LLM_HASS_API,
                default=RECOMMENDED_CONVERSATION_OPTIONS[CONF_LLM_HASS_API],
            ): SelectSelector(SelectSelectorConfig(options=llm_apis, multiple=True)),
            vol.Required(
                CONF_PARALLEL_TOOL_CALLS,
                default=True,
            ): bool,
            vol.Required(
                CONF_ENABLE_SMART_DISCOVERY,
                default=DEFAULT_ENABLE_SMART_DISCOVERY,
            ): bool,
            vol.Required(
                CONF_STRIP_EMOJIS,
                default=False,
            ): bool,
            vol.Required(
                CONF_TEMPERATURE,
                default=0.6,
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=1, step=0.01, mode=NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_MAX_MESSAGE_HISTORY,
                default=0,
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=50,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_CONTENT_INJECTION_METHOD,
            ): SelectSelector(
                SelectSelectorConfig(
                    mode=SelectSelectorMode.DROPDOWN,
                    options=CONF_CONTENT_INJECTION_METHODS,
                )
            ),
            vol.Required(CONF_CHAT_TEMPLATE_OPTS): section(
                options=SectionConfig(collapsed=True),
                schema=vol.Schema(
                    schema={
                        vol.Required(
                            CONF_CHAT_TEMPLATE_KWARGS, default=[]
                        ): ObjectSelector(
                            config={
                                "multiple": True,
                                "fields": {
                                    "Name": {
                                        "selector": {"text": None},
                                        "required": True,
                                    },
                                    "Value": {
                                        "selector": {"template": None},
                                        "required": True,
                                    },
                                },
                            }
                        ),
                    }
                ),
            ),
        }

        if entry.data.get(CONF_WEAVIATE_OPTIONS, {}).get(CONF_WEAVIATE_HOST):
            schema = {
                **schema,
                vol.Optional(CONF_WEAVIATE_OPTIONS): section(
                    schema=vol.Schema(
                        schema={
                            vol.Optional(
                                CONF_WEAVIATE_CLASS_NAME,
                                default=CONF_WEAVIATE_DEFAULT_CLASS_NAME,
                            ): str,
                            vol.Optional(
                                CONF_WEAVIATE_MAX_RESULTS,
                                default=CONF_WEAVIATE_DEFAULT_MAX_RESULTS,
                            ): NumberSelector(
                                NumberSelectorConfig(
                                    min=1,
                                    max=CONF_WEAVIATE_MAX_RESULTS_MAX,
                                    step=1,
                                    mode=NumberSelectorMode.SLIDER,
                                )
                            ),
                            vol.Optional(
                                CONF_WEAVIATE_THRESHOLD,
                                default=CONF_WEAVIATE_DEFAULT_THRESHOLD,
                            ): NumberSelector(
                                NumberSelectorConfig(
                                    min=0,
                                    max=1,
                                    step=0.01,
                                    mode=NumberSelectorMode.SLIDER,
                                )
                            ),
                            vol.Optional(
                                CONF_WEAVIATE_HYBRID_SEARCH_ALPHA,
                                default=CONF_WEAVIATE_DEFAULT_HYBRID_SEARCH_ALPHA,
                            ): NumberSelector(
                                NumberSelectorConfig(
                                    min=0,
                                    max=1,
                                    step=0.01,
                                    mode=NumberSelectorMode.SLIDER,
                                )
                            ),
                        }
                    ),
                    options=SectionConfig(collapsed=True),
                ),
            }

        return vol.Schema(schema)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """User flow to create a sensor subentry."""
        errors = {}

        if user_input is not None:
            if not user_input.get(CONF_LLM_HASS_API):
                user_input.pop(CONF_LLM_HASS_API, None)
            model_name = self.strip_model_pathing(user_input.get(CONF_MODEL, "Local"))

            try:
                weaviate_opts = {
                    **self._get_entry().data.get(CONF_WEAVIATE_OPTIONS, {}),
                    **user_input.get(CONF_WEAVIATE_OPTIONS, {}),
                }
                await prepare_weaviate_class(
                    hass=self.hass,
                    weaviate_opts=weaviate_opts,
                )
            except WeaviateError as err:
                LOGGER.exception(f"Unexpected exception: {err}")
                errors["base"] = "cannot_connect_weaviate"
            else:
                return self.async_create_entry(
                    title=f"{model_name} AI Agent", data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=await self.get_schema(),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """User flow to create a sensor subentry."""
        errors = {}

        if user_input is not None:
            if not user_input.get(CONF_LLM_HASS_API):
                user_input.pop(CONF_LLM_HASS_API, None)

            try:
                weaviate_opts = {
                    **self._get_entry().data.get(CONF_WEAVIATE_OPTIONS, {}),
                    **user_input.get(CONF_WEAVIATE_OPTIONS, {}),
                }
                await prepare_weaviate_class(
                    hass=self.hass,
                    weaviate_opts=weaviate_opts,
                )
            except WeaviateError as err:
                LOGGER.exception(f"Unexpected exception: {err}")
                errors["base"] = "cannot_connect_weaviate"
            else:
                return self.async_update_and_abort(
                    self._get_entry(),
                    self._get_reconfigure_subentry(),
                    data=user_input,
                )

        options = self._get_reconfigure_subentry().data.copy()

        # Filter out any tool providers that no longer exist
        llm_apis = [api.id for api in llm.async_get_apis(self.hass)]

        options[CONF_LLM_HASS_API] = [
            api for api in options.get(CONF_LLM_HASS_API, []) if api in llm_apis
        ]

        schema = self.add_suggested_values_to_schema(await self.get_schema(), options)

        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )


class AITaskDataFlowHandler(LocalAiSubentryFlowHandler):
    """Handle subentry flow."""

    async def get_schema(self):
        try:
            client = self._get_entry().runtime_data
            response = await client.models.list()
            downloaded_models: list[SelectOptionDict] = [
                SelectOptionDict(
                    label=model.id,
                    value=model.id,
                )
                for model in response.data
            ]
        except OpenAIError as err:
            LOGGER.exception(f"OpenAI Error retrieving models list: {err}")
            downloaded_models = []
        except Exception as err:
            LOGGER.exception(f"Unexpected exception retrieving models list: {err}")
            downloaded_models = []

        llm_apis = self.get_llm_apis()

        return vol.Schema(
            {
                vol.Required(
                    CONF_MODEL,
                ): SelectSelector(
                    SelectSelectorConfig(options=downloaded_models, custom_value=True)
                ),
                vol.Required(
                    CONF_AI_TASK_SUPPORTED_ATTRIBUTES,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "generate_data", "label": "Generate Data"},
                            {"value": "generate_image", "label": "Generate Image"},
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(CONF_AI_TASK_TOOLS_SECTION): section(
                    options=SectionConfig(collapsed=True),
                    schema=vol.Schema(
                        schema={
                            vol.Optional(
                                CONF_LLM_HASS_API,
                                default=[],
                            ): SelectSelector(
                                SelectSelectorConfig(options=llm_apis, multiple=True)
                            ),
                            vol.Required(
                                CONF_PARALLEL_TOOL_CALLS,
                                default=True,
                            ): bool,
                        }
                    ),
                ),
            }
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """User flow to create a sensor subentry."""
        if user_input is not None:
            model_name = self.strip_model_pathing(user_input.get(CONF_MODEL, "Local"))
            return self.async_create_entry(
                title=f"{model_name} AI Task", data=user_input
            )

        schema = await self.get_schema()
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """User flow to create a sensor subentry."""
        errors = {}
        if user_input is not None:
            return self.async_update_and_abort(
                entry=self._get_entry(),
                subentry=self._get_reconfigure_subentry(),
                data=user_input,
            )

        options = self._get_reconfigure_subentry().data.copy()
        schema = self.add_suggested_values_to_schema(await self.get_schema(), options)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )
    
class PersonalityLLMOptionsFlowHandler(OptionsFlow):
    """Handle options flow for personality_llm."""

    async def _get_config_manager(self) -> UserConfigManager:
        """Return the live config manager, or a freshly loaded fallback."""
        if hasattr(self, "_config_manager"):
            return self._config_manager
        cm = self.hass.data.get(DOMAIN, {}).get("config_manager")
        if cm is None:
            cm = UserConfigManager(self.hass)
            await cm.async_load()
        self._config_manager = cm
        return cm

    async def async_step_init(self, user_input=None):
        """Step 1: House-level personality and capability toggles."""
        self._selected_user = None
        if user_input is not None:
            if not user_input.get("enable_per_user_personality"):
                user_input["allow_personality_override"] = False
                user_input["allow_full_prompt_override"] = False
            # Flatten the advanced section back to the top level so the rest of
            # the integration can read house_model_prompt / house_personality_prompt
            # from entry.options directly (no nested dict).
            advanced = user_input.pop("advanced_prompts", {}) or {}
            user_input["house_model_prompt"] = advanced.get(
                "house_model_prompt", DEFAULT_HOUSE_MODEL_PROMPT
            )
            user_input["house_personality_prompt"] = advanced.get(
                "house_personality_prompt", DEFAULT_HOUSE_PERSONALITY_PROMPT
            )
            self._house_options = user_input
            if user_input.get("enable_per_user_personality"):
                return await self.async_step_user_select()
            return self.async_create_entry(title="", data=user_input)

        opts = {**self.config_entry.options} if self.config_entry.options else {}

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_ASSISTANT_NAME,
                    default=opts.get(CONF_ASSISTANT_NAME, DEFAULT_ASSISTANT_NAME),
                ): str,
                vol.Optional(
                    CONF_PERSONALITY_STYLE,
                    default=opts.get(CONF_PERSONALITY_STYLE, DEFAULT_PERSONALITY_STYLE),
                ): SelectSelector(SelectSelectorConfig(
                    mode=SelectSelectorMode.DROPDOWN,
                    options=_PERSONALITY_STYLE_OPTIONS,
                )),
                vol.Optional(
                    CONF_HUMOR_LEVEL,
                    default=opts.get(CONF_HUMOR_LEVEL, DEFAULT_HUMOR_LEVEL),
                ): SelectSelector(SelectSelectorConfig(
                    mode=SelectSelectorMode.DROPDOWN,
                    options=_HUMOR_LEVEL_OPTIONS,
                )),
                vol.Optional(
                    CONF_RESPONSE_STYLE,
                    default=opts.get(CONF_RESPONSE_STYLE, DEFAULT_RESPONSE_STYLE),
                ): SelectSelector(SelectSelectorConfig(
                    mode=SelectSelectorMode.DROPDOWN,
                    options=_RESPONSE_STYLE_OPTIONS,
                )),
                vol.Optional(
                    "enable_per_user_personality",
                    default=opts.get("enable_per_user_personality", False),
                ): bool,
                vol.Optional(
                    "allow_personality_override",
                    default=opts.get("allow_personality_override", False),
                ): bool,
                vol.Optional(
                    "allow_full_prompt_override",
                    default=opts.get("allow_full_prompt_override", False),
                ): bool,
                vol.Optional("advanced_prompts"): section(
                    schema=vol.Schema({
                        vol.Required(
                            "house_model_prompt",
                            default=opts.get("house_model_prompt", DEFAULT_HOUSE_MODEL_PROMPT),
                        ): TextSelector(TextSelectorConfig(multiline=True)),
                        vol.Required(
                            "house_personality_prompt",
                            default=opts.get("house_personality_prompt", DEFAULT_HOUSE_PERSONALITY_PROMPT),
                        ): TextSelector(TextSelectorConfig(multiline=True)),
                    }),
                    options=SectionConfig(collapsed=True),
                ),
            }),
        )

    async def async_step_user_select(self, user_input=None):
        """Step 2: Select an existing user or type a new speaker ID to configure."""
        config_manager = await self._get_config_manager()
        existing_users = sorted(u for u in config_manager.list_users() if u != "default")
        errors = {}

        if user_input is not None:
            choice = (user_input.get("selected_user") or "").strip().lower()
            if not choice:
                return self.async_create_entry(
                    title="", data=getattr(self, "_house_options", {})
                )
            if not re.match(r"^[a-z0-9_]{1,50}$", choice):
                errors["selected_user"] = "invalid_speaker_id"
            else:
                self._selected_user = choice
                return await self.async_step_user_personality()

        options = [
            SelectOptionDict(
                value=u,
                label=f"{u} — {config_manager.get_user(u).get('display_name', u)}",
            )
            for u in existing_users
        ]

        return self.async_show_form(
            step_id="user_select",
            data_schema=vol.Schema({
                vol.Optional("selected_user"): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        custom_value=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
            errors=errors,
            description_placeholders={"configured": str(len(existing_users))},
        )

    async def async_step_user_personality(self, user_input=None):
        """Step 3: Configure a specific user's personality."""
        config_manager = await self._get_config_manager()
        errors: dict[str, str] = {}

        if user_input is not None:
            personal_context = (user_input.get(CONF_PERSONAL_CONTEXT) or "").strip()
            if len(personal_context) > PERSONAL_CONTEXT_MAX_LENGTH:
                errors[CONF_PERSONAL_CONTEXT] = "personal_context_too_long"

            if not errors:
                advanced = user_input.pop("advanced_prompts", {}) or {}
                new_conf = {
                    "display_name": user_input.get("display_name", "").strip() or self._selected_user,
                    "pronouns": (user_input.get("pronouns") or "").strip(),
                    CONF_PERSONALITY_STYLE: user_input.get(CONF_PERSONALITY_STYLE, USER_STYLE_INHERIT),
                    CONF_HUMOR_LEVEL: user_input.get(CONF_HUMOR_LEVEL, USER_STYLE_INHERIT),
                    CONF_RESPONSE_STYLE: user_input.get(CONF_RESPONSE_STYLE, USER_STYLE_INHERIT),
                    CONF_ADDRESS_STYLE: user_input.get(CONF_ADDRESS_STYLE, DEFAULT_ADDRESS_STYLE),
                    CONF_PERSONAL_CONTEXT: personal_context,
                    "personality_prompt": advanced.get("personality_prompt", ""),
                    "override_house_personality": advanced.get("override_house_personality", False),
                    "personality_override_prompt": advanced.get("personality_override_prompt", ""),
                    "full_prompt_override": advanced.get("full_prompt_override", ""),
                }
                await config_manager.async_add_user(self._selected_user, new_conf)
                return await self.async_step_user_select()

        existing = config_manager.get_user(self._selected_user) or {}
        defaults = {
            "display_name": existing.get("display_name", self._selected_user),
            "pronouns": existing.get("pronouns", ""),
            CONF_PERSONALITY_STYLE: existing.get(CONF_PERSONALITY_STYLE, USER_STYLE_INHERIT),
            CONF_HUMOR_LEVEL: existing.get(CONF_HUMOR_LEVEL, USER_STYLE_INHERIT),
            CONF_RESPONSE_STYLE: existing.get(CONF_RESPONSE_STYLE, USER_STYLE_INHERIT),
            CONF_ADDRESS_STYLE: existing.get(CONF_ADDRESS_STYLE, DEFAULT_ADDRESS_STYLE),
            CONF_PERSONAL_CONTEXT: existing.get(CONF_PERSONAL_CONTEXT, ""),
            "personality_prompt": existing.get("personality_prompt", ""),
            "override_house_personality": existing.get("override_house_personality", False),
            "personality_override_prompt": existing.get("personality_override_prompt", ""),
            "full_prompt_override": existing.get("full_prompt_override", ""),
        }

        # Use in-progress house options for capability flag checks
        pending_opts = getattr(self, "_house_options", self.config_entry.options or {})

        # Build advanced section — raw prompt escape hatch for power users
        advanced_fields: dict = {
            vol.Optional(
                "personality_prompt", default=defaults["personality_prompt"]
            ): TextSelector(TextSelectorConfig(multiline=True)),
        }
        if pending_opts.get("allow_personality_override"):
            advanced_fields[
                vol.Optional("override_house_personality", default=defaults["override_house_personality"])
            ] = bool
            advanced_fields[
                vol.Optional("personality_override_prompt", default=defaults["personality_override_prompt"])
            ] = TextSelector(TextSelectorConfig(multiline=True))
        if pending_opts.get("allow_full_prompt_override"):
            advanced_fields[
                vol.Optional("full_prompt_override", default=defaults["full_prompt_override"])
            ] = TextSelector(TextSelectorConfig(multiline=True))

        return self.async_show_form(
            step_id="user_personality",
            data_schema=vol.Schema({
                vol.Optional("display_name", default=defaults["display_name"]): str,
                vol.Optional("pronouns", default=defaults["pronouns"]): str,
                vol.Optional(
                    CONF_PERSONALITY_STYLE, default=defaults[CONF_PERSONALITY_STYLE]
                ): SelectSelector(SelectSelectorConfig(
                    mode=SelectSelectorMode.DROPDOWN,
                    options=_USER_PERSONALITY_STYLE_OPTIONS,
                )),
                vol.Optional(
                    CONF_HUMOR_LEVEL, default=defaults[CONF_HUMOR_LEVEL]
                ): SelectSelector(SelectSelectorConfig(
                    mode=SelectSelectorMode.DROPDOWN,
                    options=_USER_HUMOR_LEVEL_OPTIONS,
                )),
                vol.Optional(
                    CONF_RESPONSE_STYLE, default=defaults[CONF_RESPONSE_STYLE]
                ): SelectSelector(SelectSelectorConfig(
                    mode=SelectSelectorMode.DROPDOWN,
                    options=_USER_RESPONSE_STYLE_OPTIONS,
                )),
                vol.Optional(
                    CONF_ADDRESS_STYLE, default=defaults[CONF_ADDRESS_STYLE]
                ): SelectSelector(SelectSelectorConfig(
                    mode=SelectSelectorMode.DROPDOWN,
                    options=_ADDRESS_STYLE_OPTIONS,
                )),
                vol.Optional(
                    CONF_PERSONAL_CONTEXT, default=defaults[CONF_PERSONAL_CONTEXT]
                ): TextSelector(TextSelectorConfig(multiline=True)),
                vol.Optional("advanced_prompts"): section(
                    schema=vol.Schema(advanced_fields),
                    options=SectionConfig(collapsed=True),
                ),
            }),
            description_placeholders={"user": self._selected_user},
            errors=errors,
        )
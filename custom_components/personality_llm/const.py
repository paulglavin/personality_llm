"""Constants for the Personality LLM integration."""

import logging

from homeassistant.components import ai_task
from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT
from homeassistant.helpers import llm

DOMAIN = "personality_llm"
LOGGER = logging.getLogger(__package__)

CONF_RECOMMENDED = "recommended"
CONF_BASE_URL = "base_url"
CONF_SERVER_NAME = "server_name"
CONF_STRIP_EMOJIS = "strip_emojis"
CONF_MAX_MESSAGE_HISTORY = "max_message_history"
CONF_TEMPERATURE = "temperature"
CONF_PARALLEL_TOOL_CALLS = "parallel_tool_calls"
CONF_CHAT_TEMPLATE_OPTS = "chat_template_opts"
CONF_CHAT_TEMPLATE_KWARGS = "chat_template_kwargs"

CONF_AI_TASK_SUPPORTED_ATTRIBUTES = "supported_attributes"
CONF_AI_TASK_SUPPORTED_ATTRIBUTE_OPTIONS = {
    "generate_data": ai_task.AITaskEntityFeature.GENERATE_DATA
    | ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS,
    "generate_image": ai_task.AITaskEntityFeature.GENERATE_IMAGE,
}

CONF_AI_TASK_TOOLS_SECTION = "tooling"

CONF_CONTENT_INJECTION_METHOD_SYSTEM = "System"
CONF_CONTENT_INJECTION_METHOD_ASSISTANT = "Assistant"
CONF_CONTENT_INJECTION_METHOD_USER = "User"
CONF_CONTENT_INJECTION_METHOD_TOOL = "Tool Result"

CONF_CONTENT_INJECTION_METHOD = "content_injection_method"
CONF_CONTENT_INJECTION_METHODS = [
    CONF_CONTENT_INJECTION_METHOD_TOOL,
    CONF_CONTENT_INJECTION_METHOD_ASSISTANT,
    CONF_CONTENT_INJECTION_METHOD_USER,
]

CONF_WEAVIATE_OPTIONS = "weaviate_options"
CONF_WEAVIATE_HOST = "weaviate_host"
CONF_WEAVIATE_API_KEY = "weaviate_api_key"
CONF_WEAVIATE_CLASS_NAME = "weaviate_class_name"
CONF_WEAVIATE_MAX_RESULTS = "weaviate_max_results"
CONF_WEAVIATE_THRESHOLD = "weaviate_threshold"
CONF_WEAVIATE_HYBRID_SEARCH_ALPHA = "weaviate_hybrid_search_alpha"

CONF_WEAVIATE_DEFAULT_CLASS_NAME = "Homeassistant"
CONF_WEAVIATE_DEFAULT_THRESHOLD = 0.9
CONF_WEAVIATE_DEFAULT_MAX_RESULTS = 2
CONF_WEAVIATE_DEFAULT_HYBRID_SEARCH_ALPHA = 0.5
CONF_WEAVIATE_MAX_RESULTS_MAX = 10

RECOMMENDED_CONVERSATION_OPTIONS = {
    CONF_RECOMMENDED: True,
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
}

# Storage
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_users"

# Webhook
WEBHOOK_ID = f"{DOMAIN}_input"
CONF_WEBHOOK_SECRET = "webhook_secret"

# Default user configuration
DEFAULT_USER_CONFIG = {
    "display_name": "Guest",
    "personality": {
        "system_prompt": (
            "You are a helpful, polite assistant. "
            "Keep responses concise (under 3 sentences) unless asked for detail."
        ),
        "temperature": 0.7,
        "max_tokens": 150,
    },
    "llm": {
        "provider": "ollama",
        "model": "gpt-oss-20b",
        "api_url": "http://localhost:11434/v1",
        "api_key": "",
        "fallback_provider": "ollama",
        "fallback_model": "gpt-oss-20b",
    },
    "tts": {
        # Deferred to Phase 4, but include schema now
        "engine": "tts.piper",
        "voice": "en_US-ryan-medium",
        "speed": 1.0,
        "pitch": 0,
    },
}

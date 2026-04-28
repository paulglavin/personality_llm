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

# Smart Discovery (Phase 0)
CONF_ENABLE_SMART_DISCOVERY = "enable_smart_discovery"
CONF_MAX_ENTITIES_PER_DISCOVERY = "max_entities_per_discovery"
DEFAULT_ENABLE_SMART_DISCOVERY = False
DEFAULT_MAX_ENTITIES_PER_DISCOVERY = 50
SMART_DISCOVERY_API_ID = "personality_llm_smart_discovery"
CONF_MUSIC_SCRIPT = "music_script"

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

# ---------------------------------------------------------------------------
# Structured personality configuration
# ---------------------------------------------------------------------------
# Field-name constants
CONF_ASSISTANT_NAME = "assistant_name"
CONF_PERSONALITY_STYLE = "personality_style"
CONF_HUMOR_LEVEL = "humor_level"
CONF_RESPONSE_STYLE = "response_style"
CONF_ADDRESS_STYLE = "address_style"
CONF_PERSONAL_CONTEXT = "personal_context"

# Soft cap on free-text "about you" — discourages users dumping prompt-engineered
# text into a field that's framed to the model as user-supplied background.
PERSONAL_CONTEXT_MAX_LENGTH = 500

# Sentinel used in per-user style fields to mean "inherit from house settings".
USER_STYLE_INHERIT = "inherit"

# personality_style ---------------------------------------------------------
PERSONALITY_STYLE_FRIENDLY = "friendly"
PERSONALITY_STYLE_PROFESSIONAL = "professional"
PERSONALITY_STYLE_WITTY = "witty"
PERSONALITY_STYLE_SARCASTIC = "sarcastic"
PERSONALITY_STYLE_PLAYFUL = "playful"
PERSONALITY_STYLE_CONCISE = "concise"
PERSONALITY_STYLE_CUSTOM = "custom"

PERSONALITY_STYLE_OPTIONS = [
    PERSONALITY_STYLE_FRIENDLY,
    PERSONALITY_STYLE_PROFESSIONAL,
    PERSONALITY_STYLE_WITTY,
    PERSONALITY_STYLE_SARCASTIC,
    PERSONALITY_STYLE_PLAYFUL,
    PERSONALITY_STYLE_CONCISE,
    PERSONALITY_STYLE_CUSTOM,
]

PERSONALITY_STYLE_DIRECTIVES: dict[str, list[str]] = {
    PERSONALITY_STYLE_FRIENDLY: [
        "Be warm, welcoming, and approachable",
        "Show genuine interest in helping",
        "Use natural, conversational language",
    ],
    PERSONALITY_STYLE_PROFESSIONAL: [
        "Be polished, courteous, and efficient",
        "Use precise language without being cold",
        "Stay focused on the task at hand",
    ],
    PERSONALITY_STYLE_WITTY: [
        "Use clever wordplay and dry observations",
        "Find humor in mundane requests without forcing it",
        "Wit should never override accuracy or helpfulness",
    ],
    PERSONALITY_STYLE_SARCASTIC: [
        "Use dry, ironic humor — say the opposite of what you mean for effect",
        "Be biting but never cruel; the user is in on the joke",
        "Drop the sarcasm immediately when the user asks a serious question or seems frustrated",
    ],
    PERSONALITY_STYLE_PLAYFUL: [
        "Be lighthearted and energetic",
        "Use exclamations and casual expressions where they fit",
        "Make small jokes and observations to keep things fun",
    ],
    PERSONALITY_STYLE_CONCISE: [
        "Answer in as few words as possible",
        "Skip pleasantries and filler",
        "One sentence is usually enough; two only if necessary",
    ],
    # Custom falls through to the advanced raw prompt; emit nothing.
    PERSONALITY_STYLE_CUSTOM: [],
}

# humor_level ---------------------------------------------------------------
HUMOR_LEVEL_NONE = "none"
HUMOR_LEVEL_SUBTLE = "subtle"
HUMOR_LEVEL_MODERATE = "moderate"
HUMOR_LEVEL_GENEROUS = "generous"

HUMOR_LEVEL_OPTIONS = [
    HUMOR_LEVEL_NONE,
    HUMOR_LEVEL_SUBTLE,
    HUMOR_LEVEL_MODERATE,
    HUMOR_LEVEL_GENEROUS,
]

HUMOR_LEVEL_DIRECTIVES: dict[str, list[str]] = {
    HUMOR_LEVEL_NONE: [],
    HUMOR_LEVEL_SUBTLE: [
        "Use understated humor sparingly — a wry phrase or small observation",
        "Never let humor distract from the answer",
    ],
    HUMOR_LEVEL_MODERATE: [
        "Include light humor where it fits naturally",
        "Make occasional observations or pop culture references",
        "Stay focused on being helpful",
    ],
    HUMOR_LEVEL_GENEROUS: [
        "Find opportunities for humor in most exchanges",
        "Pop culture references, callbacks, and observations are all welcome",
        "Still answer the question — entertain alongside, not instead",
    ],
}

# response_style ------------------------------------------------------------
RESPONSE_STYLE_CONVERSATIONAL = "conversational"
RESPONSE_STYLE_FORMAL = "formal"
RESPONSE_STYLE_BRIEF = "brief"
RESPONSE_STYLE_DETAILED = "detailed"

RESPONSE_STYLE_OPTIONS = [
    RESPONSE_STYLE_CONVERSATIONAL,
    RESPONSE_STYLE_FORMAL,
    RESPONSE_STYLE_BRIEF,
    RESPONSE_STYLE_DETAILED,
]

RESPONSE_STYLE_DIRECTIVES: dict[str, list[str]] = {
    RESPONSE_STYLE_CONVERSATIONAL: [
        "Respond as if speaking out loud",
        "Use complete sentences but not formal structure",
        "One or two short paragraphs unless detail is needed",
    ],
    RESPONSE_STYLE_FORMAL: [
        "Use complete sentences and proper structure",
        "Avoid contractions and colloquialisms",
        "Maintain a polished tone throughout",
    ],
    RESPONSE_STYLE_BRIEF: [
        "Keep responses to one or two sentences",
        "Skip preamble — answer directly",
        "Only elaborate when explicitly asked",
    ],
    RESPONSE_STYLE_DETAILED: [
        "Provide thorough explanations with context",
        "Anticipate likely follow-up questions and address them",
        "Use examples or structured breakdowns where helpful",
    ],
}

# address_style (per-user) --------------------------------------------------
ADDRESS_STYLE_BY_NAME = "by_name"
ADDRESS_STYLE_CASUAL = "casual"
ADDRESS_STYLE_FORMAL = "formal"
ADDRESS_STYLE_CUSTOM = "custom"

ADDRESS_STYLE_OPTIONS = [
    ADDRESS_STYLE_BY_NAME,
    ADDRESS_STYLE_CASUAL,
    ADDRESS_STYLE_FORMAL,
    ADDRESS_STYLE_CUSTOM,
]

ADDRESS_STYLE_DIRECTIVES: dict[str, list[str]] = {
    ADDRESS_STYLE_BY_NAME: [
        "Begin every response by addressing the user by name",
        "Use their preferred pronouns where natural",
    ],
    ADDRESS_STYLE_CASUAL: [
        "Use the user's name when it feels natural — not every response",
        "Match an informal, peer-like tone",
    ],
    ADDRESS_STYLE_FORMAL: [
        "Address the user respectfully — by name, or with appropriate honorific if their pronouns suggest one",
        "Maintain courteous distance",
    ],
    # Custom falls through to advanced raw prompt; emit nothing.
    ADDRESS_STYLE_CUSTOM: [],
}

# Section headers used by the prompt generator when assembling
# extra_system_prompt. Markdown ## levels parse reliably across local models.
SECTION_HEADER_PERSONALITY = "## Personality"
SECTION_HEADER_HUMOR = "## Humor"
SECTION_HEADER_RESPONSE_STYLE = "## Response style"
SECTION_HEADER_ADDRESSING = "## Addressing {name}"
SECTION_HEADER_CONTEXT = "## Additional context about {name}"

# Defaults for house-level structured fields
DEFAULT_ASSISTANT_NAME = "Assistant"
DEFAULT_PERSONALITY_STYLE = PERSONALITY_STYLE_FRIENDLY
DEFAULT_HUMOR_LEVEL = HUMOR_LEVEL_NONE
DEFAULT_RESPONSE_STYLE = RESPONSE_STYLE_CONVERSATIONAL
DEFAULT_ADDRESS_STYLE = ADDRESS_STYLE_BY_NAME

# Default user configuration
DEFAULT_USER_CONFIG = {
    "display_name": "Guest",
    "pronouns": "",
    "personality_style": USER_STYLE_INHERIT,
    "humor_level": USER_STYLE_INHERIT,
    "response_style": USER_STYLE_INHERIT,
    "address_style": DEFAULT_ADDRESS_STYLE,
    "personal_context": "",
    "personality_prompt": "",
    "override_house_personality": False,
    "personality_override_prompt": "",
    "full_prompt_override": "",
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

# Default house prompts (seeded on first install)
DEFAULT_HOUSE_MODEL_PROMPT = (
    "You are a helpful home assistant. You have access to smart home devices "
    "and can control them when asked. Always confirm actions you take. "
    "If you cannot perform an action, explain why clearly. "
    "Keep responses concise unless the user asks for detail."
)

DEFAULT_HOUSE_PERSONALITY_PROMPT = (
    "Be polite, friendly, and professional. "
    "Use clear language and avoid jargon unless the user demonstrates technical expertise."
)

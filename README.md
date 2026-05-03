# Personality LLM <small>_(Custom Integration for Home Assistant)_</small>

> **Forked from [hass_local_openai_llm](https://github.com/skye-harris/hass_local_openai_llm) by [@skye-harris](https://github.com/skye-harris).**  
> Upstream changes are merged periodically. Issues specific to this fork should be reported here, not upstream.

A Home Assistant conversation integration that connects to any OpenAI-compatible LLM server and adds a layered personality system, per-user profiles, speaker recognition, and an optional rephrase pipeline — giving your local AI assistant a consistent voice that adapts to each member of your household.

---

## What this adds over the upstream fork

- **Personality system** — configure your assistant's name, style, humour level, and response style via dropdowns. The integration generates example-driven prompts tuned for small local models.
- **Per-user profiles** — each person in your household gets their own personality settings, pronouns, personal context, and optional prompt overrides.
- **Speaker recognition** — a webhook receives speaker identification from a voice pipeline and routes each conversation to the correct user profile. Multi-turn conversations maintain speaker context automatically. Designed for use with [VoicePipeline](https://github.com/paulglavin/VoicePipeline), but any pipeline that fires the webhook will work.
- **Rephrase pipeline** — optionally route the final response through a second, more capable model (e.g. Claude Haiku) to enforce personality consistency when your primary model is small.
- **Smart Discovery** — a token-efficient entity discovery system that reduces context usage by ~80% compared to a full entity dump.
- **Music Assistant integration** — a typed tool for Music Assistant voice requests.
- **Persona reminder injection** — injects a brief personality reminder after tool call results to prevent tone drift on small models.

Everything from the upstream fork is preserved: streaming, TTS, `<think>` tag stripping, chat template arguments, message history trimming, parallel tool calls, emoji stripping, date/time context injection, RAG via Weaviate, and AI Task entities.

---

## Installation

### Via HACS (recommended)

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Paul-Glavin&repository=personality_llm&category=integration)

> [!NOTE]
> If the button above doesn't work, add `https://github.com/Paul-Glavin/personality_llm` as a custom repository of type **Integration** in HACS.

1. Install `Personality LLM` from HACS.
2. Restart Home Assistant.

<details><summary>Manual install</summary>

Copy the `personality_llm` folder from the [latest release](https://github.com/Paul-Glavin/personality_llm/releases/latest) to your [`custom_components` directory](https://developers.home-assistant.io/docs/creating_integration_file_structure/#where-home-assistant-looks-for-integrations), then restart Home Assistant.

</details>

---

## Quick Start

1. **Add the integration** — Settings → Devices & Services → Add Integration → *Personality LLM*
   - Enter your LLM server URL (e.g. `http://192.168.1.100:11434/v1` for Ollama)
   - Enter an API key if your server requires one (leave blank for Ollama)
2. **Add a Conversation Agent** — from the integration card, add a subentry and select your model
3. **Configure your assistant** — Settings → Devices & Services → Personality LLM → Configure
   - Set an assistant name (e.g. *JARVIS*)
   - Choose a personality style
4. **Assign to Assist** — Settings → Voice Assistants → select your Personality LLM agent

---

## Configuration Reference

### Server Setup

| Field | Description |
|-------|-------------|
| Server name | Display label for this server |
| Server URL | OpenAI-compatible API base URL, typically ending in `/v1` |
| API Key | Optional — leave blank for Ollama and most local servers |

> **Context window:** Assist requires a substantial context for tool definitions and entity lists. Use at least 8k context and configure `max_message_history` to avoid overflow. Context window size is set on the inference server, not here.

> **Tool calling:** Must be enabled in your inference engine. See [vLLM docs](https://docs.vllm.ai/en/latest/features/tool_calling/) or [llama.cpp docs](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md).

### Conversation Agent

| Field | Default | Description |
|-------|---------|-------------|
| Model | — | Selected from your server's available models; supports custom text input |
| System prompt | — | Base instructions; supports Home Assistant template syntax |
| Tool providers | — | Which HA LLM APIs to expose (Assist, Smart Discovery, etc.) |
| Temperature | 0.6 | Response randomness — lower is more predictable |
| Max message history | 0 (unlimited) | Conversation rounds to retain; reduce to save context |
| Strip emojis | off | Removes emoji characters from responses |
| Parallel tool calls | on | Allows multiple simultaneous tool calls per turn |
| Enable Smart Discovery | off | Token-efficient entity discovery (see [Smart Discovery](#smart-discovery)) |
| Music script | — | Music Assistant LLM script entity (see [Music Assistant](#music-assistant)) |

### Personality System

Configure via **Settings → Devices & Services → Personality LLM → Configure**.

| Field | Options | Description |
|-------|---------|-------------|
| Assistant name | any | What the assistant calls itself — used in all generated prompts |
| Personality style | Friendly / Professional / Witty / Sarcastic / Playful / Concise / Custom | Overall voice and tone |
| Humour level | None / Subtle / Moderate / Generous | How much humour appears in responses |
| Response style | Conversational / Formal / Brief / Detailed | Response length and structure |

The integration generates **example-driven prompts** from these settings. Rather than abstract directives ("be sarcastic"), the model sees concrete User/Assistant exchange examples. This produces more consistent results on small local models than meta-instructions alone.

When **Custom** is selected for Personality Style, the raw `house_personality_prompt` field is used instead.

#### Advanced: Raw Prompts

For full control, expand the **Advanced** section in the options flow:

| Field | Description |
|-------|-------------|
| House model prompt | Base instructions: tool rules, response format, truthfulness after tool calls. Supports `{assistant_name}`, `{time}`, `{date}`, `{home_context_summary}` placeholders. |
| House personality prompt | Fallback personality text used only when Personality Style is set to Custom. |

### Per-User Profiles

Enable with the **Enable per-user personality** toggle. Each speaker gets an independent profile:

| Field | Description |
|-------|-------------|
| Display name | Name used in prompts and addressed by the assistant |
| Pronouns | Preferred pronouns used naturally in responses |
| Personality style | Inherits from house settings, or override individually |
| Humour level | Inherits from house settings, or override individually |
| Response style | Inherits from house settings, or override individually |
| Address style | Always by name / Casually / Formally / Custom |
| Personal context | Background info shown to the model (max 500 chars): role, preferences, interests |
| Personality prompt | Additional instructions appended after the house personality |

**Advanced per-user overrides** (enabled separately by admin):

| Field | Description |
|-------|-------------|
| Personality override | Replaces the house personality entirely for this user |
| Full prompt override | Replaces the entire system prompt — house model prompt and all personality content |

#### Speaker Identification via Webhook

Speaker identification is designed for use with [VoicePipeline](https://github.com/paulglavin/VoicePipeline), but any pipeline that fires the webhook in the correct format will work.

To route conversations to the correct profile, fire a webhook before each voice interaction. The integration registers a webhook at:

```
POST /api/webhook/personality_llm_input
Content-Type: application/json

{
  "speaker_id": "paul",
  "confidence": 1.0,
  "timestamp": "2026-05-03T10:00:00Z"
}
```

- `speaker_id` must match the ID used in the integration config (lowercase alphanumeric + underscores, max 50 chars)
- Speaker identity is cached for 2 seconds — fire the webhook immediately before the voice command
- Multi-turn conversation identity is maintained for 30 minutes
- Shadow HA users are created automatically per speaker for permission scoping

If no webhook fires and no conversation history is present, the `default` speaker profile is used.

### Rephrase Pipeline

Routes the primary model's response through a second, more capable model to enforce personality consistency. Useful when your primary model is small and struggles to maintain a consistent voice.

Configure via the **Rephrase Settings** section of the Conversation Agent config:

| Field | Description |
|-------|-------------|
| Enable rephrase | Enables the pipeline |
| Rephrase model | Model identifier at the rephrase endpoint (e.g. `claude-haiku-4-5-20251001`) |
| Rephrase base URL | Base URL of the rephrase service; leave blank to use the same server as the primary model |
| Rephrase API key | API key for the rephrase service |

The rephrase model receives the same personality prompt as the primary model and is instructed to preserve all facts and device states while restating the response in the configured voice with speech-formatted output.

### Smart Discovery

A token-efficient alternative to the standard HA entity dump. Instead of sending the full entity list (~8k tokens for a typical installation), Smart Discovery provides a structural index (~1.5k tokens) and exposes `discover_entities` and `get_entity_details` tools for on-demand lookup.

To enable:
1. Toggle **Enable Smart Discovery** on in the Conversation Agent config
2. In **Tool Providers**, select **Personality LLM Smart Discovery** (instead of, or alongside, the standard Assist API)

### Music Assistant

Enables voice-controlled music playback via [Music Assistant](https://music-assistant.io/).

1. In Music Assistant, create an LLM script for voice requests
2. In the Conversation Agent config, set **Music Script** to that script entity
3. The integration exposes a typed `play_music` tool that routes requests through Music Assistant

### Date/Time Context Injection

Injects the current date and time into the model context each turn. Three injection methods are available:

| Method | Description |
|--------|-------------|
| Tool Result | Injected as a tool call result — recommended, most reliable |
| Assistant | Injected as an assistant message |
| User | Injected as a user message |

Leave unset to disable. Note: the default house model prompt includes `{time}` and `{date}` placeholders that are resolved at call time regardless of this setting.

---

## Experimental: Retrieval Augmented Generation (RAG) with Weaviate

Retrieval Augmented Generation pre-fills the model with relevant context based on the current user message, without loading everything into the prompt at all times.

Once configured, user messages are queried against a Weaviate vector database before being sent to the model. Matching entries are injected into the current conversation turn as context.

> This is not a general-purpose memory — context is only injected when it matches the current user message, and does not carry forward to subsequent turns.

### Weaviate Setup

1. **Install Weaviate** — a `docker-compose.yml` is provided in the `weaviate/` directory
2. **Configure the integration** — expand the **Weaviate configuration** section when adding or reconfiguring the *server* entry (not the agent):
   - Weaviate host (include protocol and port, e.g. `http://192.168.1.100:8080`)
   - Weaviate API key (`homeassistant` if using the supplied `docker-compose.yml`)
3. **Optionally tune per-agent** — reconfigure an agent to adjust:
   - Object class name (default: `Homeassistant`)
   - Max results (default: 2)
   - Result score threshold (default: 0.9)
   - Hybrid search alpha (default: 0.5 — balances keyword vs. semantic matching)

### Managing Knowledge Entries

Use the `personality_llm.add_to_weaviate` service action to add or update entries:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | Yes | Text matched against user input |
| `content` | Yes | Context injected into the model when the query matches |
| `identifier` | No | Unique ID — allows updating an existing entry |

A simple management web app is included in `weaviate/` and exposed on port 9090 by default by the supplied `docker-compose.yml`.

### Notes

- Only the current user message is queried — prior turns are not included
- Results are used for the current turn only, including any tool call iterations
- Each entry stores a `query` (vectorised, matched against input) and `content` (injected into prompt on match)
- A `personality_llm.add_to_weaviate` service action is available for adding entries from HA automations

---

## Acknowledgements

- Forked from [hass_local_openai_llm](https://github.com/skye-harris/hass_local_openai_llm) by [@skye-harris](https://github.com/skye-harris)
- Which is itself forked from the [OpenRouter](https://github.com/home-assistant/core/tree/dev/homeassistant/components/open_router) integration for Home Assistant by [@joostlek](https://github.com/joostlek)

---

For implementation details and internals, see [docs/architecture.md](docs/architecture.md).

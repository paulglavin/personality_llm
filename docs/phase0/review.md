# Architecture Audit: `local_openai` HA Integration

> **Note:** The component domain is `local_openai`, not `local_openai_llm`. The repo name is just the GitHub project name.

---

## 1. How `conversation.py` Integrates with HA's Assist Pipeline

`conversation.py` is minimal — it delegates almost entirely to `entity.py`.

`LocalAiConversationEntity` extends both `LocalAiEntity` and HA's `conversation.ConversationEntity`:

```python
class LocalAiConversationEntity(LocalAiEntity, conversation.ConversationEntity):
    _attr_supports_streaming = True
```

The key integration point is `_async_handle_message`, which HA calls for every Assist turn:

```python
async def _async_handle_message(self, user_input, chat_log):
    await chat_log.async_provide_llm_data(
        user_input.as_llm_context(DOMAIN),
        llm_apis,           # which HA tool APIs to expose
        system_prompt,
        user_input.extra_system_prompt,
    )
    await self._async_handle_chat_log(chat_log, ...)
    return conversation.async_get_result_from_chat_log(user_input, chat_log)
```

HA's `ChatLog` object is the shared conversation state. `async_provide_llm_data` populates it with the system prompt and available tools. `async_get_result_from_chat_log` extracts the final response. The integration never manually constructs `ConversationResult` — HA's helpers do it.

The entity is registered during `async_setup_entry` by iterating over config subentries with `subentry_type == "conversation"` — meaning a single config entry (one LLM server) can host multiple conversation agents on different models.

---

## 2. How It Calls the OpenAI-Compatible API

The `AsyncOpenAI` client is initialized in `__init__.py` and stored in `entry.runtime_data`:

```python
client = AsyncOpenAI(
    base_url=entry.data[CONF_BASE_URL],
    api_key=entry.data.get(CONF_API_KEY, ""),
    http_client=get_async_client(hass),  # HA's shared httpx client
)
```

The actual call in `entity.py`:

```python
result_stream = await client.chat.completions.create(**model_args, stream=True)
```

`model_args` always includes:

| Field | Value |
|---|---|
| `model` | from subentry config |
| `temperature` | configurable (default 0.6) |
| `parallel_tool_calls` | configurable bool |
| `extra_headers` | `HTTP-Referer` + `X-Title: "Home Assistant"` (OpenRouter attribution) |
| `messages` | converted chat history |
| `tools` | HA tool list (if APIs enabled) |
| `extra_body` | `chat_template_kwargs` + `metadata.session_id` (optional) |
| `response_format` | JSON Schema (AI Task only, for structured output) |

Streaming is always `True`. The response is consumed via `_transform_stream`, which yields `AssistantContentDeltaDict` chunks fed into `chat_log.async_add_delta_content_stream`.

---

## 3. Tool Calling

**Which HA API:** Tools come from HA's `llm` subsystem — specifically `llm.async_get_apis()`. The default is `llm.LLM_API_ASSIST` (the Assist API, which exposes entity control, scripts, scenes, etc.). Users can select multiple APIs.

**Tool format conversion:**

```python
def _format_tool(tool, custom_serializer) -> ChatCompletionFunctionToolParam:
    parameters = convert(tool.parameters, custom_serializer=custom_serializer)
    _remove_unsupported_keys_from_tool_schema(parameters)  # strips allOf/anyOf/oneOf
    tool_spec = FunctionDefinition(name=tool.name, parameters=parameters)
    return ChatCompletionFunctionToolParam(type="function", function=tool_spec)
```

HA's `voluptuous` schemas are converted to JSON Schema via `voluptuous_openapi.convert`. Unsupported combiners (`allOf`/`anyOf`/`oneOf`) are stripped for compatibility with local servers.

**Tool call loop:** Iterates up to `MAX_TOOL_ITERATIONS = 10` times. Each iteration streams the model response, appends it to `model_args["messages"]`, then checks `chat_log.unresponded_tool_results` — if none remain, it breaks. Tool calls accumulate across streaming chunks in `pending_tool_calls` dict, keyed by `tool_call_id + tool_call_name` to handle quirks across llama.cpp, Ollama, and OpenRouter streaming formats.

**Special case:** If a content injection method is configured, the `GetDateTime` tool is removed from the tool list (since the date/time is injected directly into the message stream instead).

---

## 4. Config Schema

### Server-level (one per LLM server)

| Field | Type | Notes |
|---|---|---|
| `server_name` | string | Display name |
| `base_url` | string | OpenAI-compatible endpoint |
| `api_key` | string (optional) | Bearer token |
| `weaviate_options.weaviate_host` | string | RAG vector DB host |
| `weaviate_options.weaviate_api_key` | string | Weaviate auth |

### Conversation subentry

| Field | Type | Default | Notes |
|---|---|---|---|
| `model` | select + custom | — | Populated from server's model list |
| `prompt` | template | HA default | Jinja2 system prompt |
| `llm_hass_api` | multi-select | Assist API | Which HA tool APIs to expose |
| `parallel_tool_calls` | bool | `True` | Passed to OpenAI API |
| `strip_emojis` | bool | `False` | Strips via `demoji` |
| `temperature` | float 0–1 | `0.6` | |
| `max_message_history` | int 0–50 | `0` (all) | Conversation memory limit |
| `content_injection_method` | dropdown | — | How to inject date/RAG: Tool/Assistant/User role |
| `chat_template_opts.chat_template_kwargs` | key-value pairs | `[]` | Passed as `extra_body.chat_template_kwargs` |
| `weaviate_options.*` | section | — | Per-agent RAG class, thresholds, result count |

### AI Task subentry

Adds `supported_attributes` (generate_data / generate_image) and a nested `tooling` section with `llm_hass_api` and `parallel_tool_calls`.

---

## 5. Multi-Speaker Limitations

There are significant limitations for multi-speaker use:

1. **No speaker identity propagation.** `user_input.text` is processed, but `user_input` carries a `conversation_id` (used only for LiteLLM tracing via `metadata.session_id` in `extra_body`). There is no mechanism to attach speaker identity, voice profile, or user entity to messages.

2. **Single `ChatLog` per `conversation_id`.** HA's `ChatLog` is keyed on `conversation_id`. Multi-speaker scenarios would require each speaker to maintain a distinct conversation ID, but there is nothing in this integration to route or create those IDs per-speaker. HA Assist itself doesn't currently surface speaker identity to conversation agents.

3. **Single system prompt.** The system prompt is a single Jinja2 template configured at the subentry level. There is no per-user prompt personalization.

4. **Shared `max_message_history`.** History trimming is purely count-based, per chat log. In a shared-conversation scenario (same `conversation_id`), messages from different speakers interleave with no attribution.

5. **RAG is not user-scoped.** Weaviate class and search parameters are global to the subentry; RAG retrieval uses the raw `user_input.text` query with no user context.

**The root constraint is HA's Assist pipeline itself** — it does not currently pass speaker/user identity to conversation agents. This integration faithfully exposes all data HA provides, so multi-speaker support would require upstream HA changes before this integration could act on it.

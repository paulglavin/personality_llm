# Architecture & Internals

Implementation reference for contributors and for understanding how the integration works under the hood.

---

## Key Files

| File | Purpose |
|------|---------|
| `conversation.py` | Main conversation entity — speaker resolution, prompt assembly, rephrase pipeline |
| `prompt_generator.py` | Assembles `extra_system_prompt` from structured personality config |
| `prompt_resolver.py` | Routes between structured/legacy prompt modes, applies per-user overrides |
| `const.py` | All constants: `PERSONALITY_STYLE_EXAMPLES`, `GOOD_BAD_EXAMPLES`, style directives |
| `entity.py` | Base entity — chat log handling, tool iteration, persona reminder injection |
| `config_flow.py` | All configuration flows: server, conversation agent, options, per-user |
| `__init__.py` | Integration setup — webhook, speaker cache, user config manager, smart discovery |
| `smart_discovery.py` | Entity index management and `PersonalityLLMSmartAPI` tool provider |
| `user_config.py` | `UserConfigManager` — persistent per-speaker storage |

---

## Prompt Layer Architecture

Every conversation turn assembles a final `(system_prompt, extra_system_prompt)` pair from up to four layers:

```
Layer 1: house_model_prompt          → system_prompt
          (tool rules, format, safety)

Layer 2: generated personality       → extra_system_prompt
          (from style dropdowns)       injected AFTER entity list
          OR house_personality_prompt  (recency advantage)

Layer 3: per-user additive prompt    → appended to extra_system_prompt
          OR per-user override         replaces extra_system_prompt

Layer 4: full_prompt_override        → replaces system_prompt + extra_system_prompt entirely
```

`extra_system_prompt` is passed via `chat_log.async_provide_llm_data()`, which positions it after HA's entity list in the context window. This gives personality instructions recency advantage over the entity dump.

### House Model Prompt

Base model instructions stored in `house_model_prompt` (entry options). Defaults to `HOUSE_BASE_PERSONALITY_TEMPLATE` in `const.py`.

Template variables resolved at call time:

| Placeholder | Resolves to |
|------------|-------------|
| `{assistant_name}` | Configured assistant name |
| `{time}` | Current time (HH:MM) |
| `{date}` | Current date (YYYY-MM-DD) |
| `{home_context_summary}` | Smart Discovery index, if enabled |

### Generated Personality (extra_system_prompt)

Built by `prompt_generator.generate_personality_prompt()` from structured dropdown fields.

The generator uses **example-based prompting** rather than directive bullets. Each personality style maps to concrete User/Assistant exchange examples in `const.PERSONALITY_STYLE_EXAMPLES`. Small local models respond to input→output pairs more reliably than meta-instructions.

Multiple state variants per style (`device_query_none_on`, `device_query_all_on`) teach the model to reflect actual tool results rather than copying example content verbatim.

**Family context guard:** If a user's `personal_context` mentions family relationships (detected by keyword scan: `married to`, `father to`, etc.), the generator appends a constraint reminding the model not to default to family references as punchlines. This prevents overfitting to family-specific examples.

### Per-User Personality

Resolved by `prompt_resolver.py`. Decision tree:

1. `full_prompt_override` set and `allow_full_prompt_override` enabled → replaces everything
2. `override_house_personality` set and `allow_personality_override` enabled → replaces generated personality, keeps speaker header
3. `personality_prompt` set → appended after generated personality
4. Otherwise → generated personality used as-is

Routing between structured (dropdown) and legacy (raw prompt) modes is handled by checking whether `personality_style` is present in `entry_options`.

---

## Speaker Resolution Pipeline

```
Voice pipeline fires POST /api/webhook/personality_llm_input
                        ↓
                  SpeakerCache (2s TTL)
                        ↓
           _async_handle_message() called
                        ↓
          ┌─ Cache hit? → speaker_id from webhook
          ├─ No cache, has conversation_id? → ConversationSpeakerCache (30min TTL)
          └─ Nothing? → speaker_id = "default"
                        ↓
          Load user config from UserConfigManager
                        ↓
          Build (system_prompt, extra_system_prompt) for this speaker
                        ↓
          Update Context(user_id=shadow_user_id) for HA permission scoping
                        ↓
          ... LLM call, tool iterations ...
                        ↓
          Store conversation_id → speaker_id in ConversationSpeakerCache
```

Shadow HA users (`voice_speaker_{speaker_id}`) are created on demand so HA's permission system correctly scopes tool access per speaker.

---

## Rephrase Pipeline

```
Primary model generates response
            ↓
chat_log.content[-1] = AssistantContent(original)
            ↓
_async_rephrase_response(original, personality_prompt, rephrase_opts)
            ↓
Rephrase model receives:
  system: personality_prompt (same prompt as primary model)
  user:   "Rephrase the following response in your assigned voice...
           Keep all facts, device states, and specific information exactly as stated.
           Format for speech: spell out numbers, no markdown or symbols.
           Output only the rephrased text, nothing else.

           {original}"
            ↓
Returns rephrased text — or None on failure (caller keeps original)
            ↓
chat_log.content[-1] = AssistantContent(rephrased)
```

After each successful rephrase, token counts and latency are written to the `personality_llm.bench` HA state entity for benchmarking (see [Benchmark Tooling](#benchmark-tooling)).

---

## Smart Discovery

`SmartDiscovery` (`smart_discovery.py`) maintains a structural index of the home's entities, grouped by area and domain. The `IndexManager` rebuilds the index on a schedule and on state changes.

When Smart Discovery is enabled on a conversation agent, the rendered index is injected into the `{home_context_summary}` placeholder in the house model prompt before each call.

`PersonalityLLMSmartAPI` is registered as an LLM API provider and exposes two tools to the model:

| Tool | Description |
|------|-------------|
| `discover_entities` | Returns entities matching an area, domain, or both |
| `get_entity_details` | Returns full state + attributes for specific entity IDs |

This replaces the standard HA Assist API entity dump (~8k tokens) with an index (~1.5k tokens) plus on-demand lookup — approximately 80% token reduction on a typical installation.

---

## Persona Reminder Injection

After each tool call result, before the next LLM call, a system message is injected:

```
[Reminder: You are {assistant_name}. Deliver the tool results in your assigned voice and personality.]
```

This is handled in `entity.py` during the tool iteration loop. It prevents small models from reverting to generic assistant language after processing tool results.

---

## Message History Trimming

When `max_message_history > 0`, the integration trims the chat log before each call to keep the last N assistant turns (2×N messages total) plus the current user message and system prompt.

Orphaned tool result messages (where the corresponding tool call was trimmed) are removed to prevent API errors on strict OpenAI-compatible endpoints.

---

## Benchmark Tooling

### bench_ha.py

Fires real HA commands via the `/api/conversation/process` endpoint and collects metrics by polling the `personality_llm.bench` state entity after each response.

```
python bench_ha.py --model GPTOSS --headers > results.csv
# Switch model in HA
python bench_ha.py --model Gemma4 >> results.csv
```

**Secrets:** Read from `bench_secrets.py` (gitignored). Falls back to empty strings if absent.

**State polling:** The integration writes to `personality_llm.bench` after each rephrase with a `ts` timestamp. `bench_ha.py` polls until it sees a `ts` newer than the query start time, with a 10-second timeout.

**Speaker webhook:** Fired before each command to ensure HA resolves the correct per-user config.

### bench_rephrase.py

Offline benchmark comparing local model output vs. rephrase model output across a set of test queries, without requiring a live HA instance. Useful for evaluating model/rephrase pairs and tuning personality prompts before deploying to HA.

Results are written as CSV to stdout; progress to stderr.

---

## Content Injection Methods (Date/Time)

When date/time injection is configured, the integration inserts a synthetic message before the current user turn:

| Method | Message role | Notes |
|--------|-------------|-------|
| `Tool Result` | tool | Simulates a tool call result; most reliable across models |
| `Assistant` | assistant | Use if Tool Result causes issues |
| `User` | user | Last resort; some models echo it back |

The `GetDateTime` tool is removed from the tool list when date/time is injected manually, to avoid double-injection.

---

## Configuration Flow Structure

```
Integration setup (async_step_user)
    Server URL, API key, Weaviate host/key

    ├─ Conversation subentry (ConversationFlowHandler)
    │   Model, prompt, tools, temperature, history, rephrase, Smart Discovery, Music, RAG
    │
    └─ AI Task subentry (AITaskDataFlowHandler)
        Model, task types (generate_data / generate_image), tools

Options flow (PersonalityLLMOptionsFlowHandler)
    Step 1 (async_step_init): House personality + per-user enablement flags
        └─ If per-user enabled:
            Step 2 (async_step_user_select): Select or create speaker ID
            Step 3 (async_step_user_personality): Individual speaker settings
                └─ Loop back to Step 2 for next speaker
```

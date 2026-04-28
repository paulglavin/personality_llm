# Smart Entity Discovery — Development Plan

**Problem being solved:** At 90+ exposed HA entities, `LLM_API_ASSIST` injects ~8,000 tokens of entity catalog into every system-prompt turn. Small local models (7B–20B) exhaust their context window before reaching the personality directives, causing them to drop or ignore the configured personality entirely.

**Solution:** Replace the monolithic entity dump with a compact structural index (~700 tokens) and three on-demand discovery tools. The model reads the index to understand what exists, then queries specifics as needed.

**Expected token budget:**

| Before | After (index + tool schemas + API prompt) | Saving |
|--------|------------------------------------------|--------|
| ~8,000 | ~1,500–2,000 | ~75–80% |

---

## Current Branch

`feature/phase-3-tokenreduction`

---

## Architecture

### Component overview

```
__init__.py
  ├── IndexManager          (index_manager.py)   — builds/caches structural index
  ├── SmartDiscovery        (discovery.py)        — filtered entity lookup
  └── PersonalityLLMSmartAPI (tools.py)           — registers 3 llm.Tool subclasses

conversation.py
  └── _async_handle_message — reads CONF_ENABLE_SMART_DISCOVERY toggle;
                              appends index block to model_prompt before
                              resolve_prompts() is called
```

### How it fits into HA's LLM machinery

```
HA ChatLog.async_provide_llm_data(llm_context, llm_apis, system_prompt, extra_system_prompt)
          │
          ├── llm_apis = ["personality_llm_smart_discovery"]   ← our custom API
          │     └── PersonalityLLMSmartAPI.async_get_api_instance()
          │           ├── api_prompt: SMART_API_PROMPT (tool usage instructions)
          │           └── tools: [DiscoverEntitiesTool, GetEntityDetailsTool, PerformActionTool]
          │
          └── system_prompt contains the structural index (injected by conversation.py)
```

### Structural index format (render_for_prompt output)

```
Areas (12): Kitchen [14, Ground], Living Room [22, Ground], ...
Floors (2): Ground (5 areas, 48), First (3 areas, 22)
Labels: Security(8), Energy(14)
Domains: light(28), sensor(22), switch(14), climate(4), ...
Device classes: motion(8), temperature(6), humidity(4), ...
Scripts: bedtime, leave_house, movie_mode
Automations: Morning routine, Away mode, ...
People: Paul, Alice
```

~400–700 tokens for 90 entities (vs ~8k for the full entity dump).

---

## Configuration

### Per conversation subentry options

| Setting | Key | Default | Description |
|---------|-----|---------|-------------|
| Enable smart entity discovery | `enable_smart_discovery` | `False` | Injects index into model_prompt |

### HA config entry (global)

The `PersonalityLLMSmartAPI` registers as a tool provider called **"Personality LLM Smart Discovery"** that appears in the "Tool Providers" multiselect on any conversation subentry.

### Recommended setup for maximum token saving

1. Open the conversation subentry → reconfigure
2. **Tool Providers**: remove "Home Assistant" (Assist), add "Personality LLM Smart Discovery"
3. Enable the **"Enable smart entity discovery"** toggle
4. Save and restart

This removes the full entity dump entirely and replaces it with the index + tools path.

---

## Files

### New (untracked → commit these)

| File | Purpose |
|------|---------|
| `custom_components/personality_llm/index_manager.py` | Builds/caches structural index; listens for registry events and debounce-refreshes (60s) |
| `custom_components/personality_llm/discovery.py` | Filtered entity discovery with attribute whitelist; supports domain/area/floor/label/state/name/device_class filters |
| `custom_components/personality_llm/tools.py` | `DiscoverEntitiesTool`, `GetEntityDetailsTool`, `PerformActionTool`, `PersonalityLLMSmartAPI` |

### Modified

| File | Change summary |
|------|---------------|
| `const.py` | +5 constants: `CONF_ENABLE_SMART_DISCOVERY`, `DEFAULT_ENABLE_SMART_DISCOVERY=False`, `CONF_MAX_ENTITIES_PER_DISCOVERY`, `DEFAULT_MAX_ENTITIES_PER_DISCOVERY=50`, `SMART_DISCOVERY_API_ID` |
| `__init__.py` | Imports IndexManager/SmartDiscovery/PersonalityLLMSmartAPI; initialises them in `async_setup_entry`; tears them down in `async_unload_entry` before `hass.data.clear()` |
| `conversation.py` | Adds `dt_util` import; reads `CONF_ENABLE_SMART_DISCOVERY` toggle; injects index block into `model_prompt` before `resolve_prompts()` |
| `config_flow.py` | Adds `CONF_ENABLE_SMART_DISCOVERY` bool field to `ConversationFlowHandler.get_schema()` |
| `translations/en.json` | Adds label + description for `enable_smart_discovery` in both `user` and `reconfigure` steps |

---

## Phase 0 — Done

- [x] `index_manager.py` — structural index builder with lazy caching, debounced refresh, compact text renderer
- [x] `discovery.py` — filtered entity discovery (general path, attribute-whitelist results)
- [x] `tools.py` — three `llm.Tool` subclasses + `PersonalityLLMSmartAPI`
- [x] `const.py` — smart discovery constants
- [x] `__init__.py` — IndexManager/SmartDiscovery init, API registration, teardown
- [x] `conversation.py` — index injection block
- [x] `config_flow.py` — toggle in conversation schema
- [x] `translations/en.json` — labels for toggle

### What Phase 0 does NOT include (intentional deferral)

- Gap-filling (LLM infers entity types for ambiguous names) — Phase 2
- Script field introspection (scripts listed by name only, no parameter schema) — Phase 2
- Per-subentry `max_entities_per_discovery` — Phase 1
- `list_areas` / `list_domains` tools — Phase 1

---

## Verification Steps (do after HA restart)

1. Check "Personality LLM Smart Discovery" appears in Tool Providers multiselect on a conversation subentry.
2. Enable the toggle, keep "Assist" as well for the first test (belt-and-braces).
3. Add this temporary line **before** `chat_log.async_provide_llm_data` in `conversation.py:163`:
   ```python
   _LOGGER.warning("PROMPT TOKENS ~%d", (len(system_prompt) + len(combined_extra or "")) // 4)
   ```
4. Restart HA, send a message, check the HA log for `PROMPT TOKENS`.
5. Compare: with toggle OFF should be ~8k tokens; with toggle ON + Assist removed should be ~1.5k.
6. Confirm the model calls `discover_entities` before acting on a device.
7. Confirm personality directives appear in responses (they were previously lost at 8k tokens).
8. Remove the temporary log line.

---

## Phase 1 Backlog

Each item is independent and can ship without the others.

### 1.1 `list_areas` / `list_domains` tools

Expose `IndexManager.get_index()` areas/domains data as explicit `llm.Tool` subclasses so the model can query the index at runtime instead of relying solely on the injected text block.

- **File**: `tools.py` — add `ListAreasTool`, `ListDomainsTool`
- **~80 LoC**

### 1.2 Per-subentry `max_entities_per_discovery`

Currently `DiscoverEntitiesTool` caps at 50 (hardcoded). Let users tune this per conversation subentry.

- **File**: `config_flow.py` — add `CONF_MAX_ENTITIES_PER_DISCOVERY` `NumberSelector` to `ConversationFlowHandler.get_schema()`
- **File**: `tools.py` `DiscoverEntitiesTool.async_call` — read from `llm_context` (needs subentry data accessible; may need to thread via `PersonalityLLMSmartAPI`)
- **~30 LoC**

### 1.3 `get_entity_history` tool

Answers questions like "when did the front door last open?" and "what was the temperature yesterday?".

Port from mcp-assist `mcp_server.py:920`:
```python
from homeassistant.components.recorder import history

async def async_call(self, hass, tool_input, llm_context):
    entity_id = tool_input.tool_args["entity_id"]
    hours = tool_input.tool_args.get("hours", 24)
    end = dt_util.utcnow()
    start = end - timedelta(hours=hours)
    states = await recorder.get_instance(hass).async_add_executor_job(
        history.get_significant_states, hass, start, end, [entity_id]
    )
    ...
```

- **File**: `tools.py` — add `GetEntityHistoryTool`
- **~150 LoC**
- **Requires**: `homeassistant.components.recorder` (already a HA core component)

### 1.4 Response-mode framework

Port `RESPONSE_MODE_INSTRUCTIONS` from mcp-assist `const.py:105-133`. Lets the integration signal the voice pipeline to stay in continued-listening mode (useful for multi-turn voice queries like "turn on X… and also Y").

- **Files**: `const.py` (new `CONF_RESPONSE_MODE`, mode string constants), `config_flow.py` (selector), `tools.py` (new `SetConversationStateTool`), `conversation.py` (inject mode hint into API prompt at runtime)
- **~100 LoC + content**

### 1.5 Unit tests for Phase 0

Key test cases:

| Test | What it verifies |
|------|-----------------|
| `test_index_render_under_1k` | Fixture of 90 entities → `render_for_prompt()` < 1,000 tokens |
| `test_discover_entities_respects_limit` | `limit=5` returns ≤5 results |
| `test_discover_entities_caps_at_max` | `limit=100` is capped at 50 |
| `test_index_refresh_debounces` | 5 rapid registry events → exactly 1 `_generate_index` call after debounce |
| `test_token_budget` | Full conversation path with toggle ON → ≤2,000 tokens in system_prompt |
| `test_perform_action_bad_service` | `domain/action` not registered → `{"success": False}` |
| `test_get_entity_details_not_exposed` | Entity not exposed → `{"error": "entity not exposed..."}` |

---

## Phase 2 Backlog

These are more complex and gated behind their own toggles.

### 2.1 LLM gap-filling in index

When the index contains entity IDs that can't be resolved to a clear type (e.g. `sensor.x1234_a`), make one LLM call on index build to infer their semantic type and cache the result.

Port from mcp-assist `index_manager.py:694-892`:
- Call `entry.runtime_data.chat.completions.create()` directly (the `AsyncOpenAI` client on `entry.runtime_data`), NOT the conversation agent
- Preserve brace-balancing JSON repair logic from mcp-assist
- Gate behind `CONF_GAP_FILLING` (default `False`)
- Skip on first index build; only run after at least one cached index exists

**~250 LoC**

### 2.2 `run_script` and `run_automation` tools

Port from mcp-assist `mcp_server.py:868,894`. Also add script field introspection to `IndexManager._get_scripts` (port `index_manager.py:519-560`) so the model knows what parameters a script accepts.

**~150 LoC**

---

## Phase 3 — Explicitly Skipped

These were considered but rejected as outside scope:

| Feature | Reason skipped |
|---------|---------------|
| Multi-profile entry pattern (mcp-assist style) | personality_llm's subentries + speaker awareness already covers this better |
| OpenClaw WebSocket client | Niche, off-mission |
| Brave/DuckDuckGo/read_url search tools | Outside personality scope |
| Person/pet entity routing heuristics | General discovery path covers the same cases via filters |
| External MCP HTTP server | In-process `llm.Tool` API is cleaner, no port management |

---

## Key Design Decisions

### Why not `extra_system_prompt` for the index?

The index text (700 tokens) is placed in `model_prompt`, not `extra_system_prompt`. The `extra_system_prompt` position (injected by HA after the entity list) is reserved for personality directives which benefit from recency attention. The index is structural background, not behavioral, so it belongs in `model_prompt`.

### Why a structural index rather than a dynamic tool?

The model needs to know what *categories* of things exist before it can formulate a sensible discovery query. If the model doesn't know there's a floor called "Ground" or a label called "Security", it won't know to filter by them. The index gives the model a map; discovery tools give it the territory.

### Why not just set a lower entity count limit in Assist?

Assist's entity injection is all-or-nothing per entity exposure config. You'd have to un-expose entities from voice to reduce the count, which breaks queries for those entities entirely. Smart Discovery keeps all entities reachable while keeping the prompt small.

### Why `DEFAULT_ENABLE_SMART_DISCOVERY = False`?

Safe default. Existing subentries using Assist keep working without changes. Users opt in explicitly.

### Reload safety

`IndexManager` registers HA bus event listeners and must unsub them on entry unload. `async_unload_entry` calls `await index_mgr.async_stop()` **before** `hass.data[DOMAIN].clear()`. Without this, reloading the entry would leak listeners from the previous load, causing double-refresh on every registry change.

---

## Prompt Layering (full picture)

```
system_prompt (sent as the "system" message):
  [house_model_prompt]          ← entry.options["house_model_prompt"]
  [subentry_prompt]             ← subentry.data[CONF_PROMPT]  (per-model quirks)
  [## Home Assistant context    ← injected by conversation.py when toggle ON
    <index text>
    Current time / Date]

extra_system_prompt (injected by HA after entity list):
  [upstream pipeline extra]     ← user_input.extra_system_prompt
  [generated personality        ← resolve_prompts() → generated_extra
    ## Personality ...
    ## Humor ...
    ## Response style ...
    ## Addressing {name} ...
    ## Additional context ...]
```

When Smart Discovery is ON and Assist is removed from Tool Providers, the "entity list" injected by HA between system_prompt and extra_system_prompt is empty (no tool providers = no entity dump), so the model receives only the index + personality, totalling ~1.5k tokens.

---

## Related Files (for context only, not modified by this work)

| File | Role |
|------|------|
| `prompt_resolver.py` | Combines house + user personality into `(system_prompt, generated_extra)` tuple |
| `prompt_generator.py` | Builds structured personality directives from style/humor/response_style settings |
| `entity.py` | `LocalAiEntity` base — contains `_async_handle_chat_log` with the tool-call loop |
| `speaker_cache.py` | 2s TTL cache: webhook → speaker_id before conversation.py runs |
| `conversation_speaker_cache.py` | 30min TTL: conversation_id → speaker_id for multi-turn |
| `user_config.py` | Persistent per-speaker config (display_name, personality overrides, etc.) |

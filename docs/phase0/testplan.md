# Phase 0 Baseline Test Plan: `local_openai` HA Integration

**Purpose:** Validate that the upstream `hass_local_openai_llm` integration works correctly before any modifications.
**Prerequisites:** Integration installed and configured in HA with a working OpenAI-compatible backend (e.g., Ollama, llama.cpp, LM Studio).

---

## Setup: Enable Debug Logging

Add to `configuration.yaml` before running any tests. This enables verbose output for all five test areas.

```yaml
logger:
  default: warning
  logs:
    custom_components.local_openai: debug
    homeassistant.components.conversation: debug
    homeassistant.helpers.llm: debug
```

Restart HA after adding. Access logs via **Settings → System → Logs** or tail directly:

```bash
tail -f home-assistant.log | grep -E "local_openai|conversation|llm"
```

---

## Test 1: Basic Conversation (No Tools)

**Goal:** Confirm the integration can complete a round-trip with no tool use, streaming correctly, and returning a coherent response.

### Setup

- In the subentry config, set `llm_hass_api` to empty (no HA APIs selected).
- Confirm `parallel_tool_calls` is irrelevant here but leave at default `True`.

### Steps

1. Open **Developer Tools → Conversation** in HA, or use the Assist UI.
2. Select the `local_openai` agent from the agent dropdown.
3. Send: `"What is the capital of France?"`
4. Send: `"What did I just ask you?"` (tests short-term memory within the same conversation session).

### Expected Outcomes

| Step | Expected |
|---|---|
| Step 3 | Response contains "Paris" within a few seconds. No tool calls appear in logs. |
| Step 4 | Response references France/Paris, demonstrating the `ChatLog` history is preserved. |

### Log Snippets to Look For

Successful streaming start:
```
DEBUG (MainThread) [custom_components.local_openai.entity] {'role': 'assistant', ...}
```

Confirm no tool calls fired:
```
# Should NOT appear:
DEBUG (MainThread) [custom_components.local_openai.entity] Calling tools: ...
```

Confirm clean finish (no errors after response):
```
# Should NOT appear:
ERROR (MainThread) [custom_components.local_openai] ...
WARNING (MainThread) [custom_components.local_openai] ...
```

### Latency Measurement

Note the wall-clock time from sending the message to the first visible character in the Assist UI — this is Time To First Token (TTFT). Use browser DevTools Network tab filtering on `/api/conversation/process` to get precise timing:

- **Request sent** → timestamp in Headers tab
- **Response first byte** → check Timing tab → "Waiting (TTFB)"
- **Full response** → "Content Download" duration

Record: `TTFT`, `Total response time`, approximate `tokens/sec` (count response words × 1.3 as a rough token estimate).

---

## Test 2: Tool Calling (light.turn_on)

**Goal:** Confirm the integration correctly formats HA tools, passes them to the model, receives a tool call response, executes via HA's LLM API, and completes the loop.

### Setup

- Ensure at least one light entity exists in HA (real or virtual — use **Developer Tools → States** to create a `light.test_light` helper if needed).
- In the subentry config, set `llm_hass_api` to include **Assist** (the default).
- Confirm `parallel_tool_calls` is `True`.

### Steps

1. Open Assist UI, select the `local_openai` agent.
2. Send: `"Turn on the living room light"` (substitute your actual light's friendly name).
3. Observe the light state change in HA.
4. Send: `"Turn on all the lights"` (tests parallel tool calls).
5. Check **Developer Tools → States** to confirm light states changed.

### Expected Outcomes

| Step | Expected |
|---|---|
| Step 2 | Light turns on. Assistant responds with a confirmation sentence. |
| Step 3 | Light entity state is `on` in HA. |
| Step 4 | All lights turn on. If `parallel_tool_calls = True`, a single model response may contain multiple tool calls resolved in one iteration. |

### Log Snippets to Look For

Tool list being sent to model (logged when tools are formatted):
```
DEBUG (MainThread) [homeassistant.helpers.llm] Tools: [{'name': 'HassTurnOn', ...}]
```

Model requesting a tool call:
```
DEBUG (MainThread) [custom_components.local_openai.entity] Calling tools: {'<id>HassTurnOn': {'id': '...', 'name': 'HassTurnOn', 'args': {'name': 'living room light'}}}
```

Tool result injected back:
```
DEBUG (MainThread) [custom_components.local_openai.entity] {'role': 'tool', 'tool_call_id': '...', 'content': '...'}
```

Loop completing (unresponded_tool_results empty):
```
# Should NOT appear more than MAX_TOOL_ITERATIONS (10) times:
DEBUG ... Calling tools: ...
```

### Latency Measurement

Tool calling adds at least one extra model round-trip. Measure:

- **Total latency** from message send to final response (Assist UI wall clock).
- **Number of iterations** — count `Calling tools:` log lines for the request. Each is one full model round-trip.
- For parallel tool calls: confirm all tool calls appear in a **single** `Calling tools:` log entry (one dict with multiple keys).

---

## Test 3: Error Handling (Invalid API Endpoint)

**Goal:** Confirm graceful failure when the backend is unreachable, with no crashes or unhandled exceptions in HA.

### Steps

1. Go to **Settings → Devices & Services → Local OpenAI LLM → Configure**.
2. Change `base_url` to an invalid address (e.g., `http://127.0.0.1:9999`).
3. Save. HA will attempt to reload the entry.
4. Open Assist UI, select the agent.
5. Send: `"Hello"`.
6. Restore the correct `base_url` and confirm the agent recovers.

### Expected Outcomes

| Step | Expected |
|---|---|
| Step 3 | Config entry enters `Setup error` / `Not ready` state in the integrations page. No HA crash. |
| Step 5 | Assist UI shows an error message (e.g., "Sorry, I had a problem talking to the AI"). No Python traceback visible to the user. |
| Step 6 | After reconfigure, agent responds normally — confirms no persistent broken state. |

### Log Snippets to Look For

Entry failing to load (from `__init__.py`):
```
ERROR (MainThread) [homeassistant.config_entries] Error setting up entry ... for local_openai
homeassistant.exceptions.ConfigEntryNotReady: ...
```

Runtime API error during conversation (from `entity.py`):
```
ERROR (MainThread) [custom_components.local_openai.entity] <OpenAIError subclass>
ERROR (MainThread) [custom_components.local_openai.entity] Error talking to API
```

### What Should NOT Appear

```
# No unhandled exceptions:
ERROR (MainThread) [homeassistant.core] Error doing job: ...
# NoHomeAssistant crash/restart logs
```

---

## Test 4: Latency Measurement

**Goal:** Establish a baseline latency profile across different request types for future comparison after modifications.

### Method A: HA Developer Tools (Quick)

1. Open browser DevTools (F12) → Network tab.
2. Filter by `conversation/process`.
3. Send each test message and record from the Timing tab:
   - **TTFB** (Time to First Byte) = server processing + TTFT
   - **Content Download** = streaming duration

### Method B: HA REST API (Repeatable)

```bash
curl -s -w "\nTime: %{time_total}s\n" \
  -H "Authorization: Bearer <YOUR_LONG_LIVED_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"text": "What is 2 plus 2?", "agent_id": "conversation.<your_agent_entity_id>"}' \
  http://homeassistant.local:8123/api/conversation/process
```

Run this 5 times per test case and record min/max/average.

### Baseline Measurements to Record

| Test Case | TTFT (ms) | Total (ms) | Approx tokens/sec | Tool iterations |
|---|---|---|---|---|
| Simple factual (no tools) | | | | 0 |
| Single tool call | | | | 1 |
| Parallel tool calls (2 lights) | | | | 1 |
| Multi-turn (2nd message, history loaded) | | | | 0 |

### Tokens/Sec Estimation

```
tokens_per_sec ≈ (word_count_of_response × 1.3) / content_download_seconds
```

For precise measurement, check if your backend exposes timing metadata. llama.cpp returns `timings` in the final SSE chunk — the integration captures this:

```python
# entity.py — look for this in logs if using llama.cpp:
self.extra_state_attributes = {"timings": event.timings}
```

Check **Developer Tools → States** on the conversation entity for `timings` attributes after a request.

---

## Test 5: Log Analysis

**Goal:** Confirm no unexpected errors or warnings appear during normal operation that could indicate integration issues.

### Steps

1. Clear HA logs: **Settings → System → Logs → Clear**.
2. Run Tests 1 and 2 in sequence (basic conversation + tool call).
3. Download the full log: **Settings → System → Logs → Download Full Log**.
4. Analyse with the filters below.

### Log Analysis Commands

```bash
# Any errors from the integration:
grep -n "ERROR.*local_openai" home-assistant.log

# Any warnings (expected: zero during normal operation):
grep -n "WARNING.*local_openai" home-assistant.log

# Non-JSON-serialisable tool results (indicates a tool returned unexpected data):
grep -n "Attempting string convertion" home-assistant.log

# Unknown message types that couldn't be converted:
grep -n "Could not convert message" home-assistant.log

# Tool iteration count (more than 3 for a simple request is suspicious):
grep -c "Calling tools:" home-assistant.log

# Check streaming worked (should see multiple delta chunks per response):
grep -c "AssistantContentDeltaDict\|'role': 'assistant'" home-assistant.log
```

### Expected Log State After Clean Run

| Check | Expected result |
|---|---|
| `ERROR.*local_openai` | 0 matches |
| `WARNING.*local_openai` | 0 matches |
| `Attempting string convertion` | 0 matches |
| `Could not convert message` | 0 matches |
| `Calling tools:` (for Test 1) | 0 matches |
| `Calling tools:` (for Test 2, single light) | 1 match |

### Known Benign Log Patterns

These are expected and can be ignored:

```
# OpenVINO model server quirk — role defaults to assistant:
# (no log emitted, handled silently in _transform_stream)

# llama.cpp full model path being stripped:
# (handled silently in strip_model_pathing)
```

---

## Results Summary Template

Fill this in after completing all five tests.

| Test | Pass/Fail | Notes |
|---|---|---|
| 1. Basic conversation | | |
| 2. Tool calling (single light) | | |
| 2b. Tool calling (parallel lights) | | |
| 3. Invalid endpoint — entry load | | |
| 3b. Invalid endpoint — runtime error | | |
| 3c. Recovery after reconfigure | | |
| 4. Latency baseline recorded | | |
| 5. Log analysis — zero errors | | |

**Backend:** _(e.g., Ollama 0.x, llama.cpp, LM Studio)_
**Model:** _(e.g., llama3.2:3b, mistral-7b-q4)_
**HA Version:** _(e.g., 2026.4.x)_
**Test Date:** _(YYYY-MM-DD)_

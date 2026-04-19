# Phase 1 Implementation Plan – Tasks 1.1, 1.2, 1.3

## Overview

**Phase:** 1 (Speaker Awareness)  
**Status:** Validation complete (Q1-Q3 PASS), ready for implementation  
**Tasks covered:** 1.1 (Speaker Cache), 1.2 (User Config Manager), 1.3 (Webhook Handler)  
**Dependencies:** All tasks are independent and can be implemented in parallel if desired

**Key principle:** Build **new, isolated modules** first. Only modify existing files (`__init__.py`, `conversation.py`) in Task 1.4 after foundational modules are stable.

***

## Task 1.1 – Speaker Cache Module

### Objective

Create a **short-lived, in-memory cache** that stores speaker metadata from the VoicePipeline webhook and makes it available to the conversation agent.

**Why this exists:**

*   VoicePipeline sends speaker metadata via webhook **before** the conversation request arrives
*   Need to store speaker\_id temporarily (2-5 seconds) until the conversation agent retrieves it
*   Prevent race conditions when multiple satellites send concurrent requests

### Scope

**Responsibilities:**

*   ✅ Store speaker metadata (speaker\_id, confidence, timestamp)
*   ✅ Retrieve most recent speaker within TTL window
*   ✅ Auto-expire old entries
*   ✅ Thread-safe access (async context)

**Non-responsibilities:**

*   ❌ Persistent storage (ephemeral only)
*   ❌ User configuration storage (that's Task 1.2)
*   ❌ Webhook handling (that's Task 1.3)
*   ❌ LLM or TTS logic

### File Structure

**Create:** `custom_components/personality_llm/speaker_cache.py`

**Module exports:**

*   `SpeakerCache` class (singleton pattern via `hass.data`)

### Public Interface

```python
class SpeakerCache:
    """Short-lived cache for speaker metadata from VoicePipeline."""
    
    def __init__(self, hass: HomeAssistant):
        """Initialize cache."""
        
    async def async_put(
        self,
        speaker_id: str,
        confidence: float,
        interaction_id: str | None = None
    ) -> None:
        """
        Store speaker metadata.
        
        Args:
            speaker_id: Speaker identifier from VoicePipeline
            confidence: Recognition confidence (0.0-1.0)
            interaction_id: Optional correlation ID for feedback
        """
        
    async def async_get_recent(
        self,
        max_age_seconds: float = 2.0
    ) -> dict | None:
        """
        Get most recent speaker within TTL window.
        
        Args:
            max_age_seconds: Maximum age of cached entry
            
        Returns:
            {
                "speaker_id": str,
                "confidence": float,
                "interaction_id": str | None,
                "timestamp": float
            } or None if no recent entry
        """
        
    async def async_cleanup(self) -> int:
        """
        Remove expired entries.
        
        Returns:
            Number of entries removed
        """
```

### Data Model

**Cache entry structure:**

```python
@dataclass
class SpeakerCacheEntry:
    speaker_id: str
    confidence: float
    timestamp: float  # time.time()
    interaction_id: str | None = None
```

**Storage:** In-memory dict, keyed by timestamp (for ordering)

```python
self._cache: dict[float, SpeakerCacheEntry] = {}
```

### Implementation Details

**Key design decisions:**

1.  **Storage:** Use `hass.data[DOMAIN]["speaker_cache"]` (not instance variable) for singleton
2.  **Cleanup strategy:** Automatic cleanup on every `async_get_recent()` call (lazy cleanup)
3.  **Concurrency:** Use async patterns, no explicit locks needed (HA's event loop is single-threaded)
4.  **TTL:** Default 2 seconds (configurable via const.py)

**Edge cases:**

| Scenario                     | Behavior                                                          |
| ---------------------------- | ----------------------------------------------------------------- |
| No webhook received          | `async_get_recent()` returns `None`, agent uses "default" speaker |
| Multiple concurrent requests | Returns **most recent** entry (sorted by timestamp)               |
| Webhook arrives late         | If within TTL, still valid; if expired, returns `None`            |
| Invalid speaker\_id          | Stored as-is (validation happens in webhook handler)              |

### Error Handling

```python
# In async_put
try:
    # Validate input
    if not speaker_id or not isinstance(speaker_id, str):
        _LOGGER.warning(f"Invalid speaker_id: {speaker_id}")
        return
    
    if not (0.0 <= confidence <= 1.0):
        _LOGGER.warning(f"Invalid confidence: {confidence}")
        confidence = 0.0  # Fallback
    
    # Store entry
    # ...
except Exception as e:
    _LOGGER.error(f"Failed to store speaker cache: {e}")
    # Don't raise (non-fatal)
```

### Test Strategy

**Unit tests:** `tests/unit/test_speaker_cache.py`

```python
async def test_put_and_get():
    """Test basic put/get flow."""
    cache = SpeakerCache(hass)
    await cache.async_put("paul", 0.95)
    entry = await cache.async_get_recent()
    assert entry["speaker_id"] == "paul"
    assert entry["confidence"] == 0.95

async def test_ttl_expiry():
    """Test entries expire after TTL."""
    cache = SpeakerCache(hass)
    await cache.async_put("paul", 0.95)
    await asyncio.sleep(3)  # Wait longer than TTL
    entry = await cache.async_get_recent(max_age_seconds=2.0)
    assert entry is None  # Expired

async def test_most_recent():
    """Test returns most recent when multiple entries exist."""
    cache = SpeakerCache(hass)
    await cache.async_put("paul", 0.9)
    await asyncio.sleep(0.1)
    await cache.async_put("sarah", 0.95)
    entry = await cache.async_get_recent()
    assert entry["speaker_id"] == "sarah"  # Most recent

async def test_cleanup():
    """Test cleanup removes old entries."""
    cache = SpeakerCache(hass)
    await cache.async_put("paul", 0.9)
    await asyncio.sleep(3)
    removed = await cache.async_cleanup()
    assert removed == 1
    assert len(cache._cache) == 0
```

**Integration tests:**  
Test webhook → cache → conversation agent flow in Task 1.4.

### Acceptance Criteria

*   [ ] `SpeakerCache` class implemented with all public methods
*   [ ] Entries expire after configurable TTL (default 2s)
*   [ ] Returns most recent entry when multiple exist
*   [ ] Handles invalid inputs gracefully (no crashes)
*   [ ] Unit tests pass (coverage >90%)
*   [ ] Documented with docstrings

### Implementation Steps

```markdown
1. [ ] Create `speaker_cache.py` file
2. [ ] Define `SpeakerCacheEntry` dataclass
3. [ ] Implement `SpeakerCache.__init__`
4. [ ] Implement `async_put()` with validation
5. [ ] Implement `async_get_recent()` with TTL filtering
6. [ ] Implement `async_cleanup()` (lazy cleanup)
7. [ ] Add logging (debug level for put/get, warning for issues)
8. [ ] Write unit tests
9. [ ] Run tests, achieve >90% coverage
10. [ ] Document usage in docstrings
11. [ ] Commit: "feat: add speaker cache module"
```

### Risks & Mitigations

| Risk                                  | Mitigation                                        |
| ------------------------------------- | ------------------------------------------------- |
| Race condition (2 requests within ms) | Return most recent by timestamp (acceptable)      |
| Memory leak (cache grows unbounded)   | Automatic cleanup on every get (lazy GC)          |
| TTL too short (webhook arrives late)  | Make TTL configurable (2s default, 5s max)        |
| Invalid data in cache                 | Validate in webhook handler (Task 1.3), not cache |

***

## Task 1.2 – User Config Manager

### Objective

Create a **persistent storage manager** for per-speaker configuration (personality prompts, LLM settings, TTS preferences).

**Why this exists:**

*   Each speaker needs their own personality, model, and TTS config
*   Config must persist across HA restarts
*   Config must be managed via HA's config flow UI (Task 1.5)

### Scope

**Responsibilities:**

*   ✅ Load/save per-speaker configs from HA storage
*   ✅ Provide CRUD operations (get, add, update, delete)
*   ✅ Fallback to "default" speaker when speaker\_id not found
*   ✅ Schema validation and defaults

**Non-responsibilities:**

*   ❌ UI for editing configs (that's Task 1.5 config flow)
*   ❌ LLM execution (that's conversation.py)
*   ❌ TTS execution (deferred to Phase 4)
*   ❌ Speaker cache management (that's Task 1.1)

### File Structure

**Create:** `custom_components/personality_llm/user_config.py`

**Module exports:**

*   `UserConfigManager` class

### Public Interface

```python
class UserConfigManager:
    """Manage per-speaker configuration storage."""
    
    def __init__(self, hass: HomeAssistant):
        """Initialize config manager."""
        
    async def async_load(self) -> None:
        """Load configs from HA storage."""
        
    async def async_save(self) -> None:
        """Save configs to HA storage."""
        
    def get_user(self, speaker_id: str) -> dict:
        """
        Get config for speaker, fallback to 'default'.
        
        Args:
            speaker_id: Speaker identifier
            
        Returns:
            User config dict (never None, always returns default if not found)
        """
        
    async def async_add_user(self, speaker_id: str, config: dict) -> None:
        """
        Add or update user config.
        
        Args:
            speaker_id: Speaker identifier
            config: Full user config dict
        """
        
    async def async_delete_user(self, speaker_id: str) -> None:
        """
        Delete user config.
        
        Args:
            speaker_id: Speaker identifier
            
        Raises:
            ValueError: If trying to delete 'default' user
        """
        
    def list_users(self) -> list[str]:
        """Return list of all speaker_ids."""
```

### Data Model

**Storage file:** `.storage/personality_llm_users`

**Schema:**

```python
{
    "version": 1,
    "users": {
        "default": {
            "display_name": "Guest",
            "personality": {
                "system_prompt": "You are a helpful assistant. Keep responses concise.",
                "temperature": 0.7,
                "max_tokens": 150
            },
            "llm": {
                "provider": "ollama",
                "model": "gpt-oss-20b",
                "api_url": "http://localhost:11434/v1",
                "api_key": "",
                "fallback_provider": "ollama",
                "fallback_model": "gemma-4-26b"
            },
            "tts": {
                # Deferred to Phase 4, but include schema now
                "engine": "tts.piper",
                "voice": "en_US-ryan-medium",
                "speed": 1.0,
                "pitch": 0
            }
        },
        "paul": {
            "display_name": "Paul",
            "personality": {
                "system_prompt": "You are Paul's technical assistant. Be concise and precise.",
                "temperature": 0.6,
                "max_tokens": 100
            },
            "llm": {
                "provider": "ollama",
                "model": "gpt-oss-20b",
                "api_url": "http://localhost:11434/v1",
                "api_key": "",
                "fallback_provider": "anthropic",
                "fallback_model": "claude-3-5-sonnet-20241022"
            },
            "tts": {
                "engine": "tts.piper",
                "voice": "en_US-lessac-medium",
                "speed": 1.0,
                "pitch": 0
            }
        }
    }
}
```

**Default config template (const.py):**

```python
DEFAULT_USER_CONFIG = {
    "display_name": "Guest",
    "personality": {
        "system_prompt": "You are a helpful, polite assistant. Keep responses under 3 sentences unless asked for detail.",
        "temperature": 0.7,
        "max_tokens": 150
    },
    "llm": {
        "provider": "ollama",
        "model": "gpt-oss-20b",
        "api_url": "http://localhost:11434/v1",
        "api_key": "",
        "fallback_provider": "ollama",
        "fallback_model": "gpt-oss-20b"
    },
    "tts": {
        "engine": "tts.piper",
        "voice": "en_US-ryan-medium",
        "speed": 1.0,
        "pitch": 0
    }
}
```

### Implementation Details

**Key design decisions:**

1.  **Storage:** Use HA's `Store` helper (`homeassistant.helpers.storage.Store`)
2.  **Loading:** Async load once at startup, cache in memory
3.  **Fallback:** Always return "default" config if speaker not found (never None)
4.  **Validation:** Basic schema validation (type checking, required fields)

**Edge cases:**

| Scenario              | Behavior                                  |
| --------------------- | ----------------------------------------- |
| Speaker not found     | Return "default" user config              |
| Storage file missing  | Create with default config only           |
| Storage file corrupt  | Log error, create new with default config |
| Delete "default" user | Raise ValueError (protected)              |
| Missing config fields | Merge with default config (fill gaps)     |

### Error Handling

```python
# In async_load
try:
    data = await self.store.async_load()
    if data is None:
        _LOGGER.info("No user config found, creating defaults")
        data = self._get_default_storage()
    
    # Validate schema
    if "version" not in data or "users" not in data:
        _LOGGER.warning("Invalid config schema, resetting to defaults")
        data = self._get_default_storage()
    
    self._config = data
except Exception as e:
    _LOGGER.error(f"Failed to load user config: {e}")
    self._config = self._get_default_storage()

# In get_user
def get_user(self, speaker_id: str) -> dict:
    if speaker_id not in self._config["users"]:
        _LOGGER.debug(f"Speaker {speaker_id} not found, using default")
        speaker_id = "default"
    
    return self._config["users"][speaker_id]
```

### Test Strategy

**Unit tests:** `tests/unit/test_user_config.py`

```python
async def test_load_missing_file():
    """Test creates default config when file missing."""
    manager = UserConfigManager(hass)
    await manager.async_load()
    assert "default" in manager._config["users"]

async def test_get_user_fallback():
    """Test returns default for unknown speaker."""
    manager = UserConfigManager(hass)
    await manager.async_load()
    config = manager.get_user("unknown_speaker")
    assert config["display_name"] == "Guest"  # Default

async def test_add_user():
    """Test adding new user."""
    manager = UserConfigManager(hass)
    await manager.async_load()
    
    paul_config = {
        "display_name": "Paul",
        "personality": {"system_prompt": "Test", "temperature": 0.7, "max_tokens": 100},
        "llm": {...},
        "tts": {...}
    }
    await manager.async_add_user("paul", paul_config)
    
    assert "paul" in manager.list_users()
    assert manager.get_user("paul")["display_name"] == "Paul"

async def test_delete_default_protected():
    """Test cannot delete default user."""
    manager = UserConfigManager(hass)
    await manager.async_load()
    
    with pytest.raises(ValueError):
        await manager.async_delete_user("default")

async def test_schema_validation():
    """Test validates and fills missing fields."""
    manager = UserConfigManager(hass)
    await manager.async_load()
    
    incomplete_config = {"display_name": "Test"}  # Missing personality, llm, tts
    # Should merge with defaults
    # (Implementation detail: decide if you auto-fill or reject)
```

### Acceptance Criteria

*   [ ] `UserConfigManager` class implemented with all CRUD methods
*   [ ] Persists to `.storage/personality_llm_users`
*   [ ] Loads on init, caches in memory
*   [ ] Always returns valid config (fallback to default)
*   [ ] Cannot delete "default" user
*   [ ] Unit tests pass (coverage >90%)
*   [ ] Schema documented

### Implementation Steps

```markdown
1. [ ] Create `user_config.py` file
2. [ ] Define `DEFAULT_USER_CONFIG` in `const.py`
3. [ ] Implement `UserConfigManager.__init__` (setup Store)
4. [ ] Implement `async_load()` with error handling
5. [ ] Implement `async_save()`
6. [ ] Implement `get_user()` with fallback
7. [ ] Implement `async_add_user()` with validation
8. [ ] Implement `async_delete_user()` with protection
9. [ ] Implement `list_users()`
10. [ ] Add schema validation helper
11. [ ] Write unit tests
12. [ ] Run tests, achieve >90% coverage
13. [ ] Commit: "feat: add user config manager"
```

### Risks & Mitigations

| Risk                          | Mitigation                                      |
| ----------------------------- | ----------------------------------------------- |
| Storage corruption            | Validate on load, reset to default if corrupt   |
| Concurrent writes             | HA is single-threaded, use async properly       |
| Schema evolution (future)     | Version field in storage, migration logic later |
| Large configs (many speakers) | Acceptable (hundreds of users = \~1MB)          |

***

## Task 1.3 – Webhook Handler

### Objective

Register a **webhook endpoint** in Home Assistant that receives speaker metadata from the external VoicePipeline and stores it in the speaker cache.

**Why this exists:**

*   VoicePipeline (external) needs a way to send speaker\_id to HA
*   Webhook is fire-and-forget, non-blocking
*   Decouples VoicePipeline from conversation agent lifecycle

### Scope

**Responsibilities:**

*   ✅ Register webhook endpoint with HA
*   ✅ Validate incoming payload
*   ✅ Store metadata in speaker cache (Task 1.1)
*   ✅ Map speaker\_id to HA user\_id (shadow user creation)
*   ✅ Return success/error JSON responses

**Non-responsibilities:**

*   ❌ Speaker identification (done by VoicePipeline)
*   ❌ Conversation processing (done by conversation agent)
*   ❌ User config storage (done by Task 1.2)
*   ❌ LLM or TTS logic

### File Structure

**Modify:** `custom_components/personality_llm/__init__.py`

**Add:**

*   Webhook registration in `async_setup_entry()`
*   `async_handle_webhook()` function
*   `_get_or_create_user_id()` helper

### Public Interface

**Webhook endpoint:**

    POST /api/webhook/personality_llm_input
    Content-Type: application/json

    {
      "speaker_id": "paul",
      "confidence": 0.92,
      "timestamp": "2026-04-19T12:34:56.789Z",
      "interaction_id": "550e8400-e29b-41d4-a716-446655440000"  // optional
    }

**Response:**

```json
// Success
{
  "success": true,
  "user_id": "abc123..."
}

// Error
{
  "success": false,
  "error": "Invalid speaker_id format"
}
```

### Data Model

**Payload schema:**

```python
@dataclass
class WebhookPayload:
    speaker_id: str           # Required: alphanumeric + underscore, max 50 chars
    confidence: float         # Required: 0.0-1.0
    timestamp: str            # Required: ISO 8601 UTC
    interaction_id: str | None = None  # Optional: UUID for feedback correlation
```

**Validation rules:**

| Field            | Rule                                     | Error Message                |
| ---------------- | ---------------------------------------- | ---------------------------- |
| `speaker_id`     | Required, regex `^[a-zA-Z0-9_]{1,50}$`   | "Invalid speaker\_id format" |
| `confidence`     | Required, float 0.0-1.0                  | "Invalid confidence value"   |
| `timestamp`      | Required, string (not validated further) | "Missing timestamp"          |
| `interaction_id` | Optional, string                         | (none)                       |

### Implementation Details

**Key design decisions:**

1.  **Registration:** Use `hass.components.webhook.async_register()`
2.  **User mapping:** Create HA "shadow users" for each speaker\_id
3.  **Non-blocking:** Webhook returns immediately (does not wait for conversation)
4.  **Idempotent:** Safe to call multiple times with same speaker\_id

**Shadow user naming:**

```python
# speaker_id "paul" → HA user name "voice_speaker_paul"
user_name = f"voice_speaker_{speaker_id}"
```

**Shadow user properties:**

*   `system_generated=True` (not shown in HA user list)
*   No password (cannot log in)
*   Used only for Context.user\_id mapping

### Error Handling

```python
async def async_handle_webhook(hass, webhook_id, request):
    try:
        data = await request.json()
    except Exception as e:
        _LOGGER.warning(f"Invalid JSON in webhook: {e}")
        return web.json_response(
            {"success": False, "error": "Invalid JSON"},
            status=400
        )
    
    # Validate speaker_id
    speaker_id = data.get("speaker_id")
    if not speaker_id or not re.match(r'^[a-zA-Z0-9_]{1,50}$', speaker_id):
        return web.json_response(
            {"success": False, "error": "Invalid speaker_id format"},
            status=400
        )
    
    # Validate confidence
    confidence = data.get("confidence")
    if confidence is None or not (0.0 <= confidence <= 1.0):
        return web.json_response(
            {"success": False, "error": "Invalid confidence value"},
            status=400
        )
    
    # Store in cache
    try:
        cache = hass.data[DOMAIN]["speaker_cache"]
        await cache.async_put(
            speaker_id,
            confidence,
            data.get("interaction_id")
        )
    except Exception as e:
        _LOGGER.error(f"Failed to store speaker cache: {e}")
        return web.json_response(
            {"success": False, "error": "Internal error"},
            status=500
        )
    
    # Map to HA user
    try:
        user_id = await _get_or_create_user_id(hass, speaker_id)
    except Exception as e:
        _LOGGER.error(f"Failed to create shadow user: {e}")
        # Non-fatal, continue
        user_id = None
    
    return web.json_response({
        "success": True,
        "user_id": user_id
    })
```

### Test Strategy

**Integration tests:** `tests/integration/test_webhook.py`

```python
async def test_webhook_valid_payload(hass, aiohttp_client):
    """Test webhook accepts valid payload."""
    client = await aiohttp_client(hass.http.app)
    
    resp = await client.post(
        "/api/webhook/personality_llm_input",
        json={
            "speaker_id": "paul",
            "confidence": 0.95,
            "timestamp": "2026-04-19T12:00:00Z"
        }
    )
    
    assert resp.status == 200
    data = await resp.json()
    assert data["success"] is True
    assert "user_id" in data

async def test_webhook_invalid_speaker_id(hass, aiohttp_client):
    """Test webhook rejects invalid speaker_id."""
    client = await aiohttp_client(hass.http.app)
    
    resp = await client.post(
        "/api/webhook/personality_llm_input",
        json={
            "speaker_id": "invalid@name!",  # Special chars not allowed
            "confidence": 0.95,
            "timestamp": "2026-04-19T12:00:00Z"
        }
    )
    
    assert resp.status == 400
    data = await resp.json()
    assert data["success"] is False
    assert "speaker_id" in data["error"]

async def test_webhook_stores_in_cache(hass):
    """Test webhook stores data in speaker cache."""
    # POST webhook
    # Check cache.async_get_recent() returns the data
    
async def test_shadow_user_creation(hass):
    """Test webhook creates shadow HA user."""
    # POST webhook with speaker_id "paul"
    # Check hass.auth.async_get_users() contains "voice_speaker_paul"
```

**Manual tests:**

*   Use `curl` or Postman to POST to webhook
*   Check HA logs for webhook receipt
*   Verify speaker cache populated

### Acceptance Criteria

*   [ ] Webhook endpoint registered at `/api/webhook/personality_llm_input`
*   [ ] Validates payload (speaker\_id format, confidence range)
*   [ ] Stores metadata in speaker cache
*   [ ] Creates shadow HA users for new speaker\_ids
*   [ ] Returns JSON response (success/error)
*   [ ] Integration tests pass
*   [ ] Documented with examples

### Implementation Steps

```markdown
1. [ ] In `__init__.py`, import webhook helpers
2. [ ] In `async_setup_entry()`, register webhook:
       `webhook.async_register(hass, DOMAIN, "personality_llm_input", async_handle_webhook)`
3. [ ] Implement `async_handle_webhook()` function
4. [ ] Add payload validation (speaker_id regex, confidence range)
5. [ ] Call `speaker_cache.async_put()` with validated data
6. [ ] Implement `_get_or_create_user_id()` helper
7. [ ] Add comprehensive error handling
8. [ ] Write integration tests
9. [ ] Test manually with curl
10. [ ] Document webhook API in `docs/WEBHOOK_API.md`
11. [ ] Commit: "feat: add webhook handler for speaker metadata"
```

### Risks & Mitigations

| Risk                           | Mitigation                                  |
| ------------------------------ | ------------------------------------------- |
| Malicious payloads (injection) | Strict validation (regex, type checks)      |
| Webhook spam (DoS)             | Accept (HA has rate limiting at HTTP layer) |
| Speaker\_id collision          | Use unique naming (voice\_speaker\_prefix)  |
| Shadow users clutter           | Mark as system\_generated (hidden from UI)  |

***

## Integration & Testing (Tasks 1.1-1.3 Combined)

### End-to-End Test Scenario

**Setup:**

1.  Install Tasks 1.1, 1.2, 1.3 in HA
2.  Restart HA
3.  Add "paul" user via UI (Task 1.5, or manually in storage)

**Test flow:**

```bash
# 1. POST webhook (simulating VoicePipeline)
curl -X POST http://homeassistant.local:8123/api/webhook/personality_llm_input \
  -H "Content-Type: application/json" \
  -d '{
    "speaker_id": "paul",
    "confidence": 0.95,
    "timestamp": "2026-04-19T14:00:00Z"
  }'

# Expected response:
# {"success": true, "user_id": "..."}

# 2. Check speaker cache (via logs or debug service)
# Expected: Entry exists with speaker_id="paul", confidence=0.95

# 3. Check HA users
# Expected: User "voice_speaker_paul" exists (system_generated=True)

# 4. Trigger conversation (Task 1.4 will use cached speaker)
# (Not yet implemented)
```

### Combined Acceptance Criteria

Tasks 1.1-1.3 are complete when:

*   [ ] Webhook accepts speaker metadata and returns success
*   [ ] Speaker cache stores and retrieves metadata correctly
*   [ ] User config manager loads/saves per-speaker configs
*   [ ] Shadow HA users created automatically
*   [ ] All unit tests pass (>90% coverage each module)
*   [ ] Integration test passes (webhook → cache → user creation)
*   [ ] No errors in HA logs during normal operation
*   [ ] Code documented with docstrings
*   [ ] Committed to `feature/phase1-speaker-awareness` branch

***

## Git Workflow for Tasks 1.1-1.3

### Option A: Sequential Implementation (Recommended)

```powershell
# Start from Phase 1 branch
git checkout feature/phase1-speaker-awareness

# Task 1.1
git checkout -b feature/task-1.1-speaker-cache
# Implement, test, commit
git checkout feature/phase1-speaker-awareness
git merge feature/task-1.1-speaker-cache
git branch -d feature/task-1.1-speaker-cache

# Task 1.2
git checkout -b feature/task-1.2-user-config
# Implement, test, commit
git checkout feature/phase1-speaker-awareness
git merge feature/task-1.2-user-config
git branch -d feature/task-1.2-user-config

# Task 1.3
git checkout -b feature/task-1.3-webhook
# Implement, test, commit
git checkout feature/phase1-speaker-awareness
git merge feature/task-1.3-webhook
git branch -d feature/task-1.3-webhook

# Integration test
# Test all 3 modules together
git add tests/integration/
git commit -m "test: add integration tests for tasks 1.1-1.3"
git push origin feature/phase1-speaker-awareness
```

### Option B: Parallel Implementation (Advanced)

If implementing all 3 in parallel (on 2 computers):

```powershell
# Computer A: Task 1.1
git checkout -b feature/task-1.1-speaker-cache
# Work, commit, push

# Computer B: Task 1.2
git checkout -b feature/task-1.2-user-config
# Work, commit, push

# Later: Merge all to phase1 branch
git checkout feature/phase1-speaker-awareness
git merge feature/task-1.1-speaker-cache
git merge feature/task-1.2-user-config
git merge feature/task-1.3-webhook
```

***

## Next Steps After 1.1-1.3 Complete

Once all three tasks pass:

1.  **Task 1.4:** Conversation injection (modify `conversation.py` to use cache and config)
2.  **Task 1.5:** Multi-speaker config flow UI
3.  **Integration testing:** Full speaker-aware flow (webhook → cache → conversation → LLM)
4.  **Merge to main:** After all Phase 1 tasks complete and tested

***

## Quick Reference – Module Responsibilities

| Module       | Purpose                           | Dependencies | Modified Files                                |
| ------------ | --------------------------------- | ------------ | --------------------------------------------- |
| **Task 1.1** | Speaker cache (ephemeral storage) | None         | `speaker_cache.py` (new)                      |
| **Task 1.2** | User config (persistent storage)  | HA Store     | `user_config.py` (new), `const.py` (defaults) |
| **Task 1.3** | Webhook handler                   | Task 1.1     | `__init__.py` (modify)                        |

All three are **foundational modules** — no feature behavior yet, just infrastructure.

**You are ready to start implementation.** Begin with **Task 1.1** (speaker cache) as it has no dependencies.

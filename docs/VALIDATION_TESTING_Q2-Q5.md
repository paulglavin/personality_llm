# Phase 1 Validation Code – Q2 through Q5

Save this as: `docs/VALIDATION_TESTING_Q2-Q5.md`

***

## Q2 – System Prompt Injection Point

### What We're Validating

*   System prompt is read **once** from config
*   Passed to `chat_log.async_provide_llm_data()`
*   No other prompt construction points exist

### Code Changes

**File:** `custom_components/personality_llm/conversation.py`

**Location:** Around line 58 (where `system_prompt` is first assigned)

**Add this logging:**

```python
    options = self.subentry.data
    system_prompt = options.get(CONF_PROMPT)
    
    # ============ VALIDATION Q2 START ============
    import logging
    _LOGGER = logging.getLogger(__name__)
    
    _LOGGER.warning(f"[VALIDATE-Q2-READ] system_prompt from config (first 80 chars): {system_prompt[:80] if system_prompt else 'NONE'}...")
    _LOGGER.warning(f"[VALIDATE-Q2-READ] Full length: {len(system_prompt) if system_prompt else 0} chars")
    # ============ VALIDATION Q2 END ============
```

**Location:** Around line 68-73 (where `async_provide_llm_data` is called)

**Add this logging just BEFORE the call:**

```python
    # ============ VALIDATION Q2 START ============
    _LOGGER.warning(f"[VALIDATE-Q2-PASS] About to pass system_prompt to chat_log.async_provide_llm_data")
    _LOGGER.warning(f"[VALIDATE-Q2-PASS] Prompt unchanged: {system_prompt[:80] if system_prompt else 'NONE'}...")
    # ============ VALIDATION Q2 END ============
    
    await chat_log.async_provide_llm_data(
        system_prompt=system_prompt,
        # ... rest of call
    )
```

### Additional Verification

**After adding logging, search for other prompt references:**

```powershell
cd custom_components\personality_llm
grep -n "system_prompt\|CONF_PROMPT" *.py
```

**Expected output:**

*   Only the locations you just logged
*   Plus const.py definition
*   If you see OTHER construction points, log those too

### Test Scenario

```yaml
service: conversation.process
data:
  agent_id: conversation.personality_llm
  text: "Hello assistant"
```

### Expected Logs (PASS)

    [VALIDATE-Q2-READ] system_prompt from config (first 80 chars): You are a helpful assistant...
    [VALIDATE-Q2-READ] Full length: 245 chars
    [VALIDATE-Q2-PASS] About to pass system_prompt to chat_log.async_provide_llm_data
    [VALIDATE-Q2-PASS] Prompt unchanged: You are a helpful assistant...

### Pass/Fail Criteria

✅ **PASS if:**

*   Both log pairs appear exactly once per request
*   Prompt text is identical in READ and PASS logs
*   No other `system_prompt` construction found in grep

❌ **FAIL if:**

*   Logs appear multiple times (multiple construction points)
*   Prompt text differs between READ and PASS (transformation happening)
*   Grep finds other prompt manipulation code

### Remove Logging After Validation

Delete all `# ============ VALIDATION Q2 START/END ============` blocks.

***

## Q3 – Model Selection Override

### What We're Validating

*   `self.model` is set at `__init__` in `entity.py`
*   Used in `model_args` dict later
*   Call path: init → conversation call → model\_args construction

### Code Changes

**File:** `custom_components/personality_llm/entity.py`

**Location:** In `__init__` where `self.model` is assigned (around line 243)

**Add this logging:**

```python
    self.model = subentry.data[CONF_MODEL]
    
    # ============ VALIDATION Q3 START ============
    import logging
    _LOGGER = logging.getLogger(__name__)
    
    _LOGGER.warning(f"[VALIDATE-Q3-INIT] Entity.__init__ called")
    _LOGGER.warning(f"[VALIDATE-Q3-INIT] self.model set to: {self.model}")
    # ============ VALIDATION Q3 END ============
```

**Location:** Where `model_args` is built (around line 438)

**Add this logging:**

```python
    model_args = {
        "model": self.model,
        # ... other args ...
    }
    
    # ============ VALIDATION Q3 START ============
    _LOGGER.warning(f"[VALIDATE-Q3-MODELARGS] Building model_args")
    _LOGGER.warning(f"[VALIDATE-Q3-MODELARGS] model_args['model'] = {model_args.get('model')}")
    _LOGGER.warning(f"[VALIDATE-Q3-MODELARGS] Full model_args keys: {list(model_args.keys())}")
    # ============ VALIDATION Q3 END ============
```

**File:** `custom_components/personality_llm/conversation.py`

**Location:** Where `_async_handle_chat_log` is called (around line 77)

**Add this logging just BEFORE the call:**

```python
    # ============ VALIDATION Q3 START ============
    _LOGGER.warning(f"[VALIDATE-Q3-CONV] About to call _async_handle_chat_log")
    # ============ VALIDATION Q3 END ============
    
    await self._async_handle_chat_log(
        chat_log,
        user_input=user_input,
        # ...
    )
```

### Test Scenario

Same as Q2:

```yaml
service: conversation.process
data:
  agent_id: conversation.personality_llm
  text: "What time is it?"
```

### Expected Logs (PASS)

    [VALIDATE-Q3-INIT] Entity.__init__ called
    [VALIDATE-Q3-INIT] self.model set to: gpt-oss-20b
    [VALIDATE-Q3-CONV] About to call _async_handle_chat_log
    [VALIDATE-Q3-MODELARGS] Building model_args
    [VALIDATE-Q3-MODELARGS] model_args['model'] = gpt-oss-20b
    [VALIDATE-Q3-MODELARGS] Full model_args keys: ['model', 'temperature', ...]

**Order confirms:**

1.  Init happens first (once per HA restart)
2.  Conversation call happens per request
3.  Model args built inside that call

### Pass/Fail Criteria

✅ **PASS if:**

*   Logs appear in order: INIT → CONV → MODELARGS
*   Model value consistent across all logs
*   MODELARGS shows `model` is a key in the dict

❌ **FAIL if:**

*   Order is different (call path not as expected)
*   Model value is None or different
*   MODELARGS logs never appear (built elsewhere)

### Remove Logging After Validation

Delete all `# ============ VALIDATION Q3 START/END ============` blocks from both files.

***

## Q4 – TTS Voice Override Hook

### What We're Validating

*   `user_input.tts_options` exists and is accessible
*   Can be mutated before building `ConversationResult`
*   Mutation doesn't break result construction

### Code Changes

**File:** `custom_components/personality_llm/conversation.py`

**Location:** Just BEFORE `conversation.async_get_result_from_chat_log()` is called (around line 81)

**Add this logging:**

```python
    # ============ VALIDATION Q4 START ============
    import logging
    _LOGGER = logging.getLogger(__name__)
    
    _LOGGER.warning(f"[VALIDATE-Q4-BEFORE] user_input.tts_options BEFORE mutation: {getattr(user_input, 'tts_options', 'ATTR_NOT_FOUND')}")
    
    # Test mutation (temporary)
    if hasattr(user_input, 'tts_options'):
        original_tts = user_input.tts_options
        user_input.tts_options = {**(user_input.tts_options or {}), "test_validation_voice": "q4_test_voice"}
        _LOGGER.warning(f"[VALIDATE-Q4-MUTATE] Successfully mutated tts_options")
        _LOGGER.warning(f"[VALIDATE-Q4-MUTATE] New value: {user_input.tts_options}")
    else:
        _LOGGER.warning(f"[VALIDATE-Q4-MUTATE] FAIL - user_input has no tts_options attribute")
    # ============ VALIDATION Q4 END ============
    
    return conversation.async_get_result_from_chat_log(user_input, chat_log)
```

**After the return, add:**

```python
    return conversation.async_get_result_from_chat_log(user_input, chat_log)
    
    # ============ VALIDATION Q4 START ============
    # If we reach here without exceptions, mutation worked
    _LOGGER.warning(f"[VALIDATE-Q4-AFTER] Result built successfully after mutation")
    # ============ VALIDATION Q4 END ============
```

**Note:** The AFTER log may not appear if `async_get_result_from_chat_log` is the final return. That's okay — no exception = success.

### Test Scenario

```yaml
service: conversation.process
data:
  agent_id: conversation.personality_llm
  text: "Say hello"
```

### Expected Logs (PASS)

    [VALIDATE-Q4-BEFORE] user_input.tts_options BEFORE mutation: None
    [VALIDATE-Q4-MUTATE] Successfully mutated tts_options
    [VALIDATE-Q4-MUTATE] New value: {'test_validation_voice': 'q4_test_voice'}

OR if tts\_options already exists:

    [VALIDATE-Q4-BEFORE] user_input.tts_options BEFORE mutation: {'existing_key': 'value'}
    [VALIDATE-Q4-MUTATE] Successfully mutated tts_options
    [VALIDATE-Q4-MUTATE] New value: {'existing_key': 'value', 'test_validation_voice': 'q4_test_voice'}

**Key validation:**

*   No exceptions during execution
*   Mutation succeeds

### Pass/Fail Criteria

✅ **PASS if:**

*   `user_input.tts_options` exists (even if None)
*   Mutation succeeds without exceptions
*   Result builds without errors

❌ **FAIL if:**

*   `tts_options` attribute not found
*   Mutation raises exception (read-only)
*   HA crashes or returns error

### Remove Logging After Validation

Delete all `# ============ VALIDATION Q4 START/END ============` blocks.

**Important:** Remove the **test mutation** code too (the `user_input.tts_options = ...` line). This was only for validation.

***

## Q5 – Minimal-Change Pattern Validation

### What We're Validating

*   All changes from Q1-Q4 fit in `conversation.py` and `entity.py` only
*   No other files require modification for speaker awareness

### Code Changes

**None** — this is a meta-validation based on Q1-Q4 outcomes.

### Validation Method

After completing Q1-Q4, review your findings:

**Checklist:**

```markdown
## Q5 Validation Checklist

- [ ] Q1 (Speaker ID): Validated in `conversation.py` only? (YES/NO)
- [ ] Q2 (System prompt): Validated in `conversation.py` only? (YES/NO)
- [ ] Q3 (Model selection): Validated in `conversation.py` + `entity.py`? (YES/NO)
- [ ] Q4 (TTS hook): Validated in `conversation.py` only? (YES/NO)
- [ ] Any other files modified during validation? (YES/NO)

**If all answers are as expected:** Q5 PASS
**If any unexpected files touched:** Q5 FAIL (document which files and why)
```

### Expected Outcome (PASS)

**Files requiring modification (validated):**

*   ✅ `conversation.py` (speaker ID, system prompt, TTS hook)
*   ✅ `entity.py` (model selection)
*   ✅ NEW: `speaker_cache.py` (new module, not yet created)
*   ✅ NEW: `user_config.py` (new module, not yet created)

**Files NOT requiring modification:**

*   ✅ Tool execution code (untouched)
*   ✅ Error handling (untouched)
*   ✅ Response building core logic (untouched)

### Pass/Fail Criteria

✅ **PASS if:**

*   Speaker awareness can be implemented by modifying only 2 existing files + adding 2 new modules
*   Upstream diff surface area is minimal

❌ **FAIL if:**

*   Q1-Q4 revealed need to modify additional core files
*   Call paths are more complex than expected

### Documentation

Update `docs/VALIDATION_LOG.md` Q5 section with the checklist results.

***

## Execution Order for Q2-Q5

### Day 1: Q2 and Q3

**Morning (Q2):**

1.  Add Q2 logging to `conversation.py`
2.  Search for other `system_prompt` references
3.  Deploy, restart HA
4.  Test, capture logs
5.  Document in `VALIDATION_LOG.md`
6.  Remove Q2 logging
7.  Commit: `"docs: Q2 validation complete"`

**Afternoon (Q3):**

1.  Add Q3 logging to `entity.py` and `conversation.py`
2.  Deploy, restart HA
3.  Test, capture logs
4.  Document in `VALIDATION_LOG.md`
5.  Remove Q3 logging
6.  Commit: `"docs: Q3 validation complete"`

### Day 2: Q4 and Q5

**Morning (Q4):**

1.  Add Q4 logging to `conversation.py`
2.  Deploy, restart HA
3.  Test, capture logs
4.  Document in `VALIDATION_LOG.md`
5.  **Remove Q4 logging AND test mutation code**
6.  Commit: `"docs: Q4 validation complete"`

**Afternoon (Q5):**

1.  Review Q1-Q4 outcomes
2.  Fill Q5 checklist
3.  Document in `VALIDATION_LOG.md`
4.  Commit: `"docs: Q5 validation complete (all Q1-Q5 PASS)"`

***

## Git Workflow Per Question

**For each Q (Q2, Q3, Q4):**

```powershell
# Add logging
# Edit files, save

# Commit validation code
git add custom_components\personality_llm\*.py
git commit -m "temp: add Q2 validation logging

Validates system prompt injection point.
See: docs/VALIDATION_LOG.md Q2
Will be reverted after validation."

# Deploy
bash .\deploy.sh

# Restart HA, test, capture logs

# Remove logging, document results
# Edit files to remove logging
# Update docs/VALIDATION_LOG.md

git add custom_components\personality_llm\*.py
git add docs\VALIDATION_LOG.md
git commit -m "docs: Q2 validation complete (PASS)

System prompt read once from config, passed to chat_log.
Single injection point confirmed.
See: docs/VALIDATION_LOG.md Q2"

# Push
git push origin feature/phase1-speaker-awareness
```

***

## Safety Checks Before Each Validation

**Before deploying validation code:**

```powershell
# Check syntax
python -m py_compile custom_components\personality_llm\conversation.py
python -m py_compile custom_components\personality_llm\entity.py

# Verify you're on the right branch
git branch
# Should show: * feature/phase1-speaker-awareness

# Verify files have your changes
grep "VALIDATE-Q" custom_components\personality_llm\conversation.py
```

***

## Common Issues & Fixes

### "Logs don't appear for QX"

**Check:**

1.  Did you restart HA after deploy?
2.  Are file timestamps on HA recent?
    ```bash
    ssh root@192.168.2.30 "ls -lh /config/custom_components/personality_llm/conversation.py"
    ```
3.  Is the logging code actually in the file on HA?
    ```bash
    ssh root@192.168.2.30 "grep VALIDATE-QX /config/custom_components/personality_llm/conversation.py"
    ```

### "Import error on restart"

**Cause:** Syntax error in logging code.

**Fix:**

```powershell
python -m py_compile custom_components\personality_llm\conversation.py
# Fix any errors shown
# Redeploy
```

### "Q4 mutation raises exception"

**This is valuable data** — document it as FAIL, note the exception type, and we'll design around it in implementation.

***

## After All Validations Complete

**You should have:**

```powershell
git log --oneline -6
```

Output:

    abc1234 docs: Q5 validation complete (all Q1-Q5 PASS)
    def5678 docs: Q4 validation complete (PASS)
    ...

**All validation logging removed:**

```powershell
grep -r "VALIDATE-Q" custom_components\personality_llm\
# Should return: nothing
```

**All results documented:**

```powershell
code docs\VALIDATION_LOG.md
# Should show Q1-Q5 all marked PASS with outcomes
```

**Ready for implementation:**

```markdown
## Summary in VALIDATION_LOG.md

**Validated:** 5/5  
**Failed:** 0/5  
**Pending:** 0/5  

**Ready for implementation:** ✅ Yes
```

***

## What Happens Next

After Q1-Q5 all PASS, you will:

1.  Update `docs/PHASE_1_PLAN.md` with validated injection points
2.  Create implementation branches:
    *   `feature/phase1-speaker-cache`
    *   `feature/phase1-user-config`
    *   `feature/phase1-webhook`
    *   `feature/phase1-conversation-injection`
3.  Implement features one by one
4.  Merge each to `feature/phase1-speaker-awareness`
5.  Final integration test
6.  Merge Phase 1 to `main`

But **do not start implementation until all validations are complete and documented.**

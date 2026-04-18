# Phase 1 Implementation Plan – Speaker Awareness

**Goal:** Integrate speaker identification from external VoicePipeline into conversation agent flow.

**Status:** 🟡 Validation phase  
**Started:** [DATE]

---

## Phase Overview

Phase 1 adds speaker awareness **without breaking upstream compatibility**:
- Accept speaker metadata via webhook
- Route to per-speaker personality prompts
- Route to per-speaker models
- Route to per-speaker TTS voices

**Non-goals for Phase 1:**
- Conversation history (Phase 2+)
- Streaming responses (Phase 2+)
- Advanced TTS features (Phase 4)

---

## Current Status: Validation

Before implementing, we must **validate Claude's injection-point analysis**.

See:
- `docs/CLAUDE_ANALYSIS.md` (hypothesis)
- `docs/VALIDATION_LOG.md` (outcomes)

---

## Validation Tasks (In Progress)

- [ ] Q1: Validate speaker identity source
- [ ] Q2: Validate system prompt injection point
- [ ] Q3: Validate model selection flow
- [ ] Q4: Validate TTS voice override hook
- [ ] Q5: Confirm minimal-change pattern

**Blocked on:** Validation completion

---

## Implementation Tasks (Not Started)

**Task 1.1: Speaker Cache Module**
- File: `custom_components/personality_llm/speaker_cache.py`
- Purpose: Store speaker metadata from webhook with TTL
- Depends: Validation complete

**Task 1.2: User Config Manager**
- File: `custom_components/personality_llm/user_config.py`
- Purpose: Per-speaker config storage (personality, LLM, TTS)
- Depends: Task 1.1 complete

**Task 1.3: Webhook Handler**
- File: `custom_components/personality_llm/__init__.py` (modify)
- Purpose: Accept speaker metadata from VoicePipeline
- Depends: Task 1.1 complete

**Task 1.4: Conversation Injection**
- File: `custom_components/personality_llm/conversation.py` (modify)
- Purpose: Inject speaker-specific prompt/model
- Depends: Validation Q1, Q2, Q3 PASS

**Task 1.5: Multi-Speaker Config Flow**
- File: `custom_components/personality_llm/config_flow.py` (replace)
- Purpose: UI for managing speakers
- Depends: Task 1.2 complete

---

## Exit Criteria

Phase 1 is complete when:
- [ ] All validation tasks PASS
- [ ] All implementation tasks complete
- [ ] Multi-speaker test passes (3 speakers, different prompts/models)
- [ ] No regression in baseline (conversation, tool calling)
- [ ] VoicePipeline integration test passes

---

## Next Action

Run validation plan from `docs/VALIDATION_LOG.md`.
EOF
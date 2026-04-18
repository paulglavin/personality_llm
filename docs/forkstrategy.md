
# Development & Upstream Contribution Strategy  This document defines the **working strategy** for developing speaker-aware functionality on top of `hass_local_openai_llm` while **maximising upstream alignment** and **minimising long‑term maintenance risk**.

It is written for internal use and reflects a pragmatic, delivery‑focused approach rather than an aspirational or community‑positioning statement.

---

## Strategic Position

### Primary Goal
- Deliver **speaker-aware, per-personality voice interaction** without blocking progress on upstream acceptance or review cycles.

### Secondary Goal
- Contribute **select, high‑value improvements** upstream where they are broadly useful and low risk.

### Non-Goal
- Forcing large architectural changes (multi-speaker, webhook-driven identity, VoicePipeline integration) into upstream if they are misaligned with the upstream project’s scope.

---

## Core Decision

We will use a **hybrid fork-first strategy**:

- ✅ **Fork-first** for all speaker-aware and VoicePipeline-driven work
- ✅ **Upstream selectively** for small, universally useful improvements
- ❌ **Do not attempt to upstream** core speaker-awareness, per-user config, or webhook-based identity

This approach maximises delivery speed while preserving upstream compatibility and goodwill.

---

## Why This Strategy Is Necessary

### Upstream Architectural Reality

`hass_local_openai_llm` is architected around:
- A **single-user mental model**
- **Global configuration** (prompt, model, endpoint)
- Stateless conversation processing

Speaker-aware functionality requires:
- External identity ingestion (webhooks / VoicePipeline)
- Per-speaker configuration and storage
- Stateful resolution of speaker context per request

These are **fundamental shifts**, not incremental enhancements.

Attempting to upstream them would:
- Dramatically expand project scope
- Increase maintainer burden
- Introduce features most users do not need
- Likely result in rejected or stalled PRs

---

## What We Will Upstream

We will upstream **only changes that meet all of the following criteria**:
- Clearly beneficial to the majority of users
- Opt-in or non-breaking
- Small, reviewable, and easy to reason about
- Do not introduce external dependencies or new architectural concepts

### Likely Upstream Candidates
- Streaming response support (latency reduction)
- Prompt templating or variable expansion
- Bug fixes discovered during local-model testing
- Performance optimisations
- Error handling improvements for tool execution

These changes will be:
- Isolated in small PRs
- Submitted independently of speaker-aware work
- Treated as optional contributions, not blockers

---

## What Will Remain Fork-Only

The following will **not** be proposed upstream:

- Speaker identification via webhook
- Speaker cache / identity resolution
- Per-speaker personality configuration
- Per-speaker model or TTS selection
- Multi-user configuration flows
- VoicePipeline integration

These features are:
- Opinionated
- Hardware- and setup-dependent
- Outside upstream’s intended scope

They belong in a dedicated integration.

---

## Development Workflow

### Branch Model

- `main`  
  Stable fork with all features

- `upstream-sync`  
  Temporary branch for testing upstream merges

- `feature/*`  
  Feature-specific development branches

### Contribution Flow

1. Develop features freely in the fork
2. Identify any **universally useful improvement**
3. Extract that improvement into a clean, isolated branch
4. Remove fork-specific assumptions
5. Submit upstream PR
6. If accepted → merge back into fork
7. If rejected → retain fork-only

Upstream PRs are **opportunistic**, never blocking.

---

## Upstream Sync Policy

- Check upstream **monthly** or when HA releases introduce breaking changes
- Merge upstream changes into `upstream-sync
*(Internal – Pragmatic)*

## Purpose
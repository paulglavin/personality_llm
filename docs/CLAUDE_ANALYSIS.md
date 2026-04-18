
# Claude Injection-Point Analysis (Archive)

**Generated:** [DATE]  
**Status:** Hypothesis — requires validation before implementation  
**Purpose:** Preserve original analysis as reference; see VALIDATION_LOG.md for outcomes

---

## Q1 – Speaker Identity Source

**Hypothesis:**
- `_async_handle_message` receives `ConversationInput`
- Available fields: `user_input.device_id`, `user_input.context.user_id`
- Injection point: after `options = self.subentry.data` (conversation.py:~57)

**Proposed code:**
```python
speaker_id = user_input.device_id or user_input.context.user_id
speaker_profile = await self._get_speaker_profile(speaker_id)

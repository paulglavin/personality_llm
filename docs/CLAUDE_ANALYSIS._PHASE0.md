
# Claude Injection-Point Analysis (Archive)

**Generated:** YYYY-MM-DD
**Prompt:** "Identify injection points for speaker awareness in conversation.py"

## Raw Output

Speaker Awareness Injection Points
Q1 — Where to get speaker from cache in async_process()
_async_handle_message is called by HA's ConversationEntity.async_process(). The user_input argument carries all speaker identity data:


# conversation.py:51-81
async def _async_handle_message(
    self,
    user_input: conversation.ConversationInput,  # ← speaker identity lives here
    chat_log: conversation.ChatLog,
) -> conversation.ConversationResult:
ConversationInput fields relevant to speaker:

user_input.device_id — HA device making the request (e.g. voice satellite entity)
user_input.agent_id — which conversation agent was called
user_input.conversation_id — session/conversation ID (already used line 576)
user_input.context — HA context, contains user_id of the authenticated user
Injection point: conversation.py:57 — after options = self.subentry.data, add:


speaker_id = user_input.device_id or user_input.context.user_id
speaker_profile = await self._get_speaker_profile(speaker_id)  # your cache lookup
Q2 — Where the system prompt is set (per-speaker replacement)
conversation.py:58:


system_prompt = options.get(CONF_PROMPT)  # ← replace with per-speaker lookup
Then passed to HA's chat_log.async_provide_llm_data() at line 68-73. This is the only place the system prompt enters — clean single injection point.

Per-speaker replacement:


system_prompt = speaker_profile.prompt if speaker_profile else options.get(CONF_PROMPT)
Q3 — Where the model is selected (per-speaker override)
entity.py:243 — set in __init__:


self.model = subentry.data[CONF_MODEL]  # ← instance-level, set at load time
entity.py:438-439 — used in model_args:


model_args = {
    "model": self.model,  # ← override here per-call
Since _async_handle_chat_log already receives user_input, you can pass speaker_model as a parameter:


model_args = {
    "model": speaker_model or self.model,
This requires adding speaker_model: str | None = None to _async_handle_chat_log's signature (entity.py:424) and passing it from conversation.py:77.

Q4 — Where the response is built (TTS voice override)
ConversationResult is assembled at conversation.py:81:


return conversation.async_get_result_from_chat_log(user_input, chat_log)
HA's async_get_result_from_chat_log populates ConversationResult. The TTS voice is set via user_input.tts_options — you mutate this before calling async_get_result_from_chat_log:


# Inject per-speaker TTS voice before building result
if speaker_profile and speaker_profile.tts_voice:
    user_input.tts_options = {**(user_input.tts_options or {}), "voice": speaker_profile.tts_voice}

return conversation.async_get_result_from_chat_log(user_input, chat_log)
Alternatively, build the ConversationResult manually and set result.response.speech["plain"]["speech"] + result.response.voice directly.

Q5 — Cleanest integration pattern
Minimal-change approach: two files only, no new abstractions until the cache layer is built.


conversation.py  ← speaker lookup + profile resolution (3 lines added)
entity.py        ← accept optional speaker_model + speaker_prompt overrides
Concretely:

conversation.py:57-59 — resolve speaker profile from user_input.device_id:


options = self.subentry.data
system_prompt = options.get(CONF_PROMPT)
# ↓ ADD: override with per-speaker profile
speaker_profile = await async_get_speaker_profile(self.hass, user_input.device_id)
if speaker_profile:
    system_prompt = speaker_profile.prompt or system_prompt
conversation.py:77-79 — pass speaker overrides:


await self._async_handle_chat_log(
    chat_log,
    user_input=user_input,
    parallel_tool_calls=parallel_tool_calls,
    speaker_model=speaker_profile.model if speaker_profile else None,
)
entity.py:438 — consume speaker_model:


"model": speaker_model or self.model,
conversation.py:79-81 — TTS voice after the await.

The speaker profile cache/storage (async_get_speaker_profile) is the only new module needed, and it's cleanly isolated from all upstream logic.

## Status

- ✅ Validated and acted upon: See PHASE_1_PLAN.md
- ❌ Invalidated: [list any findings that were wrong]
- 🔴 Deferred: See FUTURE_IMPROVEMENTS.md

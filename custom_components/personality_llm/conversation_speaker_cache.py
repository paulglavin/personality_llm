"""Conversation-to-speaker mapping cache."""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Conversation cache TTL (30 minutes)
CONVERSATION_TTL_SECONDS = 1800


class ConversationSpeakerCache:
    """
    Maps conversation_id to speaker_id.
    
    Preserves speaker identity across multi-turn conversations.
    """
    
    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize conversation cache."""
        self._hass = hass
        # Storage: conversation_id → speaker data
        self._cache: dict[str, dict] = {}
    
    async def async_put(
        self,
        conversation_id: str,
        speaker_id: str,
    ) -> None:
        """
        Store conversation-to-speaker mapping.
        
        Args:
            conversation_id: Conversation identifier
            speaker_id: Speaker identifier
        """
        if not conversation_id or not speaker_id:
            return
        
        now = time.time()
        
        if conversation_id in self._cache:
            # Update existing conversation
            self._cache[conversation_id]["last_turn"] = now
            
            # Detect speaker change
            if self._cache[conversation_id]["speaker_id"] != speaker_id:
                old_speaker = self._cache[conversation_id]["speaker_id"]
                _LOGGER.info(
                    "Speaker changed in conversation %s: %s → %s",
                    conversation_id,
                    old_speaker,
                    speaker_id,
                )
                self._cache[conversation_id]["speaker_id"] = speaker_id
        else:
            # New conversation
            self._cache[conversation_id] = {
                "speaker_id": speaker_id,
                "timestamp": now,
                "last_turn": now,
            }
            _LOGGER.debug("Started conversation %s with speaker %s", conversation_id, speaker_id)
    
    async def async_get(self, conversation_id: str) -> str | None:
        """
        Get speaker for conversation.
        
        Args:
            conversation_id: Conversation identifier
            
        Returns:
            speaker_id or None if conversation not found or expired
        """
        if not conversation_id:
            return None
        
        # Cleanup expired entries
        await self.async_cleanup()
        
        entry = self._cache.get(conversation_id)
        
        if entry:
            _LOGGER.debug(
                "Retrieved speaker for conversation %s: %s",
                conversation_id,
                entry["speaker_id"],
            )
            return entry["speaker_id"]
        
        return None
    
    async def async_cleanup(self) -> int:
        """
        Remove expired conversations.
        
        Returns:
            Number of entries removed
        """
        now = time.time()
        cutoff = now - CONVERSATION_TTL_SECONDS
        
        expired = [
            conv_id
            for conv_id, entry in self._cache.items()
            if entry["last_turn"] < cutoff
        ]
        
        for conv_id in expired:
            del self._cache[conv_id]
        
        if expired:
            _LOGGER.debug("Cleaned up %d expired conversations", len(expired))
        
        return len(expired)
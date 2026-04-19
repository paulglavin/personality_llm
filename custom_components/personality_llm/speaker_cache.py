"""Speaker cache for VoicePipeline metadata.

Stores speaker identification metadata temporarily (2-5 seconds) between
webhook arrival and conversation agent invocation.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Default TTL for cache entries (seconds)
DEFAULT_TTL_SECONDS = 2.0


@dataclass
class _SpeakerCacheEntry:
    """
    Internal storage for cached speaker metadata.
    
    Private to this module - external callers receive dicts, not instances.
    """
    speaker_id: str
    confidence: float
    timestamp: float
    interaction_id: str | None = None


class SpeakerCache:
    """
    Short-lived cache for speaker metadata from VoicePipeline.
    
    Thread-safe for HA's async event loop (single-threaded).
    Entries auto-expire after TTL.
    """
    
    def __init__(self, hass: HomeAssistant) -> None:
        """
        Initialize speaker cache.
        
        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
        # Storage: timestamp → entry (ordered by time for easy recent lookup)
        self._cache: dict[float, _SpeakerCacheEntry] = {}
    
    async def async_put(
        self,
        speaker_id: str,
        confidence: float,
        interaction_id: str | None = None,
    ) -> None:
        """
        Store speaker metadata in cache.
        
        Args:
            speaker_id: Speaker identifier from VoicePipeline
            confidence: Recognition confidence (0.0-1.0)
            interaction_id: Optional correlation ID for feedback loop
        """
        # Validate speaker_id
        if not speaker_id or not isinstance(speaker_id, str):
            _LOGGER.warning("Invalid speaker_id: %s (type: %s)", speaker_id, type(speaker_id))
            return
        
        # Validate and clamp confidence
        if not isinstance(confidence, (int, float)):
            _LOGGER.warning("Invalid confidence type: %s", type(confidence))
            confidence = 0.0
        elif not (0.0 <= confidence <= 1.0):
            _LOGGER.warning("Confidence %s out of range [0.0, 1.0], clamping", confidence)
            confidence = max(0.0, min(1.0, confidence))
        
        # Create cache entry
        entry = _SpeakerCacheEntry(
            speaker_id=speaker_id,
            confidence=float(confidence),
            timestamp=time.time(),
            interaction_id=interaction_id,
        )
        
        # Store using timestamp as key (allows sorting by time)
        self._cache[entry.timestamp] = entry
        
        _LOGGER.debug(
            "Cached speaker: %s (confidence=%.2f, entries=%d)",
            speaker_id,
            confidence,
            len(self._cache),
        )
    
    async def async_get_recent(
        self,
        max_age_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> dict | None:
        """
        Get most recent speaker within TTL window.
        
        Automatically cleans up expired entries (lazy cleanup).
        
        Args:
            max_age_seconds: Maximum age of cached entry to return
        
        Returns:
            Dictionary with keys:
                - speaker_id: str
                - confidence: float
                - timestamp: float
                - interaction_id: str | None
            Or None if no recent entry exists
        """
        now = time.time()
        cutoff = now - max_age_seconds
        
        # Lazy cleanup: remove expired entries
        expired_count = 0
        self._cache = {
            ts: entry
            for ts, entry in self._cache.items()
            if ts >= cutoff
        }
        
        if expired_count > 0:
            _LOGGER.debug("Cleaned up %d expired cache entries", expired_count)
        
        # No entries left after cleanup
        if not self._cache:
            _LOGGER.debug("No recent speaker in cache (empty)")
            return None
        
        # Find most recent entry (max timestamp)
        latest_timestamp = max(self._cache.keys())
        latest_entry = self._cache[latest_timestamp]
        
        # Convert dataclass to plain dict (public API contract)
        result = {
            "speaker_id": latest_entry.speaker_id,
            "confidence": latest_entry.confidence,
            "timestamp": latest_entry.timestamp,
            "interaction_id": latest_entry.interaction_id,
        }
        
        _LOGGER.debug(
            "Retrieved recent speaker: %s (age=%.2fs)",
            latest_entry.speaker_id,
            now - latest_entry.timestamp,
        )
        
        return result
    
    async def async_cleanup(self, max_age_seconds: float = DEFAULT_TTL_SECONDS) -> int:
        """
        Explicitly remove expired entries.
        
        Normally cleanup happens lazily in async_get_recent(), but this
        can be called explicitly (e.g., via periodic task).
        
        Args:
            max_age_seconds: Age threshold for removal
        
        Returns:
            Number of entries removed
        """
        now = time.time()
        cutoff = now - max_age_seconds
        
        # Count entries to remove
        expired_timestamps = [ts for ts in self._cache if ts < cutoff]
        expired_count = len(expired_timestamps)
        
        # Remove expired entries
        for ts in expired_timestamps:
            del self._cache[ts]
        
        if expired_count > 0:
            _LOGGER.debug(
                "Cleanup removed %d expired entries (remaining=%d)",
                expired_count,
                len(self._cache),
            )
        
        return expired_count
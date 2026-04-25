"""User configuration manager for per-speaker settings."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    STORAGE_VERSION,
    STORAGE_KEY,
    DEFAULT_USER_CONFIG,
)

_LOGGER = logging.getLogger(__name__)


class UserConfigManager:
    """
    Manage per-speaker configuration storage.
    
    Persists to .storage/personality_llm_users.
    """
    
    def __init__(self, hass: HomeAssistant) -> None:
        """
        Initialize config manager.
        
        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._config: dict[str, Any] | None = None
    
    async def async_load(self) -> None:
        """Load configs from storage."""
        try:
            data = await self._store.async_load()
            
            if data is None:
                _LOGGER.info("No user config found, creating defaults")
                data = self._get_default_storage()
            
            # Validate schema
            if not isinstance(data, dict) or "version" not in data or "users" not in data:
                _LOGGER.warning("Invalid config schema, resetting to defaults")
                data = self._get_default_storage()
            
            # Ensure default user exists
            if "default" not in data["users"]:
                _LOGGER.warning("Default user missing, adding it")
                data["users"]["default"] = DEFAULT_USER_CONFIG.copy()
            
            self._config = data
            _LOGGER.info("Loaded config for %d users", len(data["users"]))
            
        except Exception as e:
            _LOGGER.error("Failed to load user config: %s", e)
            self._config = self._get_default_storage()
    
    async def async_save(self) -> None:
        """Save configs to storage."""
        if self._config is None:
            _LOGGER.warning("Cannot save: config not loaded")
            return
        
        try:
            await self._store.async_save(self._config)
            _LOGGER.debug("Saved config for %d users", len(self._config["users"]))
        except Exception as e:
            _LOGGER.error("Failed to save user config: %s", e)
    
    def get_user(self, speaker_id: str) -> dict[str, Any]:
        """
        Get config for speaker, fallback to 'default'.
        
        Args:
            speaker_id: Speaker identifier
            
        Returns:
            User config dict (never None)
        """
        if self._config is None:
            _LOGGER.warning("Config not loaded, returning default")
            return DEFAULT_USER_CONFIG.copy()
        
        if speaker_id not in self._config["users"]:
            _LOGGER.debug("Speaker %s not found, using default", speaker_id)
            speaker_id = "default"
        
        return self._config["users"][speaker_id]
    
    async def async_add_user(self, speaker_id: str, config: dict[str, Any]) -> None:
        """
        Add or update user config.
        
        Args:
            speaker_id: Speaker identifier
            config: Full user config dict
        """
        if self._config is None:
            _LOGGER.error("Cannot add user: config not loaded")
            return
        
        # Validate speaker_id
        if not speaker_id or not isinstance(speaker_id, str):
            raise ValueError(f"Invalid speaker_id: {speaker_id}")
        
        # Merge with defaults to fill any gaps
        full_config = self._merge_with_defaults(config)
        
        self._config["users"][speaker_id] = full_config
        await self.async_save()
        
        _LOGGER.info("Added/updated user: %s", speaker_id)
    
    async def async_update_default_user(self, config: dict[str, Any]) -> None:
        """
        Update default user config (called by config flow).
        
        Args:
            config: Updated default user config (full or partial)
        """
        if self._config is None:
            _LOGGER.error("Cannot update default: config not loaded")
            return
        
        # Merge with existing default to preserve any missing fields
        merged = self._merge_with_defaults(config)
        
        self._config["users"]["default"] = merged
        await self.async_save()
        
        _LOGGER.info("Updated default user config via UI")
    
    async def async_delete_user(self, speaker_id: str) -> None:
        """
        Delete user config.
        
        Args:
            speaker_id: Speaker identifier
            
        Raises:
            ValueError: If trying to delete 'default' user
        """
        if speaker_id == "default":
            raise ValueError("Cannot delete default user")
        
        if self._config is None:
            _LOGGER.error("Cannot delete user: config not loaded")
            return
        
        if speaker_id in self._config["users"]:
            del self._config["users"][speaker_id]
            await self.async_save()
            _LOGGER.info("Deleted user: %s", speaker_id)
        else:
            _LOGGER.warning("Cannot delete: user %s not found", speaker_id)
    
    def list_users(self) -> list[str]:
        """Return list of all speaker_ids."""
        if self._config is None:
            return ["default"]
        
        return list(self._config["users"].keys())
    
    def _get_default_storage(self) -> dict[str, Any]:
        """Get default storage structure."""
        return {
            "version": STORAGE_VERSION,
            "users": {
                "default": DEFAULT_USER_CONFIG.copy()
            }
        }
    
    def _merge_with_defaults(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        Merge user config with defaults to fill gaps.
        
        Args:
            config: Partial or full user config
            
        Returns:
            Complete config with all required fields
        """
        merged = DEFAULT_USER_CONFIG.copy()
        
        # Deep merge (one level only for simplicity)
        for key in merged:
            if key in config:
                if isinstance(merged[key], dict) and isinstance(config[key], dict):
                    merged[key] = {**merged[key], **config[key]}
                else:
                    merged[key] = config[key]
        
        return merged
"""Smart-discovery LLM tool surface for personality_llm.

Registers a custom llm.API that exposes three tools:
    discover_entities   – filtered entity lookup (token-cheap)
    get_entity_details  – full state for specific IDs
    perform_action      – call a Home Assistant service

Selecting this API in a conversation subentry's "LLM Hass API" multiselect
replaces the per-turn entity dump that LLM_API_ASSIST injects, dropping
system-prompt size from ~8k tokens (90 entities) to ~1.5–2k.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from .const import CONF_MUSIC_SCRIPT, DOMAIN, SMART_DISCOVERY_API_ID

_LOGGER = logging.getLogger(__name__)


SMART_API_PROMPT = (
    "You control a Home Assistant smart home through three tools.\n"
    "\n"
    "NEVER guess entity IDs. For ANY device-related request you MUST:\n"
    "  1. Call discover_entities to find matching entities.\n"
    "  2. Call perform_action (to control) or get_entity_details (to check state) "
    "using IDs from step 1.\n"
    "Discovering an entity does not control it — you must call perform_action.\n"
    "\n"
    "Use friendly names in user-facing replies, never raw entity_ids.\n"
    "When discovering, prefer specific filters (domain, area, device_class) over "
    "broad name searches. Default limit is 20; raise it only when needed.\n"
)


class _SmartTool(llm.Tool):
    """Base class — pulls SmartDiscovery off hass.data."""

    def _smart(self, hass: HomeAssistant):
        sd = hass.data.get(DOMAIN, {}).get("smart_discovery")
        if sd is None:
            raise RuntimeError(
                "SmartDiscovery not initialised; ensure personality_llm "
                "config entry is loaded."
            )
        return sd


class DiscoverEntitiesTool(_SmartTool):
    """Filtered entity discovery."""

    name = "discover_entities"
    description = (
        "Find Home Assistant entities by area/floor/label/domain/device_class/"
        "state/name. Always call this BEFORE acting on devices — never guess "
        "entity IDs. Returns up to `limit` matches with friendly names, area, "
        "and key attributes only."
    )
    parameters = vol.Schema({
        vol.Optional("domain"): str,
        vol.Optional("area"): str,
        vol.Optional("floor"): str,
        vol.Optional("label"): str,
        vol.Optional("state"): str,
        vol.Optional("name_contains"): str,
        vol.Optional("device_class"): vol.Any(str, [str]),
        vol.Optional("name_pattern"): str,
        vol.Optional("limit", default=20): vol.All(int, vol.Range(min=1, max=50)),
    })

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        results = await self._smart(hass).discover_entities(
            **tool_input.tool_args,
        )
        return {"count": len(results), "entities": results}


class GetEntityDetailsTool(_SmartTool):
    """Full state for specific entity IDs."""

    name = "get_entity_details"
    description = (
        "Get full state, attributes, area, and labels for specific entity IDs. "
        "Use this AFTER discover_entities to check a device's current state."
    )
    parameters = vol.Schema({
        vol.Required("entity_ids"): vol.All([str], vol.Length(min=1, max=20)),
    })

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        return await self._smart(hass).get_entity_details(
            tool_input.tool_args["entity_ids"],
        )


class PerformActionTool(llm.Tool):
    """Call a Home Assistant service against discovered entities."""

    name = "perform_action"
    description = (
        "Control devices by calling a Home Assistant service. Use after "
        "discover_entities — pass the discovered entity_id in `target`. "
        "Examples: turn on a light "
        "(domain='light', action='turn_on', target={'entity_id': 'light.kitchen'}); "
        "set thermostat (domain='climate', action='set_temperature', "
        "target={'entity_id': 'climate.living_room'}, data={'temperature': 22})."
    )
    parameters = vol.Schema({
        vol.Required("domain"): str,
        vol.Required("action"): str,
        vol.Required("target"): vol.Schema(
            {
                vol.Optional("entity_id"): vol.Any(str, [str]),
                vol.Optional("area_id"): vol.Any(str, [str]),
                vol.Optional("device_id"): vol.Any(str, [str]),
            },
            extra=vol.PREVENT_EXTRA,
        ),
        vol.Optional("data"): dict,
    })

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        args = tool_input.tool_args
        domain = args["domain"]
        action = args["action"]
        target = args["target"]
        data = args.get("data") or {}

        if not hass.services.has_service(domain, action):
            return {
                "success": False,
                "error": f"service {domain}.{action} not registered",
            }

        try:
            await hass.services.async_call(
                domain,
                action,
                service_data=data,
                target=target,
                blocking=True,
                context=llm_context.context,
            )
        except Exception as err:  # noqa: BLE001 — surface to LLM
            _LOGGER.warning("perform_action failed: %s.%s -> %s", domain, action, err)
            return {"success": False, "error": str(err)}

        return {"success": True, "domain": domain, "action": action, "target": target}


class PlayMusicTool(llm.Tool):
    """Call the Music Assistant voice script with typed parameters."""

    name = "play_music"
    description = (
        "Play music via Music Assistant. Use for any music playback request. "
        "Extract all details from the user's request and call immediately — "
        "do NOT ask for clarification unless the request is genuinely ambiguous."
    )
    parameters = vol.Schema({
        vol.Required("media_type"): vol.In(["track", "album", "artist", "playlist", "radio"]),
        vol.Required("media_id"): str,
        vol.Required("media_description"): str,
        vol.Optional("artist", default=""): str,
        vol.Optional("album", default=""): str,
        vol.Optional("shuffle", default=False): bool,
        vol.Optional("area"): str,
        vol.Optional("media_player"): str,
    })

    def __init__(self, script_entity_id: str) -> None:
        self._script_entity_id = script_entity_id

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        args = tool_input.tool_args
        variables: dict[str, Any] = {
            "media_type": args["media_type"],
            "media_id": args["media_id"],
            "artist": args.get("artist", ""),
            "album": args.get("album", ""),
            "media_description": args["media_description"],
            "shuffle": args.get("shuffle", False),
        }
        if "area" in args:
            variables["area"] = args["area"]
        if "media_player" in args:
            variables["media_player"] = args["media_player"]

        try:
            await hass.services.async_call(
                "script",
                "turn_on",
                {"entity_id": self._script_entity_id, "variables": variables},
                blocking=False,
                context=llm_context.context,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("play_music failed: %s", err)
            return {"success": False, "error": str(err)}

        return {"success": True, "playing": args["media_description"]}


class PersonalityLLMSmartAPI(llm.API):
    """Custom LLM API exposing smart discovery + action tools."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass=hass,
            id=SMART_DISCOVERY_API_ID,
            name="Personality LLM Smart Discovery",
        )

    def _get_music_script(self, llm_context: llm.LLMContext) -> str | None:
        """Return the music script entity_id configured for the requesting subentry."""
        if not llm_context.assistant:
            return None
        from homeassistant.helpers import entity_registry as er
        registry = er.async_get(self.hass)
        entity_entry = registry.async_get(llm_context.assistant)
        if entity_entry is None or entity_entry.config_subentry_id is None:
            return None
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            subentry = entry.subentries.get(entity_entry.config_subentry_id)
            if subentry is not None:
                return subentry.data.get(CONF_MUSIC_SCRIPT) or None
        return None

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext,
    ) -> llm.APIInstance:
        tools: list[llm.Tool] = [
            DiscoverEntitiesTool(),
            GetEntityDetailsTool(),
            PerformActionTool(),
        ]
        api_prompt = SMART_API_PROMPT
        music_script = self._get_music_script(llm_context)
        if music_script:
            tools.append(PlayMusicTool(music_script))
            api_prompt += (
                "\n\nFor music requests, use the play_music tool directly — "
                "no entity discovery needed."
            )
        return llm.APIInstance(
            api=self,
            api_prompt=api_prompt,
            llm_context=llm_context,
            tools=tools,
        )

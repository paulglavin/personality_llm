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
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    llm,
)

try:
    from homeassistant.helpers import floor_registry as fr
except ImportError:  # pragma: no cover
    fr = None

from .const import CONF_MUSIC_SCRIPT, DOMAIN, SMART_DISCOVERY_API_ID

_LOGGER = logging.getLogger(__name__)


SMART_API_PROMPT = (
    "You control a Home Assistant smart home through three tools.\n"
    "\n"
    "For room-specific or named-device requests:\n"
    "  1. Call discover_entities to find matching entities.\n"
    "  2. Call perform_action (to control) or get_entity_details (to check state) "
    "using IDs from step 1.\n"
    "Discovering an entity does not control it — you must call perform_action.\n"
    "\n"
    "For floor-wide commands (e.g. 'turn on all the lights on a floor'), skip\n"
    "discover_entities entirely and call perform_action directly with the floor\n"
    "parameter — no entity IDs needed.\n"
    "\n"
    "IMPORTANT — area vs floor:\n"
    "  area = a room name (e.g. 'Kitchen', 'Living Room', 'Office')\n"
    "  floor = one of the floor names listed below\n"
    "Never pass a floor name as the area parameter — they are different fields.\n"
    "\n"
    "perform_action target accepts entity_id, area (room name), or floor (floor name).\n"
    "\n"
    "Use friendly names in user-facing replies, never raw entity_ids.\n"
    "When discovering, prefer specific filters (domain, area, device_class) over "
    "broad name searches. Default limit is 20; raise it only when needed.\n"
)


# ---------------------------------------------------------------------------
# Location resolution helpers
# ---------------------------------------------------------------------------

def _area_name_to_id(area_reg: Any, name: str) -> str | None:
    """Resolve an area name (or alias) to its HA area_id."""
    target = name.casefold()
    for entry in area_reg.async_list_areas():
        if entry.name.casefold() == target:
            return entry.id
        for alias in getattr(entry, "aliases", set()) or set():
            if alias.casefold() == target:
                return entry.id
    return None


def _floor_name_to_id(floor_reg: Any, name: str) -> str | None:
    """Resolve a floor name (or alias) to its floor_id."""
    target = name.casefold()
    for entry in floor_reg.async_list_floors():
        if entry.name.casefold() == target:
            return entry.floor_id
        for alias in getattr(entry, "aliases", set()) or set():
            if alias.casefold() == target:
                return entry.floor_id
    return None


def _resolve_target(hass: HomeAssistant, target: dict) -> dict:
    """Expand area/floor names to area_ids; return a clean HA-native target dict.

    HA services understand entity_id, area_id, and device_id — not floor_id or
    area names. This expands:
      area  (name)  → area_id
      floor (name)  → all area_ids on that floor
    and merges with any explicit area_id already in the target.
    """
    area_reg = ar.async_get(hass)

    area_ids: list[str] = []

    # Carry through any explicit area_ids already in the target
    existing = target.get("area_id")
    if existing:
        area_ids.extend([existing] if isinstance(existing, str) else list(existing))

    # Resolve area name(s) → area_id
    area_name = target.get("area")
    if area_name:
        names = [area_name] if isinstance(area_name, str) else list(area_name)
        for name in names:
            aid = _area_name_to_id(area_reg, name)
            if aid:
                area_ids.append(aid)
            else:
                _LOGGER.warning("perform_action: could not resolve area name %r", name)

    # Resolve floor name → every area_id on that floor
    floor_name = target.get("floor")
    if floor_name and fr is not None:
        floor_reg = fr.async_get(hass)
        fid = _floor_name_to_id(floor_reg, floor_name)
        if fid:
            for a in area_reg.async_list_areas():
                if getattr(a, "floor_id", None) == fid:
                    area_ids.append(a.id)
        else:
            _LOGGER.warning("perform_action: could not resolve floor name %r", floor_name)

    # Build the clean target dict HA services expect
    resolved: dict[str, Any] = {}
    entity_id = target.get("entity_id")
    if entity_id:
        resolved["entity_id"] = entity_id
    device_id = target.get("device_id")
    if device_id:
        resolved["device_id"] = device_id
    if area_ids:
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique = [x for x in area_ids if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]
        resolved["area_id"] = unique if len(unique) > 1 else unique[0]

    return resolved


def _get_device_location(hass: HomeAssistant, device_id: str | None) -> dict[str, str | None]:
    """Return the area name and floor name for a device, or None for each if unknown."""
    if not device_id:
        return {"area": None, "floor": None}
    device_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)
    device = device_reg.async_get(device_id)
    if not device or not device.area_id:
        return {"area": None, "floor": None}
    area = area_reg.async_get_area(device.area_id)
    if not area:
        return {"area": None, "floor": None}
    floor_name: str | None = None
    if fr is not None and area.floor_id:
        floor_reg = fr.async_get(hass)
        floor_entry = floor_reg.async_get_floor(area.floor_id)
        if floor_entry:
            floor_name = floor_entry.name
    return {"area": area.name, "floor": floor_name}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

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
        "floor, and key attributes only."
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
        "discover_entities. Target accepts entity_id (from discovery), "
        "area (area name, e.g. 'Kitchen'), or floor (floor name, e.g. 'Ground Floor') "
        "— area and floor names are resolved automatically. "
        "Examples: turn on kitchen lights "
        "(domain='light', action='turn_on', target={'area': 'Kitchen'}); "
        "turn off all lights on a floor "
        "(domain='light', action='turn_off', target={'floor': 'Ground Floor'}); "
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
                vol.Optional("area"): vol.Any(str, [str]),
                vol.Optional("floor"): str,
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
        data = args.get("data") or {}

        target = _resolve_target(hass, args["target"])

        if not target:
            return {"success": False, "error": "target resolved to empty — no entities, area, or floor matched"}

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
        vol.Optional("area"): vol.Any(str, [str]),
        vol.Optional("media_player"): vol.Any(str, [str]),
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
            area_reg = ar.async_get(hass)
            raw = args["area"]
            names = [raw] if isinstance(raw, str) else list(raw)
            resolved = [_area_name_to_id(area_reg, n) or n for n in names]
            variables["area"] = resolved
        if "media_player" in args:
            v = args["media_player"]
            variables["media_player"] = [v] if isinstance(v, str) else list(v)

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


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

class PersonalityLLMSmartAPI(llm.API):
    """Custom LLM API exposing smart discovery + action tools."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass=hass,
            id=SMART_DISCOVERY_API_ID,
            name="Personality LLM Smart Discovery",
        )

    def _get_music_script(self, llm_context: llm.LLMContext) -> str | None:
        """Return the first configured music script entity_id across all subentries.

        HA populates llm_context.assistant with the domain string ('conversation'),
        not the actual entity_id, so per-subentry lookup via the entity registry is
        unreliable. Since there is only one Music Assistant installation per home,
        scanning all subentries for the first configured script is safe.
        """
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            for subentry in entry.subentries.values():
                script = subentry.data.get(CONF_MUSIC_SCRIPT) or None
                if script:
                    _LOGGER.debug("_get_music_script: using %r for play_music tool", script)
                    return script
        _LOGGER.debug("_get_music_script: CONF_MUSIC_SCRIPT not set in any subentry — play_music tool not added")
        return None

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext,
    ) -> llm.APIInstance:
        tools: list[llm.Tool] = [
            DiscoverEntitiesTool(),
            GetEntityDetailsTool(),
            PerformActionTool(),
        ]

        # Build prompt — start with the base, then inject floor/area names and
        # speaking-device location so the model never has to guess colloquial names.
        prompt_parts = [SMART_API_PROMPT]

        # Inject all floor names so the model can map colloquial terms correctly
        # (e.g. "downstairs" → "Ground Floor", "upstairs" → "First Floor").
        if fr is not None:
            floor_reg = fr.async_get(self.hass)
            floor_names = [f.name for f in floor_reg.async_list_floors()]
            if floor_names:
                floors_str = ", ".join(f'"{n}"' for n in floor_names)
                example_floor = floor_names[0]
                prompt_parts.append(
                    f"Floor names in this home: {floors_str}. "
                    "These are FLOOR names — always pass them via the floor parameter, never as area. "
                    f"Example for a floor-wide light command: "
                    f"perform_action(domain='light', action='turn_on', target={{'floor': '{example_floor}'}})."
                )

        location = _get_device_location(self.hass, llm_context.device_id)
        if location["area"] or location["floor"]:
            loc_parts = []
            if location["area"]:
                loc_parts.append(f"area: {location['area']}")
            if location["floor"]:
                loc_parts.append(f"floor: {location['floor']}")
            loc_str = ", ".join(loc_parts)
            prompt_parts.append(
                f"The user is speaking from {loc_str}. "
                "When no location is specified in their request, target this area by default."
            )

        api_prompt = "\n\n".join(prompt_parts)

        music_script = self._get_music_script(llm_context)
        if music_script:
            tools.append(PlayMusicTool(music_script))
            api_prompt += (
                "\n\nFor music requests, ALWAYS use the play_music tool — never discover "
                "or call any script entity via perform_action. play_music handles all "
                "Music Assistant playback; calling the script via perform_action will fail."
            )
        else:
            _LOGGER.warning(
                "PersonalityLLMSmartAPI: play_music tool not available "
                "(CONF_MUSIC_SCRIPT not configured for this subentry)"
            )

        return llm.APIInstance(
            api=self,
            api_prompt=api_prompt,
            llm_context=llm_context,
            tools=tools,
        )

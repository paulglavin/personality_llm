"""Smart entity discovery for personality_llm.

Slim port of mike-nott/mcp-assist's discovery.py — only the general
filter path is included. The person/pet/aggregate routing heuristics
are deliberately omitted; the general path covers the same use cases
through plain filters (domain, area, name_contains).
"""
from __future__ import annotations

import fnmatch
import logging
from datetime import datetime
from typing import Any

from homeassistant.components.homeassistant import async_should_expose
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)

try:
    from homeassistant.helpers import floor_registry as fr
except ImportError:  # pragma: no cover
    fr = None

try:
    from homeassistant.helpers import label_registry as lr
except ImportError:  # pragma: no cover
    lr = None

_LOGGER = logging.getLogger(__name__)

_USEFUL_ATTRS = (
    "brightness",
    "temperature",
    "humidity",
    "unit_of_measurement",
    "device_class",
    "friendly_name",
    "current_temperature",
    "target_temp",
    "hvac_mode",
    "media_title",
    "volume_level",
)


class SmartDiscovery:
    """Filter-driven entity discovery with compact result shape."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def discover_entities(
        self,
        *,
        domain: str | None = None,
        area: str | None = None,
        floor: str | None = None,
        label: str | None = None,
        state: str | None = None,
        name_contains: str | None = None,
        device_class: str | list[str] | None = None,
        name_pattern: str | None = None,
        limit: int = 20,
        max_limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Discover entities matching the supplied filters."""
        limit = max(1, min(limit, max_limit))

        area_reg = ar.async_get(self.hass)
        entity_reg = er.async_get(self.hass)
        device_reg = dr.async_get(self.hass)
        floor_reg = fr.async_get(self.hass) if fr else None
        label_reg = lr.async_get(self.hass) if lr else None

        area_id = self._resolve_area_id(area, area_reg) if area else None
        if area and not area_id:
            return []

        floor_id = self._resolve_floor_id(floor, floor_reg) if floor else None
        if floor and not floor_id:
            return []

        label_id = self._resolve_label_id(label, label_reg) if label else None
        if label and not label_id:
            return []

        device_class_set: set[str] | None = None
        if device_class is not None:
            device_class_set = (
                {device_class} if isinstance(device_class, str) else set(device_class)
            )

        if name_pattern and "*" not in name_pattern and "?" not in name_pattern:
            name_pattern = f"*{name_pattern}*"

        results: list[dict[str, Any]] = []
        for state_obj in self.hass.states.async_all():
            entity_id = state_obj.entity_id
            if not async_should_expose(self.hass, "conversation", entity_id):
                continue

            entity_domain = entity_id.split(".")[0]
            if domain and entity_domain != domain:
                continue
            if state and state_obj.state.lower() != state.lower():
                continue

            entity_entry = entity_reg.async_get(entity_id)
            ctx = self._entity_context(
                entity_entry, device_reg, area_reg, floor_reg, label_reg,
            )

            if name_contains and not self._matches_name(
                name_contains.casefold(), state_obj, entity_entry, ctx,
            ):
                continue

            if device_class_set is not None:
                dc = state_obj.attributes.get("device_class")
                if dc not in device_class_set:
                    continue

            if name_pattern and not fnmatch.fnmatch(entity_id, name_pattern):
                continue

            if area_id and ctx["area_id"] != area_id:
                continue
            if floor_id and ctx["floor_id"] != floor_id:
                continue
            if label_id and label_id not in ctx["label_ids"]:
                continue

            results.append(self._format_entity(state_obj, ctx))
            if len(results) >= limit:
                break

        return results

    async def get_entity_details(
        self, entity_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Return full state and attributes for specific entity IDs."""
        out: dict[str, dict[str, Any]] = {}
        entity_reg = er.async_get(self.hass)
        device_reg = dr.async_get(self.hass)
        area_reg = ar.async_get(self.hass)
        floor_reg = fr.async_get(self.hass) if fr else None
        label_reg = lr.async_get(self.hass) if lr else None

        for entity_id in entity_ids:
            if not async_should_expose(self.hass, "conversation", entity_id):
                out[entity_id] = {"error": "entity not exposed to conversation"}
                continue
            state_obj = self.hass.states.get(entity_id)
            if not state_obj:
                out[entity_id] = {"error": "entity not found"}
                continue
            entity_entry = entity_reg.async_get(entity_id)
            ctx = self._entity_context(
                entity_entry, device_reg, area_reg, floor_reg, label_reg,
            )
            out[entity_id] = {
                "entity_id": entity_id,
                "name": state_obj.name,
                "domain": state_obj.domain,
                "state": state_obj.state,
                "attributes": self._serialize(dict(state_obj.attributes)),
                "area": ctx["area"],
                "floor": ctx["floor"],
                "labels": ctx["labels"],
                "last_changed": state_obj.last_changed.isoformat(),
                "last_updated": state_obj.last_updated.isoformat(),
            }
        return out

    # -- Helpers ------------------------------------------------------------

    def _resolve_area_id(self, name: str, area_reg: Any) -> str | None:
        get_by_name = getattr(area_reg, "async_get_area_by_name", None)
        if get_by_name:
            entry = get_by_name(name)
            if entry:
                return entry.id
        target = name.casefold()
        for entry in area_reg.async_list_areas():
            if entry.name.casefold() == target:
                return entry.id
            for alias in getattr(entry, "aliases", set()) or set():
                if alias.casefold() == target:
                    return entry.id
        return None

    def _resolve_floor_id(self, name: str, floor_reg: Any) -> str | None:
        if floor_reg is None:
            return None
        target = name.casefold()
        for entry in floor_reg.async_list_floors():
            if entry.name.casefold() == target:
                return entry.floor_id
            for alias in getattr(entry, "aliases", set()) or set():
                if alias.casefold() == target:
                    return entry.floor_id
        return None

    def _resolve_label_id(self, name: str, label_reg: Any) -> str | None:
        if label_reg is None:
            return None
        target = name.casefold()
        for entry in label_reg.async_list_labels():
            if entry.name.casefold() == target:
                return entry.label_id
        return None

    def _entity_context(
        self,
        entity_entry: Any,
        device_reg: Any,
        area_reg: Any,
        floor_reg: Any,
        label_reg: Any,
    ) -> dict[str, Any]:
        device = (
            device_reg.async_get(entity_entry.device_id)
            if entity_entry and entity_entry.device_id
            else None
        )
        area_id = (entity_entry.area_id if entity_entry else None) or (
            device.area_id if device else None
        )
        area = area_reg.async_get_area(area_id) if area_id else None
        floor_id = getattr(area, "floor_id", None) if area else None
        floor_name = None
        if floor_id and floor_reg is not None:
            floor_entry = floor_reg.async_get_floor(floor_id)
            if floor_entry:
                floor_name = floor_entry.name

        label_ids = set(getattr(entity_entry, "labels", set()) or set())
        if device:
            label_ids.update(getattr(device, "labels", set()) or set())
        if area:
            label_ids.update(getattr(area, "labels", set()) or set())

        labels: list[str] = []
        if label_reg is not None:
            for lid in label_ids:
                entry = label_reg.async_get_label(lid)
                labels.append(entry.name if entry else lid)
        labels.sort(key=str.casefold)

        return {
            "area": area.name if area else None,
            "area_id": area_id,
            "floor": floor_name,
            "floor_id": floor_id,
            "labels": labels,
            "label_ids": label_ids,
            "device_name": (
                (device.name_by_user or device.name) if device else None
            ),
        }

    def _matches_name(
        self,
        needle: str,
        state_obj: Any,
        entity_entry: Any,
        ctx: dict[str, Any],
    ) -> bool:
        candidates = {
            state_obj.entity_id,
            state_obj.name,
            state_obj.attributes.get("friendly_name") or "",
            ctx.get("area") or "",
            ctx.get("floor") or "",
            ctx.get("device_name") or "",
        }
        if entity_entry:
            for alias in getattr(entity_entry, "aliases", []) or []:
                if isinstance(alias, str):
                    candidates.add(alias)
        candidates.update(ctx.get("labels") or [])
        return any(c and needle in c.casefold() for c in candidates)

    def _format_entity(
        self, state_obj: Any, ctx: dict[str, Any],
    ) -> dict[str, Any]:
        info: dict[str, Any] = {
            "entity_id": state_obj.entity_id,
            "name": state_obj.name,
            "domain": state_obj.domain,
            "state": state_obj.state,
        }
        if ctx.get("area"):
            info["area"] = ctx["area"]
        if ctx.get("floor"):
            info["floor"] = ctx["floor"]
        if ctx.get("labels"):
            info["labels"] = ctx["labels"]

        attrs = {}
        for k in _USEFUL_ATTRS:
            if k in state_obj.attributes:
                attrs[k] = state_obj.attributes[k]
        if attrs:
            info["attributes"] = attrs
        return info

    @staticmethod
    def _serialize(attrs: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in attrs.items():
            if isinstance(v, datetime):
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out

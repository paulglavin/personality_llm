"""Smart structural index for token-efficient entity context.

Generates a compact structural snapshot of the Home Assistant system
(areas, floors, labels, domains, device_classes, helpers, scripts,
automations, calendars, zones, people) so the LLM can reason about
what *exists* without us injecting every entity in every prompt.

Discovery tools then fetch the small subset of entities relevant to
the current turn. See discovery.SmartDiscovery and tools.py.

This is a slimmed port of mike-nott/mcp-assist's IndexManager —
gap-filling and script field introspection are intentionally omitted
in Phase 0 and live on the backlog.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

from homeassistant.components.homeassistant import async_should_expose
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED

try:
    from homeassistant.helpers import floor_registry as fr
except ImportError:  # pragma: no cover - older HA
    fr = None

try:
    from homeassistant.helpers import label_registry as lr
except ImportError:  # pragma: no cover - older HA
    lr = None

_LOGGER = logging.getLogger(__name__)

_REFRESH_DEBOUNCE_SECONDS = 60


class IndexManager:
    """Build, cache, and serve a structural index of the HA system."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._index: dict[str, Any] | None = None
        self._last_updated: datetime | None = None
        self._refresh_task: asyncio.Task | None = None
        self._unsubs: list[Any] = []

    async def start(self) -> None:
        """Subscribe to registry events; index is built lazily on first request."""

        @callback
        def _registry_changed(event: Event) -> None:
            self._schedule_refresh()

        events = [
            EVENT_ENTITY_REGISTRY_UPDATED,
            ar.EVENT_AREA_REGISTRY_UPDATED,
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
        ]
        if fr is not None:
            events.append(fr.EVENT_FLOOR_REGISTRY_UPDATED)
        if lr is not None:
            events.append(lr.EVENT_LABEL_REGISTRY_UPDATED)

        for event_type in events:
            self._unsubs.append(
                self.hass.bus.async_listen(event_type, _registry_changed)
            )

        _LOGGER.debug("IndexManager listening on %d registry events", len(events))

    async def async_stop(self) -> None:
        """Detach event listeners and cancel pending refresh."""
        for unsub in self._unsubs:
            try:
                unsub()
            except Exception:  # pragma: no cover
                pass
        self._unsubs.clear()
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()

    def _schedule_refresh(self) -> None:
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
        self._refresh_task = asyncio.create_task(self._delayed_refresh())

    async def _delayed_refresh(self) -> None:
        try:
            await asyncio.sleep(_REFRESH_DEBOUNCE_SECONDS)
            await self.refresh_index()
        except asyncio.CancelledError:
            pass

    async def get_index(self) -> dict[str, Any]:
        if self._index is None:
            await self.refresh_index()
        return self._index or {}

    async def refresh_index(self) -> None:
        start = datetime.now()
        try:
            self._index = await self._generate_index()
            self._last_updated = datetime.now()
            elapsed = (datetime.now() - start).total_seconds()
            char_count = len(str(self._index))
            _LOGGER.info(
                "Index built in %.2fs (~%d tokens)",
                elapsed,
                char_count // 4,
            )
        except Exception:  # pragma: no cover - defensive
            _LOGGER.exception("Failed to build index")

    async def _generate_index(self) -> dict[str, Any]:
        results = await asyncio.gather(
            self._get_areas(),
            self._get_floors(),
            self._get_labels(),
            self._get_domains(),
            self._get_device_classes(),
            self._get_people(),
            self._get_calendars(),
            self._get_zones(),
            self._get_automations(),
            self._get_scripts(),
            self._get_input_helpers(),
            return_exceptions=True,
        )
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                _LOGGER.warning("Index component %d failed: %s", i, r)

        def _ok(r: Any, fallback: Any) -> Any:
            return fallback if isinstance(r, Exception) else r

        (
            areas, floors, labels, domains, device_classes,
            people, calendars, zones, automations, scripts, helpers,
        ) = results

        index: dict[str, Any] = {
            "areas": _ok(areas, []),
            "floors": _ok(floors, []),
            "labels": _ok(labels, []),
            "domains": _ok(domains, {}),
            "device_classes": _ok(device_classes, {}),
            "people": _ok(people, []),
            "calendars": _ok(calendars, []),
            "zones": _ok(zones, []),
            "automations": _ok(automations, []),
            "scripts": _ok(scripts, []),
        }
        if not isinstance(helpers, Exception):
            index.update(helpers)
        return index

    # -- Component fetchers -------------------------------------------------

    async def _get_areas(self) -> list[dict[str, Any]]:
        area_reg = ar.async_get(self.hass)
        entity_reg = er.async_get(self.hass)
        device_reg = dr.async_get(self.hass)
        floor_reg = fr.async_get(self.hass) if fr else None

        counts: dict[str, int] = defaultdict(int)
        for entity in entity_reg.entities.values():
            if not async_should_expose(self.hass, "conversation", entity.entity_id):
                continue
            if entity.area_id:
                counts[entity.area_id] += 1
            elif entity.device_id:
                device = device_reg.async_get(entity.device_id)
                if device and device.area_id:
                    counts[device.area_id] += 1

        out: list[dict[str, Any]] = []
        for area in area_reg.async_list_areas():
            count = counts.get(area.id, 0)
            if not count:
                continue
            floor_name = None
            floor_id = getattr(area, "floor_id", None)
            if floor_id and floor_reg is not None:
                floor_entry = floor_reg.async_get_floor(floor_id)
                if floor_entry:
                    floor_name = floor_entry.name
            out.append({
                "name": area.name,
                "entity_count": count,
                "floor": floor_name,
            })
        out.sort(key=lambda x: x["name"])
        return out

    async def _get_floors(self) -> list[dict[str, Any]]:
        if fr is None:
            return []
        floor_reg = fr.async_get(self.hass)
        area_reg = ar.async_get(self.hass)
        entity_reg = er.async_get(self.hass)
        device_reg = dr.async_get(self.hass)

        floor_areas: dict[str, list[str]] = defaultdict(list)
        for area in area_reg.async_list_areas():
            if getattr(area, "floor_id", None):
                floor_areas[area.floor_id].append(area.name)

        floor_entities: dict[str, set[str]] = defaultdict(set)
        for entity in entity_reg.entities.values():
            if not async_should_expose(self.hass, "conversation", entity.entity_id):
                continue
            area_id = entity.area_id
            if not area_id and entity.device_id:
                device = device_reg.async_get(entity.device_id)
                if device:
                    area_id = device.area_id
            if not area_id:
                continue
            area = area_reg.async_get_area(area_id)
            floor_id = getattr(area, "floor_id", None) if area else None
            if floor_id:
                floor_entities[floor_id].add(entity.entity_id)

        out: list[dict[str, Any]] = []
        for floor in floor_reg.async_list_floors():
            out.append({
                "name": floor.name,
                "area_count": len(floor_areas.get(floor.floor_id, [])),
                "entity_count": len(floor_entities.get(floor.floor_id, set())),
            })
        out.sort(key=lambda x: x["name"])
        return out

    async def _get_labels(self) -> list[dict[str, Any]]:
        if lr is None:
            return []
        label_reg = lr.async_get(self.hass)
        entity_reg = er.async_get(self.hass)
        device_reg = dr.async_get(self.hass)
        area_reg = ar.async_get(self.hass)

        label_entities: dict[str, set[str]] = defaultdict(set)
        for entity in entity_reg.entities.values():
            if not async_should_expose(self.hass, "conversation", entity.entity_id):
                continue
            device = device_reg.async_get(entity.device_id) if entity.device_id else None
            area_id = entity.area_id or (device.area_id if device else None)
            area = area_reg.async_get_area(area_id) if area_id else None

            combined = set(getattr(entity, "labels", set()) or set())
            if device:
                combined.update(getattr(device, "labels", set()) or set())
            if area:
                combined.update(getattr(area, "labels", set()) or set())
            for label_id in combined:
                label_entities[label_id].add(entity.entity_id)

        out: list[dict[str, Any]] = []
        for label in label_reg.async_list_labels():
            out.append({
                "name": label.name,
                "entity_count": len(label_entities.get(label.label_id, set())),
            })
        out.sort(key=lambda x: x["name"])
        return out

    async def _get_domains(self) -> dict[str, int]:
        entity_reg = er.async_get(self.hass)
        counts: dict[str, int] = defaultdict(int)
        for entity in entity_reg.entities.values():
            if async_should_expose(self.hass, "conversation", entity.entity_id):
                counts[entity.entity_id.split(".")[0]] += 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    async def _get_device_classes(self) -> dict[str, dict[str, int]]:
        entity_reg = er.async_get(self.hass)
        nested: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for entity in entity_reg.entities.values():
            if not async_should_expose(self.hass, "conversation", entity.entity_id):
                continue
            domain = entity.entity_id.split(".")[0]
            state = self.hass.states.get(entity.entity_id)
            if state and state.attributes.get("device_class"):
                nested[domain][state.attributes["device_class"]] += 1
        return {
            d: dict(sorted(c.items(), key=lambda x: x[1], reverse=True))
            for d, c in sorted(nested.items())
        }

    async def _get_people(self) -> list[str]:
        return self._collect_friendly_names("person.")

    async def _get_calendars(self) -> list[str]:
        return self._collect_friendly_names("calendar.")

    async def _get_zones(self) -> list[str]:
        names = self._collect_friendly_names("zone.")
        return [n for n in names if n.lower() != "home"]

    async def _get_automations(self) -> list[str]:
        return self._collect_friendly_names("automation.")

    async def _get_scripts(self) -> list[str]:
        return self._collect_friendly_names("script.")

    async def _get_input_helpers(self) -> dict[str, list[str]]:
        types = [
            "input_boolean", "input_text", "input_number",
            "input_select", "input_datetime", "input_button",
        ]
        out: dict[str, list[str]] = {}
        for t in types:
            names = self._collect_friendly_names(f"{t}.")
            if names:
                out[f"{t}s"] = names
        return out

    def _collect_friendly_names(self, prefix: str) -> list[str]:
        entity_reg = er.async_get(self.hass)
        names: list[str] = []
        for entity in entity_reg.entities.values():
            if not entity.entity_id.startswith(prefix):
                continue
            if not async_should_expose(self.hass, "conversation", entity.entity_id):
                continue
            state = self.hass.states.get(entity.entity_id)
            names.append(state.name if state else entity.entity_id.split(".", 1)[1])
        names.sort()
        return names

    # -- Prompt rendering ---------------------------------------------------

    def render_for_prompt(self, index: dict[str, Any]) -> str:
        """Render the index as a compact text block for the system prompt.

        Designed for ~400-700 tokens at 90 entities. JSON would be ~3x larger.
        """
        lines: list[str] = []

        areas = index.get("areas", [])
        if areas:
            parts = []
            for a in areas:
                floor = f", {a['floor']}" if a.get("floor") else ""
                parts.append(f"{a['name']} [{a['entity_count']}{floor}]")
            lines.append(f"Areas ({len(areas)}): " + ", ".join(parts))

        floors = index.get("floors", [])
        if floors:
            parts = [
                f"{f['name']} ({f['area_count']} areas, {f['entity_count']})"
                for f in floors
            ]
            lines.append(f"Floors ({len(floors)}): " + ", ".join(parts))

        labels = index.get("labels", [])
        if labels:
            parts = [f"{l['name']}({l['entity_count']})" for l in labels]
            lines.append(f"Labels: " + ", ".join(parts))

        domains = index.get("domains", {})
        if domains:
            parts = [f"{d}({c})" for d, c in domains.items()]
            lines.append("Domains: " + ", ".join(parts))

        device_classes = index.get("device_classes", {})
        if device_classes:
            flat: list[str] = []
            for domain, classes in device_classes.items():
                for cls, count in classes.items():
                    flat.append(f"{cls}({count})")
            if flat:
                lines.append("Device classes: " + ", ".join(flat))

        for key, label in (
            ("people", "People"),
            ("scripts", "Scripts"),
            ("automations", "Automations"),
            ("calendars", "Calendars"),
            ("zones", "Zones"),
        ):
            values = index.get(key, [])
            if values:
                lines.append(f"{label}: " + ", ".join(values))

        helper_keys = [
            k for k in index
            if k.startswith("input_") and k.endswith("s") and index[k]
        ]
        if helper_keys:
            parts = [f"{k}({len(index[k])})" for k in sorted(helper_keys)]
            lines.append("Helpers: " + ", ".join(parts))

        return "\n".join(lines)

"""Batched HA state writes for Vantage entities."""

from collections.abc import Callable
from datetime import datetime

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_call_later

_DEBOUNCE_SECS = 0.05


class VantageStateBatcher:
    """Coalesces async_write_ha_state calls across all entities in one config entry.

    When the Vantage controller activates a scene it broadcasts EL events for
    every load, task, LED, and adjust object it touches — up to ~30 events for a
    small scene, potentially 150+ for a floor-wide one. Without batching, each
    event fires _on_object_updated independently, scattering the resulting
    async_write_ha_state calls across as many separate asyncio callbacks.

    This batcher collects every entity that gets an update event into a dirty
    set, then flushes them all in a single loop pass 50ms after the last event.
    The result is one asyncio wakeup instead of N, and HA sees all state changes
    in the same event-loop iteration so it can batch its own downstream work
    (WebSocket pushes, automation triggers, etc.).

    The 50ms window also swallows Vantage transient STATUS messages that exist
    for only a few milliseconds during scene pre-calculation, preventing
    spurious state flips from reaching HA at all.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._dirty: set[Entity] = set()
        self._cancel: Callable[[], None] | None = None

    def mark_dirty(self, entity: Entity) -> None:
        """Mark an entity dirty and (re)start the flush timer."""
        self._dirty.add(entity)
        if self._cancel:
            self._cancel()
        self._cancel = async_call_later(self._hass, _DEBOUNCE_SECS, self._flush)

    def remove(self, entity: Entity) -> None:
        """Drop a departing entity so the flush doesn't write stale state."""
        self._dirty.discard(entity)

    @callback
    def _flush(self, _now: datetime) -> None:
        self._cancel = None
        dirty, self._dirty = self._dirty, set()
        for entity in dirty:
            entity.async_write_ha_state()

    def cancel(self) -> None:
        """Cancel any pending flush — called on integration unload."""
        if self._cancel:
            self._cancel()
            self._cancel = None
        self._dirty.clear()

"""Batched HA state writes for Vantage entities."""

import time
from collections.abc import Callable
from datetime import datetime

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_call_later

_DEBOUNCE_SECS = 0.05

# Upper bound on how long a flush can be deferred past the first pending
# update, regardless of how many further events keep resetting the debounce.
# A large scene (floor-wide activation, 150+ EL events touching tasks/LEDs/
# adjust objects across the house) can keep events arriving less than
# _DEBOUNCE_SECS apart for a second or more; without this cap, entities whose
# new state is already known sit unflushed until the *entire* flood quiets
# down, not just their own update.
_MAX_WAIT_SECS = 0.25


class VantageStateBatcher:
    """Coalesces async_write_ha_state calls across all entities in one config entry.

    When the Vantage controller activates a scene it broadcasts EL events for
    every load, task, LED, and adjust object it touches — up to ~30 events for a
    small scene, potentially 150+ for a floor-wide one. Without batching, each
    event fires _on_object_updated independently, scattering the resulting
    async_write_ha_state calls across as many separate asyncio callbacks.

    This batcher collects every entity that gets an update event into a dirty
    set, then flushes them all in a single loop pass 50ms after the last event
    (or _MAX_WAIT_SECS after the first pending event, whichever comes first).
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
        self._first_dirty_at: float | None = None

    def mark_dirty(self, entity: Entity) -> None:
        """Mark an entity dirty and (re)start the flush timer."""
        now = time.monotonic()
        self._dirty.add(entity)
        if self._first_dirty_at is None:
            self._first_dirty_at = now

        if self._cancel:
            self._cancel()

        wait = min(_DEBOUNCE_SECS, self._first_dirty_at + _MAX_WAIT_SECS - now)
        wait = max(wait, 0.0)
        self._cancel = async_call_later(self._hass, wait, self._flush)

    def remove(self, entity: Entity) -> None:
        """Drop a departing entity so the flush doesn't write stale state."""
        self._dirty.discard(entity)

    @callback
    def _flush(self, _now: datetime) -> None:
        self._cancel = None
        self._first_dirty_at = None
        dirty, self._dirty = self._dirty, set()
        for entity in dirty:
            entity.async_write_ha_state()

    def cancel(self) -> None:
        """Cancel any pending flush — called on integration unload."""
        if self._cancel:
            self._cancel()
            self._cancel = None
        self._dirty.clear()
        self._first_dirty_at = None

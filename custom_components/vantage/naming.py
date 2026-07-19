"""Hierarchical naming utilities for Vantage entities and devices.

  hierarchical_load_name()    — entity display name for Load objects
  hierarchical_station_name() — device display name for Station objects (keypads, relays)
  button_entity_name()        — device-relative entity display name for Button objects

The load/station naming algorithm replicates pyvantage register_id() exactly
so that entity IDs match the old integration, preserving automations and
history. Button entities live under their parent keypad/TPT device instead
(``has_entity_name = True``), so their naming is device-relative rather than
hierarchical -- see button_entity_name().
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiovantage.objects import TPT

if TYPE_CHECKING:
    from aiovantage import Vantage
    from aiovantage.objects import Button, LocationObject


def get_area_lineage(client: "Vantage", area_vid: int | None) -> list[str]:
    """Walk the area tree upward from area_vid, returning names closest-to-root.

    For example, area "Dining Room Balcony" whose parent is "1st Floor" whose
    parent is "Exterior" whose parent is the root "Harr Residence" returns:
        ["Dining Room Balcony", "1st Floor", "Exterior", "Harr Residence"]
    """
    lineage: list[str] = []
    current = area_vid
    count = 0
    while current and count < 10:
        area = client.areas.get(current)
        if area is None:
            break
        lineage.append((area.d_name or "").strip() or area.name)
        current = area.area  # parent area VID; 0 or None at root
        count += 1
    return lineage


def hierarchical_load_name(client: "Vantage", obj: "LocationObject") -> str:
    """Build a hierarchical name for a load, matching pyvantage register_id().

    Algorithm (mirrors pyvantage exactly):
    1. Walk the area tree upward to get the lineage (closest-to-root order).
    2. Drop the root area (last element).
    3. Reverse to get top-down order.
    4. Skip any area whose name starts with "Station Load " or "Color Load ".
    5. Join with "-" and append the load's display name.

    Example: VID 447 in "Dining Room Balcony" → "1st Floor" → "Exterior" → root
      returns "Exterior-1st Floor-Dining Room Balcony-Fan (Ceiling)"
    """
    lineage = get_area_lineage(client, obj.area)
    parts = [
        p
        for p in reversed(lineage[:-1])  # drop root, reverse to top-down
        if not p.startswith("Station Load ")
        and not p.startswith("Color Load ")
    ]
    prefix = "-".join(parts) + "-" if parts else ""
    load_name = (getattr(obj, "d_name", None) or "").strip() or obj.name
    return prefix + load_name


def hierarchical_station_name(client: "Vantage", obj: "LocationObject") -> str:
    """Build a hierarchical name for a station device (keypad, relay, etc.).

    Uses the same algorithm as hierarchical_load_name so that device names in
    the HA device registry are unique and area-contextual without needing to
    hard-code area names into the XML.

    Example: Keypad "Keypad Entry" in Wine Cellar (Basement)
      → "Basement-Wine Cellar-Keypad Entry"
    """
    lineage = get_area_lineage(client, obj.area)
    parts = [
        p
        for p in reversed(lineage[:-1])
        if not p.startswith("Station Load ")
        and not p.startswith("Color Load ")
    ]
    prefix = "-".join(parts) + "-" if parts else ""
    station_name = (getattr(obj, "d_name", None) or "").strip() or obj.name.strip() or str(obj.vid)
    return prefix + station_name


def button_entity_name(client: "Vantage", obj: "Button") -> str:
    """Build a device-relative name for a button entity: "Button {pos} (label)".

    Buttons live under their parent keypad/TPT device (``has_entity_name`` is
    True), so this returns only the button's own identity -- HA prepends the
    device name automatically. The position is always included so buttons are
    identifiable and orderable even when no label can be found; a label is
    appended in parentheses when one resolves, checked in this order:

      1. The button's own engraved text (``text1``/``text2``).
      2. The button's own ``name`` (e.g. "Left Button" on a TPT).
      3. For TPT touchscreen buttons, the on-screen LCD widget label that
         targets this button (``TPT.button_labels()``) -- most physical
         Button objects on a TPT are blank; the real label is drawn on the
         touchscreen page instead.

    Buttons with none of the above are named just "Button {pos}".
    """
    pos = obj.parent.position
    label = (
        " ".join(p for p in (obj.text1.strip(), obj.text2.strip()) if p)
        or obj.name.strip()
        or _tpt_button_label(client, obj)
    )
    return f"Button {pos}" + (f" ({label})" if label else "")


def _tpt_button_label(client: "Vantage", obj: "Button") -> str:
    """Return the on-screen LCD label for a TPT button, if any."""
    station = client.stations.get(obj.parent.vid)
    if not isinstance(station, TPT):
        return ""
    return station.button_labels().get(obj.vid, "")

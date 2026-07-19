"""Migration functions for the Vantage integration."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .config_entry import VantageConfigEntry
from .const import DOMAIN, LOGGER


async def async_migrate_data(hass: HomeAssistant, entry: VantageConfigEntry) -> None:
    """Run all Vantage data migrations."""

    async_delete_back_boxes(hass, entry)
    async_delete_serial_number_entities(hass, entry)
    async_delete_orphaned_button_devices(hass, entry)


def async_delete_back_boxes(hass: HomeAssistant, entry: VantageConfigEntry) -> None:
    """Delete back boxes from the device registry."""
    dev_reg = dr.async_get(hass)

    back_box_devices = [
        device
        for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
        if device.model == "BackBox"
    ]

    if back_box_devices:
        LOGGER.debug(f"Deleting {len(back_box_devices)} back boxes from the registry.")

        for device in back_box_devices:
            dev_reg.async_remove_device(device.id)


def async_delete_serial_number_entities(
    hass: HomeAssistant, entry: VantageConfigEntry
) -> None:
    """Delete serial number entities from the entity registry."""
    ent_reg = er.async_get(hass)

    serial_number_entities = [
        entity
        for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        if entity.unique_id.endswith(":serial_number")
    ]

    if serial_number_entities:
        LOGGER.debug(
            f"Deleting {len(serial_number_entities)} serial number entities from the registry."
        )

        for entity in serial_number_entities:
            ent_reg.async_remove(entity.entity_id)


def async_delete_orphaned_button_devices(
    hass: HomeAssistant, entry: VantageConfigEntry
) -> None:
    """Delete standalone devices left behind by buttons that now live on their keypad.

    Button sensors and LEDs used to have no parent device, so each button got
    its own device (e.g. "Button 1336"). They now attach to their parent
    keypad/TPT device via ``parent_obj``, so a leftover device whose
    identifier is a Button's own VID is *usually* stale -- ``async_cleanup_devices``
    doesn't catch these because the button object itself still exists, it
    just no longer owns a device of its own.

    IMPORTANT: removing a device from the device registry cascades to delete
    every entity still registered against it. If a button's keypad/TPT lookup
    ever fails at entity-setup time (e.g. the parent isn't in ``client.stations``
    yet), its entities land back on this per-button device -- deleting it
    unconditionally would silently delete those entities too. Only remove a
    button-identified device once it has zero entities left on it; skip (and
    log) anything still in use so it surfaces instead of disappearing.
    """
    vantage = entry.runtime_data.client
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    orphaned_devices = []
    skipped_devices = []
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        device_id = next(x[1] for x in device.identifiers if x[0] == DOMAIN)
        vantage_id = int(device_id.split(":")[0])
        if vantage_id not in vantage.buttons:
            continue

        if er.async_entries_for_device(
            ent_reg, device.id, include_disabled_entities=True
        ):
            skipped_devices.append(device)
        else:
            orphaned_devices.append(device)

    if skipped_devices:
        LOGGER.warning(
            "%d button device(s) still have entities attached and were NOT "
            "removed -- their keypad/TPT parent may have failed to resolve "
            "this startup: %s",
            len(skipped_devices),
            [device.name for device in skipped_devices],
        )

    if orphaned_devices:
        LOGGER.debug(
            f"Deleting {len(orphaned_devices)} orphaned button devices from the registry."
        )

        for device in orphaned_devices:
            dev_reg.async_remove_device(device.id)

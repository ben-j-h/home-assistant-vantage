"""The Vantage InFusion Controller integration."""

import asyncio
from pathlib import Path

from aiovantage import Vantage
from aiovantage.errors import (
    ClientConnectionError,
    LoginFailedError,
    LoginRequiredError,
)
from aiovantage.events import ObjectUpdated
from aiovantage.objects import Master

from homeassistant.config_entries import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.util.ssl import get_default_no_verify_context

from .batch import VantageStateBatcher
from .config_entry import VantageConfigEntry, VantageData
from .const import CONF_LOCAL_CONFIG_REQUIRED
from .device import async_cleanup_devices, async_setup_devices
from .entity import async_cleanup_entities
from .events import async_setup_events
from .migrate import async_migrate_data
from .services import async_register_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.FAN,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]

# How long to wait after receiving a system programming event before refreshing
SYSTEM_PROGRAMMING_DELAY = 30


async def async_setup_entry(hass: HomeAssistant, entry: VantageConfigEntry) -> bool:
    """Set up Vantage integration from a config entry."""
    host = entry.data[CONF_HOST]

    # Look for a local Design Center backup XML in the HA config directory.
    # File naming convention matches pyvantage: {host}_config.txt
    use_local_only = entry.options.get(CONF_LOCAL_CONFIG_REQUIRED, False)
    candidate = Path(hass.config.config_dir) / f"{host}_config.txt"
    local_config_file = candidate if (use_local_only or candidate.is_file()) else None

    # Create a Vantage client
    vantage = Vantage(
        host,
        entry.data.get(CONF_USERNAME),
        entry.data.get(CONF_PASSWORD),
        ssl=entry.data.get(CONF_SSL, True),
        ssl_context_factory=get_default_no_verify_context,
        local_config_file=local_config_file,
        local_config_file_required=use_local_only,
    )

    # Store the client and state batcher in the config entry's runtime data
    batcher = VantageStateBatcher(hass)
    entry.runtime_data = VantageData(client=vantage, batcher=batcher)
    entry.async_on_unload(batcher.cancel)

    try:
        # Initialize and fetch all objects
        await vantage.initialize()

        # Add Vantage devices (controllers, modules, stations) to the device registry
        await async_setup_devices(hass, entry)

        # Set up each platform (lights, covers, etc.)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Register services (start task, stop task, etc.)
        async_register_services(hass)

        # Generate events for button presses, etc.
        async_setup_events(hass, entry)

        # Clean up any orphaned devices and entities
        async_cleanup_devices(hass, entry)
        async_cleanup_entities(hass, entry)

        # Run any migrations
        await async_migrate_data(hass, entry)

        # Subscribe to system programming events
        def on_master_updated(event: ObjectUpdated[Master]) -> None:
            # Return early if the m_time attribute did not change
            if "m_time" not in event.attrs_changed:
                return

            async def refresh_controllers() -> None:
                # The m_time attribute changes at the start of system programming.
                # Unfortunately, the Vantage controller does not send an event when
                # programming ends, so we must wait for a short time before refreshing
                # controllers to avoid fetching incomplete data.
                await asyncio.sleep(SYSTEM_PROGRAMMING_DELAY)
                await vantage.initialize()

            hass.async_create_task(refresh_controllers())

        entry.async_on_unload(
            vantage.masters.subscribe(ObjectUpdated, on_master_updated)
        )

    except (LoginFailedError, LoginRequiredError) as err:
        # Handle expired or invalid credentials. This will prompt the user to
        # reconfigure the integration.
        raise ConfigEntryAuthFailed from err

    except (ClientConnectionError, FileNotFoundError) as err:
        # Handle connection errors and missing required local config file.
        # Home Assistant will automatically retry setup later.
        raise ConfigEntryNotReady(str(err)) from err

    return True


async def async_unload_entry(hass: HomeAssistant, entry: VantageConfigEntry) -> bool:
    """Unload a config entry."""
    # Close the Vantage client connection
    entry.runtime_data.client.close()

    # Unload all platforms
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

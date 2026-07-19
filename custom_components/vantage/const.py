"""Constants for the Vantage InFusion Controller integration."""

import logging

# Logging
LOGGER = logging.getLogger(__package__)

# Domain
DOMAIN = "vantage"

# Services
SERVICE_START_TASK = "start_task"
SERVICE_STOP_TASK = "stop_task"
SERVICE_SYNC_DATETIME = "sync_datetime"

# Events
EVENT_BUTTON_PRESSED = f"{DOMAIN}_button_pressed"
EVENT_BUTTON_RELEASED = f"{DOMAIN}_button_released"
EVENT_TASK_STARTED = f"{DOMAIN}_task_started"
EVENT_TASK_STOPPED = f"{DOMAIN}_task_stopped"
EVENT_TASK_STATE_CHANGED = f"{DOMAIN}_task_state_changed"

# Climate constants
FAN_MAX = "max"

# Button LED option: set True when keypads support the blue channel
CONF_BLUE_BUTTON_LED = "blue_button_led"

# When True, raise an error if the local config file is missing instead of
# falling back to live discovery from the controller.
CONF_LOCAL_CONFIG_REQUIRED = "local_config_required"

# Default ramp (fade) time in seconds applied to load on/off when the caller
# does not specify an explicit transition. Applied controller-side via Load.Ramp.
CONF_DEFAULT_RAMP_RATE = "default_ramp_rate"
DEFAULT_RAMP_RATE = 1.5

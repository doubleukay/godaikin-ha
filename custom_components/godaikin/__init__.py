"""The GO DAIKIN integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api import ApiClient
from .auth import AuthClient
from .const import (
    CONF_MOLD_PROOF_DURATION,
    DEFAULT_MOLD_PROOF_DURATION,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import GodaikinDataUpdateCoordinator
from .mold_proof import MoldProofManager

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GO DAIKIN from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    # Initialize authentication and API client
    auth = AuthClient(username=username, password=password)
    api = ApiClient(auth)

    # Initialize coordinator
    coordinator = GodaikinDataUpdateCoordinator(
        hass=hass,
        api_client=api,
        config_entry=entry,
    )

    # Fetch initial data
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Error connecting to GO DAIKIN: {err}") from err

    # Initialize mold-proof manager
    mold_proof_manager = MoldProofManager(hass, coordinator)
    coordinator.mold_proof = mold_proof_manager

    # Load saved mold-proof state from storage
    await mold_proof_manager.async_load()

    # Set mold-proof duration from options
    duration = entry.options.get(CONF_MOLD_PROOF_DURATION, DEFAULT_MOLD_PROOF_DURATION)
    mold_proof_manager.set_duration(duration)

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Clean up resources and remove coordinator from hass.data
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        # Close aiohttp session
        await coordinator.api.session.close()

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)

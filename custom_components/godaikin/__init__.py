"""The GO DAIKIN integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import Store

from .api import ApiClient
from .auth import AuthClient
from .const import (
    CONF_MOLD_PROOF_DURATION,
    DEFAULT_MOLD_PROOF_DURATION,
    DOMAIN,
    PLATFORMS,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .coordinator import GodaikinDataUpdateCoordinator
from .mold_proof import (
    MoldProofManager,
    async_clear_legacy_pending,
    async_init_legacy_pending,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GO DAIKIN from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    # Record which entries may migrate the legacy shared settings before
    # anything below can fail, so the list reflects the entries at upgrade time
    try:
        await async_init_legacy_pending(hass, Store(hass, STORAGE_VERSION, STORAGE_KEY))
    except Exception as err:
        _LOGGER.warning("Could not initialize the legacy migration list: %s", err)

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
    mold_proof_manager = MoldProofManager(hass, coordinator, entry)
    coordinator.mold_proof = mold_proof_manager

    # Cancel pending mold-proof timers on every unload path so they don't
    # outlive the entry (persisted cycles resume on the next setup)
    entry.async_on_unload(mold_proof_manager.async_unload)

    # Set mold-proof duration from options
    duration = entry.options.get(CONF_MOLD_PROOF_DURATION, DEFAULT_MOLD_PROOF_DURATION)
    mold_proof_manager.set_duration(duration)

    # Load saved mold-proof state from storage (re-arms resumed cycles)
    await mold_proof_manager.async_load()

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
        # Cancel mold-proof timers and let in-flight commands/saves finish
        # before the API session goes away and a reload can persist new state
        await coordinator.mold_proof.async_shutdown()
        # Close aiohttp session
        await coordinator.api.session.close()

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the per-entry mold-proof storage when the entry is deleted."""
    await Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}").async_remove()

    # Drop the entry from the legacy store's pending-migration list (if the
    # legacy store exists) so a re-added entry never imports stale settings
    try:
        await async_clear_legacy_pending(
            hass, Store(hass, STORAGE_VERSION, STORAGE_KEY), entry.entry_id
        )
    except Exception as err:
        _LOGGER.warning("Could not update the legacy migration list: %s", err)

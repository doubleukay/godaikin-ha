"""Light platform for GO DAIKIN integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GodaikinDataUpdateCoordinator
from .types import Aircond, UniqueID

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GO DAIKIN light entities from a config entry."""
    coordinator: GodaikinDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        GodaikinStatusLED(coordinator, unique_id)
        for unique_id in coordinator.data.keys()
        if coordinator.data[unique_id].shadowState.Ena_LEDOff
    ]

    async_add_entities(entities)


class GodaikinStatusLED(CoordinatorEntity[GodaikinDataUpdateCoordinator], LightEntity):
    """Representation of GO DAIKIN status LED."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:lightning-bolt-circle"
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(
        self,
        coordinator: GodaikinDataUpdateCoordinator,
        unique_id: UniqueID,
    ) -> None:
        """Initialize the status LED."""
        super().__init__(coordinator)
        self._unique_id = unique_id
        self._attr_unique_id = f"{unique_id}_status_led"

    @property
    def aircond(self) -> Aircond:
        """Return the air conditioner data."""
        return self.coordinator.data[self._unique_id]

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self.aircond.ACName} Status LED"

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._unique_id)},
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.aircond.is_connected

    @property
    def is_on(self) -> bool:
        """Return true if the status LED is on."""
        return not self.aircond.shadowState.Set_LEDOff

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the status LED on."""
        await self.coordinator.api.set_status_led(self._unique_id, on=True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the status LED off."""
        await self.coordinator.api.set_status_led(self._unique_id, on=False)
        await self.coordinator.async_request_refresh()

"""Switch platform for GO DAIKIN integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GodaikinDataUpdateCoordinator
from .types import UniqueID

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GO DAIKIN switch entities from a config entry."""
    coordinator: GodaikinDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        GodaikinMoldProofSwitch(coordinator, unique_id)
        for unique_id in coordinator.data.keys()
    ]

    async_add_entities(entities)


class GodaikinMoldProofSwitch(
    CoordinatorEntity[GodaikinDataUpdateCoordinator], SwitchEntity
):
    """Representation of GO DAIKIN mold-proof switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:air-filter"

    def __init__(
        self,
        coordinator: GodaikinDataUpdateCoordinator,
        unique_id: UniqueID,
    ) -> None:
        """Initialize the mold-proof switch."""
        super().__init__(coordinator)
        self._unique_id = unique_id
        self._attr_unique_id = f"{unique_id}_mold_proof"
        self._attr_name = f"{coordinator.data[unique_id].ACName} Mold-proof"

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._unique_id)},
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data[self._unique_id].is_connected
        )

    @property
    def is_on(self) -> bool:
        """Return true if mold-proof is enabled."""
        if not self.coordinator.mold_proof:
            return False
        return self.coordinator.mold_proof.is_enabled(self._unique_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.mold_proof:
            return {}

        attrs = {}
        if self.coordinator.mold_proof.is_active(self._unique_id):
            attrs["status"] = "active"
            remaining = self.coordinator.mold_proof.get_remaining_time(self._unique_id)
            attrs["remaining_seconds"] = remaining
            attrs["remaining_minutes"] = round(remaining / 60, 1)
        else:
            attrs["status"] = "idle"

        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable mold-proof for this device."""
        if self.coordinator.mold_proof:
            await self.coordinator.mold_proof.set_enabled(self._unique_id, True)
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable mold-proof for this device."""
        if self.coordinator.mold_proof:
            await self.coordinator.mold_proof.set_enabled(self._unique_id, False)
            self.async_write_ha_state()

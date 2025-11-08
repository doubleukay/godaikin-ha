"""Sensor platform for GO DAIKIN integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
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
    """Set up GO DAIKIN sensor entities from a config entry."""
    coordinator: GodaikinDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []

    for unique_id in coordinator.data.keys():
        entities.extend(
            [
                GodaikinPowerSensor(coordinator, unique_id),
                GodaikinIndoorTempSensor(coordinator, unique_id),
                GodaikinOutdoorTempSensor(coordinator, unique_id),
                GodaikinEnergySensor(coordinator, unique_id),
                GodaikinMoldProofRemainingSensor(coordinator, unique_id),
            ]
        )

    async_add_entities(entities)


class GodaikinSensorBase(
    CoordinatorEntity[GodaikinDataUpdateCoordinator], SensorEntity
):
    """Base class for GO DAIKIN sensors."""

    def __init__(
        self,
        coordinator: GodaikinDataUpdateCoordinator,
        unique_id: UniqueID,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._unique_id = unique_id
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{unique_id}_{sensor_type}"

    @property
    def aircond(self) -> Aircond:
        """Return the air conditioner data."""
        return self.coordinator.data[self._unique_id]

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


class GodaikinPowerSensor(GodaikinSensorBase):
    """Power consumption sensor for GO DAIKIN air conditioner."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(
        self,
        coordinator: GodaikinDataUpdateCoordinator,
        unique_id: UniqueID,
    ) -> None:
        """Initialize the power sensor."""
        super().__init__(coordinator, unique_id, "power")
        self._attr_name = f"{self.aircond.ACName} Power"

    @property
    def native_value(self) -> float | None:
        """Return the power consumption."""
        return self.aircond.shadowState.Sta_ODPwrCon


class GodaikinIndoorTempSensor(GodaikinSensorBase):
    """Indoor temperature sensor for GO DAIKIN air conditioner."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator: GodaikinDataUpdateCoordinator,
        unique_id: UniqueID,
    ) -> None:
        """Initialize the indoor temperature sensor."""
        super().__init__(coordinator, unique_id, "indoor_temperature")
        self._attr_name = f"{self.aircond.ACName} Indoor Temperature"

    @property
    def native_value(self) -> float | None:
        """Return the indoor temperature."""
        return self.aircond.shadowState.Sta_IDRoomTemp


class GodaikinOutdoorTempSensor(GodaikinSensorBase):
    """Outdoor temperature sensor for GO DAIKIN air conditioner."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator: GodaikinDataUpdateCoordinator,
        unique_id: UniqueID,
    ) -> None:
        """Initialize the outdoor temperature sensor."""
        super().__init__(coordinator, unique_id, "outdoor_temperature")
        self._attr_name = f"{self.aircond.ACName} Outdoor Temperature"

    @property
    def native_value(self) -> float | None:
        """Return the outdoor temperature."""
        return self.aircond.shadowState.Sta_ODAirTemp


class GodaikinEnergySensor(GodaikinSensorBase):
    """Energy consumption sensor for GO DAIKIN air conditioner."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(
        self,
        coordinator: GodaikinDataUpdateCoordinator,
        unique_id: UniqueID,
    ) -> None:
        """Initialize the energy sensor."""
        super().__init__(coordinator, unique_id, "energy")
        self._attr_name = f"{self.aircond.ACName} Energy"

    @property
    def native_value(self) -> float | None:
        """Return the energy consumption."""
        return round(self.coordinator.get_energy_usage(self._unique_id), 2)


class GodaikinMoldProofRemainingSensor(GodaikinSensorBase):
    """Mold-proof remaining time sensor for GO DAIKIN air conditioner."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(
        self,
        coordinator: GodaikinDataUpdateCoordinator,
        unique_id: UniqueID,
    ) -> None:
        """Initialize the mold-proof remaining sensor."""
        super().__init__(coordinator, unique_id, "mold_proof_remaining")
        self._attr_name = f"{self.aircond.ACName} Mold-proof remaining"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success or not self.aircond.is_connected:
            return False
        if not self.coordinator.mold_proof:
            return False
        return self.coordinator.mold_proof.is_active(self._unique_id)

    @property
    def native_value(self) -> float | None:
        """Return the remaining mold-proof time in minutes."""
        if not self.coordinator.mold_proof:
            return None
        if not self.coordinator.mold_proof.is_active(self._unique_id):
            return None
        remaining_seconds = self.coordinator.mold_proof.get_remaining_time(
            self._unique_id
        )
        return round(remaining_seconds / 60, 1)

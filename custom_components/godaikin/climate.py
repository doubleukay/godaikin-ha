"""Climate platform for GO DAIKIN integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    FAN_MODES,
    MAX_TEMP,
    MIN_TEMP,
    PRECISION,
    TEMP_STEP,
)
from .coordinator import GodaikinDataUpdateCoordinator
from .types import Aircond, AircondMode, AircondPreset, AircondSwing, FanSpeed, UniqueID

_LOGGER = logging.getLogger(__name__)

HVAC_MODE_MAP = {
    "off": HVACMode.OFF,
    "cool": HVACMode.COOL,
    "dry": HVACMode.DRY,
    "fan_only": HVACMode.FAN_ONLY,
}

HVAC_MODE_REVERSE_MAP = {v: k for k, v in HVAC_MODE_MAP.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GO DAIKIN climate entities from a config entry."""
    coordinator: GodaikinDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        GodaikinClimate(coordinator, unique_id) for unique_id in coordinator.data.keys()
    ]

    async_add_entities(entities)


class GodaikinClimate(CoordinatorEntity[GodaikinDataUpdateCoordinator], ClimateEntity):
    """Representation of a GO DAIKIN air conditioner."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_target_temperature_step = TEMP_STEP
    _attr_precision = PRECISION

    def __init__(
        self,
        coordinator: GodaikinDataUpdateCoordinator,
        unique_id: UniqueID,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._unique_id = unique_id
        self._attr_unique_id = unique_id

    @property
    def aircond(self) -> Aircond:
        """Return the air conditioner data."""
        return self.coordinator.data[self._unique_id]

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self.aircond.ACName

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._unique_id)},
            "name": self.aircond.ACName,
            "manufacturer": "Daikin",
            "model": "GO DAIKIN",
            "connections": {("mac", self.aircond.mac_address)},
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.aircond.is_connected

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        if not self.aircond.is_on:
            return HVACMode.OFF

        mode = AircondMode(self.aircond.shadowState.Set_Mode).name.lower()
        return HVAC_MODE_MAP.get(mode, HVACMode.OFF)

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return available HVAC modes."""
        return [HVACMode.OFF, HVACMode.COOL, HVACMode.DRY, HVACMode.FAN_ONLY]

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self.aircond.shadowState.Sta_IDRoomTemp

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self.aircond.shadowState.Set_Temp

    @property
    def fan_mode(self) -> str | None:
        """Return the fan setting."""
        fan_speed = FanSpeed(self.aircond.shadowState.Set_Fan)
        return fan_speed.name.lower()

    @property
    def fan_modes(self) -> list[str]:
        """Return the list of available fan modes."""
        return FAN_MODES

    @property
    def swing_mode(self) -> str | None:
        """Return the swing setting."""
        swing = AircondSwing(self.aircond.shadowState.Set_UDLvr)
        return swing.name.title()

    @property
    def swing_modes(self) -> list[str]:
        """Return the list of available swing modes."""
        modes = ["Off", "Auto"]
        if self.aircond.shadowState.Ena_UDStep:
            modes += ["Step_1", "Step_2", "Step_3", "Step_4", "Step_5"]
        return modes

    @property
    def swing_horizontal_mode(self) -> str | None:
        """Return the horizontal swing setting."""
        if not self.aircond.shadowState.Ena_LRSwing:
            return None

        swing = AircondSwing(self.aircond.shadowState.Set_LRLvr)
        return swing.name.title()

    @property
    def swing_horizontal_modes(self) -> list[str] | None:
        """Return the list of available horizontal swing modes."""
        if not self.aircond.shadowState.Ena_LRSwing:
            return None

        modes = ["Off", "Auto"]
        if self.aircond.shadowState.Ena_LRStep:
            modes += ["Step_1", "Step_2", "Step_3", "Step_4", "Step_5"]
        return modes

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        state = self.aircond.shadowState
        if state.Set_Turbo:
            return AircondPreset.BOOST.value
        elif state.Set_Breeze:
            return AircondPreset.COMFORT.value
        elif state.Set_Ecoplus:
            return AircondPreset.ECO.value
        elif state.Set_Sleep:
            return AircondPreset.SLEEP.value
        return AircondPreset.NONE.value

    @property
    def preset_modes(self) -> list[str]:
        """Return the list of available preset modes."""
        state = self.aircond.shadowState
        modes: list[str] = [AircondPreset.NONE.value]

        if state.Ena_Turbo:
            modes.append(AircondPreset.BOOST.value)
        if state.Ena_Breeze:
            modes.append(AircondPreset.COMFORT.value)
        if state.Ena_Ecoplus:
            modes.append(AircondPreset.ECO.value)
        if state.Ena_Silent:
            modes.append(AircondPreset.SLEEP.value)

        return modes

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE
        )

        if self.preset_modes:
            features |= ClimateEntityFeature.PRESET_MODE

        if self.swing_horizontal_modes:
            features |= ClimateEntityFeature.SWING_HORIZONTAL_MODE

        return features

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.api.turn_off(self._unique_id)
        elif hvac_mode == HVACMode.COOL:
            await self.coordinator.api.set_mode(self._unique_id, mode=AircondMode.COOL)
        elif hvac_mode == HVACMode.DRY:
            await self.coordinator.api.set_mode(self._unique_id, mode=AircondMode.DRY)
        elif hvac_mode == HVACMode.FAN_ONLY:
            await self.coordinator.api.set_mode(
                self._unique_id, mode=AircondMode.FAN_ONLY
            )

        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.api.set_temperature(
                self._unique_id, temperature=int(temperature)
            )
            await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode."""
        fan = FanSpeed[fan_mode.upper()]
        await self.coordinator.api.set_fan_mode(self._unique_id, fan=fan)
        await self.coordinator.async_request_refresh()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new swing mode."""
        swing = AircondSwing[swing_mode.upper()]
        await self.coordinator.api.set_swing(
            self._unique_id, swing=swing, horizontal=False
        )
        await self.coordinator.async_request_refresh()

    async def async_set_swing_horizontal_mode(self, swing_mode: str) -> None:
        """Set new horizontal swing mode."""
        swing = AircondSwing[swing_mode.upper()]
        await self.coordinator.api.set_swing(
            self._unique_id, swing=swing, horizontal=True
        )
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        try:
            preset = AircondPreset(preset_mode)
        except ValueError:
            _LOGGER.warning("Unknown preset mode: %s", preset_mode)
            preset = AircondPreset.NONE

        await self.coordinator.api.set_preset(self._unique_id, preset=preset)
        await self.coordinator.async_request_refresh()

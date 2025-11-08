"""Mold-proof manager for GO DAIKIN integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Callable, TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .types import AircondMode, FanSpeed, UniqueID

if TYPE_CHECKING:
    from .coordinator import GodaikinDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class MoldProofState:
    """State for mold-proof operation."""

    unique_id: UniqueID
    start_time: datetime
    previous_mode: AircondMode
    previous_fan_speed: FanSpeed
    cancel_timer: Callable | None = None


class MoldProofManager:
    """Manage mold-proof operations for air conditioners."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: GodaikinDataUpdateCoordinator,
    ) -> None:
        """Initialize the mold-proof manager."""
        self.hass = hass
        self.coordinator = coordinator
        self._active_states: dict[UniqueID, MoldProofState] = {}
        self._enabled_devices: set[UniqueID] = set()
        self._duration_minutes = 60
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    async def async_load(self) -> None:
        """Load enabled devices from storage."""
        data = await self._store.async_load()
        if data is not None:
            self._enabled_devices = set(data.get("enabled_devices", []))
            _LOGGER.debug(
                "Loaded %d enabled devices from storage", len(self._enabled_devices)
            )
        else:
            _LOGGER.debug("No mold-proof storage data found")

    async def _async_save(self) -> None:
        """Save enabled devices to storage."""
        data = {"enabled_devices": list(self._enabled_devices)}
        await self._store.async_save(data)
        _LOGGER.debug("Saved %d enabled devices to storage", len(self._enabled_devices))

    def set_duration(self, minutes: int) -> None:
        """Set the mold-proof duration in minutes."""
        self._duration_minutes = minutes
        _LOGGER.debug("Mold-proof duration set to %d minutes", minutes)

    async def set_enabled(self, unique_id: UniqueID, enabled: bool) -> None:
        """Enable or disable mold-proof for a specific device."""
        if enabled:
            self._enabled_devices.add(unique_id)
            _LOGGER.debug("Mold-proof enabled for %s", unique_id)
        else:
            self._enabled_devices.discard(unique_id)
            # Cancel any active mold-proof
            if unique_id in self._active_states:
                await self.cancel_mold_proof(unique_id)
            _LOGGER.debug("Mold-proof disabled for %s", unique_id)

        # Save to storage
        await self._async_save()

    def is_enabled(self, unique_id: UniqueID) -> bool:
        """Check if mold-proof is enabled for a device."""
        return unique_id in self._enabled_devices

    def is_active(self, unique_id: UniqueID) -> bool:
        """Check if mold-proof is currently active for a device."""
        return unique_id in self._active_states

    async def start_mold_proof(
        self,
        unique_id: UniqueID,
        previous_mode: AircondMode,
        previous_fan_speed: FanSpeed,
    ) -> None:
        """Start mold-proof operation for a device."""
        if not self.is_enabled(unique_id):
            _LOGGER.debug("Mold-proof not enabled for %s, skipping", unique_id)
            return

        # Cancel any existing mold-proof
        if unique_id in self._active_states:
            await self.cancel_mold_proof(unique_id)

        _LOGGER.info(
            "Starting mold-proof for %s (duration: %d minutes)",
            unique_id,
            self._duration_minutes,
        )

        # Set to fan mode with low speed
        try:
            await self.coordinator.api.set_mode(unique_id, mode=AircondMode.FAN_ONLY)
            await self.coordinator.api.set_fan_mode(unique_id, fan=FanSpeed.LOW)
        except Exception as err:
            _LOGGER.error("Failed to start mold-proof for %s: %s", unique_id, err)
            return

        # Create state tracking
        state = MoldProofState(
            unique_id=unique_id,
            start_time=datetime.now(),
            previous_mode=previous_mode,
            previous_fan_speed=previous_fan_speed,
        )

        # Schedule automatic turn off
        cancel_timer = async_call_later(
            self.hass,
            self._duration_minutes * 60,  # Convert to seconds
            self._finish_mold_proof,
        )
        state.cancel_timer = cancel_timer

        self._active_states[unique_id] = state
        _LOGGER.debug("Mold-proof state created for %s", unique_id)

    async def cancel_mold_proof(self, unique_id: UniqueID) -> None:
        """Cancel active mold-proof operation."""
        if unique_id not in self._active_states:
            return

        state = self._active_states.pop(unique_id)

        # Cancel the timer
        if state.cancel_timer:
            state.cancel_timer()

        _LOGGER.info("Mold-proof cancelled for %s", unique_id)

    @callback
    async def _finish_mold_proof(self, _now=None) -> None:
        """Finish mold-proof operation and turn off the AC."""
        # Find which device to finish (called by timer)
        for unique_id, state in list(self._active_states.items()):
            elapsed = datetime.now() - state.start_time
            if elapsed >= timedelta(minutes=self._duration_minutes):
                _LOGGER.info("Finishing mold-proof for %s", unique_id)

                try:
                    # Restore fan speed before turning off
                    await self.coordinator.api.set_fan_mode(
                        unique_id, fan=state.previous_fan_speed
                    )
                    await self.coordinator.api.turn_off(unique_id)
                    await self.coordinator.async_request_refresh()
                except Exception as err:
                    _LOGGER.error(
                        "Failed to turn off AC after mold-proof for %s: %s",
                        unique_id,
                        err,
                    )

                self._active_states.pop(unique_id, None)
                break

    async def interrupt_mold_proof(self, unique_id: UniqueID) -> tuple[bool, FanSpeed]:
        """Interrupt mold-proof and return if it was active and previous fan speed."""
        if unique_id not in self._active_states:
            return False, FanSpeed.AUTO

        state = self._active_states.pop(unique_id)

        # Cancel the timer
        if state.cancel_timer:
            state.cancel_timer()

        _LOGGER.info("Mold-proof interrupted for %s", unique_id)
        return True, state.previous_fan_speed

    def get_state(self, unique_id: UniqueID) -> MoldProofState | None:
        """Get the mold-proof state for a device."""
        return self._active_states.get(unique_id)

    def get_remaining_time(self, unique_id: UniqueID) -> int:
        """Get remaining mold-proof time in seconds."""
        if unique_id not in self._active_states:
            return 0

        state = self._active_states[unique_id]
        elapsed = datetime.now() - state.start_time
        total_seconds = self._duration_minutes * 60
        remaining = total_seconds - elapsed.total_seconds()

        return max(0, int(remaining))

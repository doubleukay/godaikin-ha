"""GO DAIKIN Data Update Coordinator."""

from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)

from .api import ApiClient
from .auth import AuthClient
from .const import OPTIMISTIC_TTL
from .energy import EnergyCounter
from .optimistic import OptimisticOverlay
from .types import Aircond, UniqueID

if TYPE_CHECKING:
    from .mold_proof import MoldProofManager

_LOGGER = logging.getLogger(__name__)


class GodaikinDataUpdateCoordinator(
    TimestampDataUpdateCoordinator[dict[UniqueID, Aircond]]
):
    """Class to manage fetching GO DAIKIN data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: ApiClient,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api_client
        self.energy = EnergyCounter()
        self.overlay = OptimisticOverlay(OPTIMISTIC_TTL)
        api_client.on_desired_sent = self.apply_optimistic
        self.mold_proof: MoldProofManager | None = None

        super().__init__(
            hass,
            _LOGGER,
            name="GO DAIKIN",
            update_interval=timedelta(seconds=7),  # matches GO DAIKIN Android app
            config_entry=config_entry,
        )

    async def _async_update_data(self) -> dict[UniqueID, Aircond]:
        """Fetch data from GO DAIKIN API."""
        try:
            airconds = await self.api.get_airconds()

            # Update energy for each aircond
            for aircond in airconds:
                self.energy.accumulate_energy_usage_for_aircond(aircond)

            # No await from here to the coordinator assigning the result, so a
            # command landing during the fetch is reconciled correctly
            now = time.monotonic()
            for aircond in airconds:
                self.overlay.apply(aircond, now)
            data = {aircond.unique_id: aircond for aircond in airconds}
            self.overlay.prune(data)
            return data
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    def apply_optimistic(self, unique_id: UniqueID, desired: dict) -> None:
        """Show a command that was just sent before the cloud reflects it.

        Never raises: callers treat an exception as a failed command.
        """
        try:
            now = time.monotonic()
            self.overlay.record(unique_id, desired, now)
            if self.data and unique_id in self.data:
                self.overlay.paint(self.data[unique_id])
        except Exception:
            _LOGGER.exception("Failed to apply optimistic state")
        self.notify_listeners()

    def notify_listeners(self) -> None:
        """Notify entities, isolating listener errors. Never raises."""
        try:
            self.async_update_listeners()
        except Exception:
            _LOGGER.exception("Listener failed during optimistic update")

    def get_energy_usage(self, unique_id: UniqueID) -> float:
        """Get energy usage for an air conditioner."""
        return self.energy.get_energy_usage(unique_id)

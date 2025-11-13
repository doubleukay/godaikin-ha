"""GO DAIKIN Data Update Coordinator."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)

from .api import ApiClient
from .auth import AuthClient
from .energy import EnergyCounter
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

            return {aircond.unique_id: aircond for aircond in airconds}
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    def get_energy_usage(self, unique_id: UniqueID) -> float:
        """Get energy usage for an air conditioner."""
        return self.energy.get_energy_usage(unique_id)

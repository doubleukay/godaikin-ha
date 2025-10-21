"""
Counts energy usage for airconds - uses Sta_ODPwrCon - quite similar results to GO DAIKIN energy data.
"""

from datetime import datetime as dt
import logging

from .types import *

_LOGGER = logging.getLogger(__name__)


class EnergyCounter:
    def __init__(self):
        self.energy_by_unique_id: dict[UniqueID, float] = {}
        self.energy_accumulated_at_by_unique_id: dict[UniqueID, dt] = {}

    def accumulate_energy_usage_for_aircond(self, aircond: Aircond) -> float:
        now = dt.now()
        accumulated_at = self.energy_accumulated_at_by_unique_id.get(aircond.unique_id)
        self.energy_accumulated_at_by_unique_id[aircond.unique_id] = now

        if not accumulated_at:
            # First accumulation
            return 0.0

        energy_at_last_accum = self.energy_by_unique_id.get(aircond.unique_id, 0.0)

        kilowatts = aircond.shadowState.Sta_ODPwrCon / 1000
        hours_passed_since_last_accum = (now - accumulated_at).total_seconds() / 3600
        energy_since_last_accum = kilowatts * hours_passed_since_last_accum

        energy_now = energy_at_last_accum + energy_since_last_accum

        self.energy_by_unique_id[aircond.unique_id] = energy_now

        return energy_now

    def get_energy_usage(self, unique_id: UniqueID) -> float:
        return self.energy_by_unique_id.get(unique_id, 0.0)

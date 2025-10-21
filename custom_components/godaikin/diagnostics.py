"""Diagnostics support for GO DAIKIN."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import GodaikinDataUpdateCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: GodaikinDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    diagnostics_data = {
        "entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "domain": entry.domain,
            "title": entry.title,
            "data": {
                "username": entry.data.get("username", "REDACTED"),
                "refresh_interval": entry.data.get("refresh_interval"),
            },
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_update_time": (
                coordinator.last_update_success_time.isoformat()
                if coordinator.last_update_success_time
                else None
            ),
            "update_interval": str(coordinator.update_interval),
        },
        "devices": [],
    }

    # Add air conditioner data
    for unique_id, aircond in coordinator.data.items():
        device_data = {
            "unique_id": unique_id,
            "group": aircond.ACGroup,
            "name": aircond.ACName,
            "ip_address": aircond.IP,
            "thing_name": aircond.ThingName,
            "thing_type": aircond.ThingType,
            "gateway_ip": aircond.gatewayIP,
            "group_index": aircond.groupIndex,
            "guest_paired": aircond.guestPaired,
            "manufacturer": aircond.manufacturer,
            "plan_expired_date": aircond.planExpiredDate,
            "plan_id": aircond.planID,
            "qx": aircond.qx,
            "shadow_state": aircond.shadowState.__dict__,
            "sub_start_date": aircond.subStartDate,
            "subnet_mask": aircond.subnetMask,
            "energy": {
                "accumulated_kwh": round(coordinator.get_energy_usage(unique_id), 3),
            },
        }
        diagnostics_data["devices"].append(device_data)

    return diagnostics_data

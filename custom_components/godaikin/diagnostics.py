"""Diagnostics support for GO DAIKIN."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import GodaikinDataUpdateCoordinator

REDACTED = "**REDACTED**"

TO_REDACT_ENTRY = {"username", "title"}
TO_REDACT_DEVICE = {
    "unique_id",
    "thing_name",
    "ip_address",
    "gateway_ip",
    "subnet_mask",
    "plan_id",
    "plan_expired_date",
    "sub_start_date",
}
TO_REDACT_SHADOW = {"key", "thingName", "ip", "port"}


def _scrub(value: Any, needles: list[str]) -> Any:
    """Replace any string containing a sensitive needle (case-insensitive)."""
    if isinstance(value, dict):
        return {k: _scrub(v, needles) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v, needles) for v in value]
    if isinstance(value, str):
        lowered = value.lower()
        if any(n in lowered for n in needles):
            return REDACTED
    return value


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
                "username": entry.data.get("username"),
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
    sensitive: set[str] = set()
    username = entry.data.get("username")
    if username:
        sensitive.add(str(username))
    pending = coordinator.overlay.snapshot(time.monotonic())
    for index, (unique_id, aircond) in enumerate(coordinator.data.items()):
        for ident in (
            unique_id,
            aircond.ThingName,
            aircond.thingName,
            aircond.shadowState.thingName,
            aircond.shadowState.key,
        ):
            if ident:
                sensitive.add(str(ident))
                # Bare "Daikin_<hex>=AC" style names: also catch the hex/MAC part.
                bare = str(ident).split("=")[0]
                if bare:
                    sensitive.add(bare)
                    sensitive.add(bare[-12:])
        device_data = {
            "device_index": index,
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
            "shadow_state": async_redact_data(
                dict(aircond.shadowState.__dict__), TO_REDACT_SHADOW
            ),
            "sub_start_date": aircond.subStartDate,
            "subnet_mask": aircond.subnetMask,
            "pending_optimistic": pending.get(unique_id, {}),
            "energy": {
                "accumulated_kwh": round(coordinator.get_energy_usage(unique_id), 3),
            },
        }
        diagnostics_data["devices"].append(
            async_redact_data(device_data, TO_REDACT_DEVICE)
        )

    diagnostics_data["entry"] = async_redact_data(
        diagnostics_data["entry"], TO_REDACT_ENTRY
    )
    # Belt and braces: no string may contain a raw identifier.
    needles = sorted({n.lower() for n in sensitive if len(n) >= 6}, key=len)
    return _scrub(diagnostics_data, needles)

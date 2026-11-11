"""Tests for diagnostics redaction."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.godaikin.const import DOMAIN
from custom_components.godaikin.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.godaikin.types import Aircond, ShadowState

pytestmark = pytest.mark.asyncio

USERNAME = "user@example.com"
KEY_A = "0123456789abcdef0123456789abcdef"
KEY_B = "fedcba9876543210fedcba9876543210"


def _aircond(mac: str, name: str, key: str, ip: str) -> Aircond:
    thing = f"Daikin_{mac}"
    return Aircond(
        ACGroup="All Units",
        ACName=name,
        IP=ip,
        ThingName=thing,
        ThingType="AC",
        gatewayIP="192.168.1.1",
        groupIndex=-1,
        guestPaired=0,
        manufacturer="Realtek",
        planExpiredDate="2027-01-04",
        planID="2",
        qx="15",
        subStartDate="2024-01-04 10:11:12",
        subnetMask="255.255.255.0",
        thingName=f"{thing}=AC",
        shadowState=ShadowState(
            Set_UDLvr=15,
            Set_Mode=2,
            version="1.2.3",
            key=key,
            thingName=thing,
            ip=ip,
            port="1883",
        ),
    )


async def test_diagnostics_redacts_identifiers():
    a = _aircond("aabbccddeeff", "bedroom", KEY_A, "192.168.1.50")
    b = _aircond("112233445566", "office", KEY_B, "192.168.1.51")
    coordinator = MagicMock()
    coordinator.data = {a.unique_id: a, b.unique_id: b}
    coordinator.last_update_success = True
    coordinator.overlay.snapshot.return_value = {}
    coordinator.last_update_success_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    coordinator.update_interval = "0:00:30"
    coordinator.get_energy_usage.return_value = 1.2345
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.version = 1
    entry.domain = DOMAIN
    entry.title = f"GO DAIKIN ({USERNAME})"
    entry.data = {"username": USERNAME, "password": "pw", "refresh_interval": 30}
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry1": coordinator}}

    out = await async_get_config_entry_diagnostics(hass, entry)
    dumped = json.dumps(out).lower()

    for secret in (
        USERNAME,
        "daikin_aabbccddeeff",
        "daikin_112233445566",
        "aabbccddeeff",
        "112233445566",
        "aa:bb:cc",
        KEY_A,
        KEY_B,
        "192.168.1.50",
        "192.168.1.51",
        "192.168.1.1",
        "255.255.255.0",
        "2027-01-04",
        "=ac",
    ):
        assert secret.lower() not in dumped, secret
    assert "password" not in dumped

    assert [d["name"] for d in out["devices"]] == ["bedroom", "office"]
    assert [d["device_index"] for d in out["devices"]] == [0, 1]
    shadow = out["devices"][0]["shadow_state"]
    assert shadow["Set_UDLvr"] == 15
    assert shadow["Set_Mode"] == 2
    assert shadow["version"] == "1.2.3"
    assert shadow["key"] == "**REDACTED**"
    assert out["devices"][0]["group"] == "All Units"
    assert out["entry"]["data"]["username"] == "**REDACTED**"
    assert out["entry"]["data"]["refresh_interval"] == 30

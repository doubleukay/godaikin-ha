"""Tests for tolerance of unknown device enum values (issue #12)."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, call

import pytest

from homeassistant.components.climate import HVACMode

from custom_components.godaikin import climate as climate_mod
from custom_components.godaikin.climate import GodaikinClimate
from custom_components.godaikin.types import AircondMode, FanSpeed

from .conftest import UID_A

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clear_warned():
    climate_mod._WARNED_UNKNOWN.clear()
    yield
    climate_mod._WARNED_UNKNOWN.clear()


@pytest.fixture
def entity(manager, coordinator, timers):
    ent = GodaikinClimate(coordinator, UID_A)
    ent.async_write_ha_state = MagicMock()
    aircond = coordinator.data[UID_A]
    aircond.is_on = True
    aircond.shadowState.Set_Mode = int(AircondMode.COOL)
    aircond.shadowState.Set_Fan = int(FanSpeed.AUTO)
    return ent


def _warnings(caplog):
    return [r for r in caplog.records if r.levelno == logging.WARNING]


async def test_unknown_swing_ud_is_none_and_warns_once(entity, coordinator, caplog):
    coordinator.data[UID_A].shadowState.Set_UDLvr = 10
    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            assert entity.swing_mode is None
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    assert UID_A in msg and "Set_UDLvr" in msg and "10" in msg


async def test_unknown_swing_lr_is_none(entity, coordinator):
    state = coordinator.data[UID_A].shadowState
    state.Ena_LRSwing = 1
    state.Set_LRLvr = 10
    assert entity.swing_horizontal_mode is None


async def test_unknown_fan_is_none(entity, coordinator):
    coordinator.data[UID_A].shadowState.Set_Fan = 99
    assert entity.fan_mode is None


async def test_unknown_mode_hvac_mode_does_not_raise(entity, coordinator):
    coordinator.data[UID_A].shadowState.Set_Mode = 99
    assert entity.hvac_mode == HVACMode.OFF


async def test_set_off_with_unknown_mode_turns_off(entity, coordinator):
    coordinator.data[UID_A].shadowState.Set_Mode = 99
    await entity.async_set_hvac_mode(HVACMode.OFF)
    coordinator.api.turn_off.assert_awaited_once_with(UID_A)


async def test_set_off_with_unknown_fan_turns_off(entity, coordinator):
    coordinator.data[UID_A].shadowState.Set_Fan = 99
    await entity.async_set_hvac_mode(HVACMode.OFF)
    coordinator.api.turn_off.assert_awaited_once_with(UID_A)


async def test_known_values_still_map(entity, coordinator):
    state = coordinator.data[UID_A].shadowState
    assert entity.hvac_mode == HVACMode.COOL
    assert entity.fan_mode == FanSpeed.AUTO.name.lower()
    state.Set_UDLvr = 0
    from custom_components.godaikin.types import AircondSwing

    assert entity.swing_mode == AircondSwing(0).name.title()

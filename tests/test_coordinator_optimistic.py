"""Tests for the coordinator's optimistic handling."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.godaikin.coordinator import GodaikinDataUpdateCoordinator
from custom_components.godaikin.types import Aircond, ShadowState

pytestmark = pytest.mark.asyncio


def _aircond(name="t1", **shadow) -> Aircond:
    ac = Aircond(shadowState=ShadowState(**shadow))
    ac.ThingName = name
    return ac


@pytest.fixture
def api():
    client = MagicMock()
    client.get_airconds = AsyncMock(return_value=[])
    return client


@pytest.fixture
def coord(api):
    return GodaikinDataUpdateCoordinator(MagicMock(), api, MagicMock())


async def test_hook_is_wired(coord, api):
    assert api.on_desired_sent == coord.apply_optimistic


async def test_apply_optimistic_unknown_uid_and_no_data(coord):
    coord.data = None
    coord.apply_optimistic("nope", {"Set_Mode": 1})
    coord.data = {}
    coord.apply_optimistic("nope", {"Set_Mode": 1})


async def test_apply_optimistic_raising_listener(coord):
    ac = _aircond(Set_Mode=2)
    coord.data = {ac.unique_id: ac}
    coord.async_add_listener(MagicMock(side_effect=RuntimeError("boom")))

    coord.apply_optimistic(ac.unique_id, {"Set_Mode": 1})  # no exception

    assert ac.shadowState.Set_Mode == 1


async def test_apply_optimistic_updates_data_and_notifies(coord):
    ac = _aircond(Set_Mode=2)
    coord.data = {ac.unique_id: ac}
    listener = MagicMock()
    coord.async_add_listener(listener)

    coord.apply_optimistic(ac.unique_id, {"Set_Mode": 1})

    assert ac.shadowState.Set_Mode == 1
    listener.assert_called_once()


async def test_command_during_fetch_is_overlaid(coord, api):
    ac = _aircond(Set_Mode=2)
    uid = ac.unique_id

    async def slow_fetch():
        # command lands while the poll is awaiting the cloud
        coord.apply_optimistic(uid, {"Set_Mode": 1})
        return [_aircond(Set_Mode=2)]  # stale cloud answer

    api.get_airconds.side_effect = slow_fetch

    data = await coord._async_update_data()

    assert data[uid].shadowState.Set_Mode == 1


async def test_failed_poll_keeps_pending(coord, api):
    ac = _aircond(Set_Mode=2)
    uid = ac.unique_id
    coord.apply_optimistic(uid, {"Set_Mode": 1})
    api.get_airconds.side_effect = RuntimeError("down")

    with pytest.raises(UpdateFailed):
        await coord._async_update_data()

    assert "Set_Mode" in coord.overlay.snapshot(time.monotonic())[uid]


async def test_confirmed_value_is_dropped_on_poll(coord, api):
    ac = _aircond(Set_Mode=1)
    coord.apply_optimistic(ac.unique_id, {"Set_Mode": 1})
    api.get_airconds.return_value = [ac]

    await coord._async_update_data()

    assert coord.overlay.snapshot(0) == {}


async def test_sequential_commands_stay_pending_through_stale_poll(coord, api):
    uid = _aircond().unique_id
    api.get_airconds.side_effect = lambda: [
        _aircond(Set_Mode=2, Set_Temp=24, Set_Fan=3)
    ]
    coord.data = await coord._async_update_data()

    coord.apply_optimistic(uid, {"Set_Temp": 22})
    coord.apply_optimistic(uid, {"Set_Fan": 5})
    coord.apply_optimistic(uid, {"Set_Mode": 1})

    snap = coord.overlay.snapshot(time.monotonic())[uid]
    assert set(snap) == {"Set_Temp", "Set_Fan", "Set_Mode"}
    shadow = coord.data[uid].shadowState
    assert (shadow.Set_Temp, shadow.Set_Fan, shadow.Set_Mode) == (22, 5, 1)

    coord.data = await coord._async_update_data()  # cloud still stale

    shadow = coord.data[uid].shadowState
    assert (shadow.Set_Temp, shadow.Set_Fan, shadow.Set_Mode) == (22, 5, 1)
    assert set(coord.overlay.snapshot(time.monotonic())[uid]) == {
        "Set_Temp",
        "Set_Fan",
        "Set_Mode",
    }


async def test_command_after_poll_painted_key_keeps_it_pending(coord, api):
    uid = _aircond().unique_id
    api.get_airconds.side_effect = lambda: [_aircond(Set_Mode=2, Set_Temp=24)]
    coord.data = await coord._async_update_data()
    coord.apply_optimistic(uid, {"Set_Temp": 22})
    coord.data = await coord._async_update_data()  # poll paints Set_Temp

    coord.apply_optimistic(uid, {"Set_Mode": 1})
    coord.data = await coord._async_update_data()

    shadow = coord.data[uid].shadowState
    assert (shadow.Set_Temp, shadow.Set_Mode) == (22, 1)


async def test_mode_and_temperature_survive_stale_poll(coord, api):
    """set_temperature(hvac_mode=cool, temperature=22): set_mode then set_temp."""
    uid = _aircond().unique_id
    api.get_airconds.side_effect = lambda: [
        _aircond(Set_OnOff=0, Set_Mode=2, Set_Temp=24)
    ]
    coord.data = await coord._async_update_data()

    coord.apply_optimistic(uid, {"Set_OnOff": 1, "Set_Mode": 1})
    coord.apply_optimistic(uid, {"Set_Temp": 22})
    coord.data = await coord._async_update_data()

    shadow = coord.data[uid].shadowState
    assert (shadow.Set_OnOff, shadow.Set_Mode, shadow.Set_Temp) == (1, 1, 22)
    assert set(coord.overlay.snapshot(time.monotonic())[uid]) == {
        "Set_OnOff",
        "Set_Mode",
        "Set_Temp",
    }


async def test_gone_device_is_pruned(coord, api):
    coord.apply_optimistic("gone", {"Set_Mode": 1})
    api.get_airconds.return_value = [_aircond()]

    await coord._async_update_data()

    assert coord.overlay.snapshot(0) == {}


async def test_energy_accumulates_once_per_poll(coord, api):
    ac = _aircond(Set_Mode=2)
    coord.apply_optimistic(ac.unique_id, {"Set_Mode": 1})
    coord.energy = MagicMock()
    api.get_airconds.return_value = [ac]

    await coord._async_update_data()

    coord.energy.accumulate_energy_usage_for_aircond.assert_called_once_with(ac)

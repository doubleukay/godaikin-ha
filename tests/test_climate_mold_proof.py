"""Tests for GodaikinClimate behaviour during a mold-proof cycle."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, call

import pytest

from homeassistant.components.climate import HVACMode

from custom_components.godaikin.climate import GodaikinClimate
from custom_components.godaikin.types import AircondMode, FanSpeed

from custom_components.godaikin.mold_proof import FINISH_RETRY_SECONDS

from .conftest import PREV_FAN, PREV_MODE, UID_A

pytestmark = pytest.mark.asyncio


@pytest.fixture
def entity(manager, coordinator, timers):
    ent = GodaikinClimate(coordinator, UID_A)
    ent.async_write_ha_state = MagicMock()
    aircond = coordinator.data[UID_A]
    aircond.is_on = True
    aircond.shadowState.Set_Mode = int(PREV_MODE)
    aircond.shadowState.Set_Fan = int(PREV_FAN)
    return ent


async def _start(manager, coordinator):
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)
    coordinator.api.reset_mock()


async def test_turn_on_restores_mode_and_fan(entity, manager, coordinator, timers):
    await _start(manager, coordinator)

    await entity.async_turn_on()

    assert coordinator.api.mock_calls == [
        call.set_state(UID_A, on=True, mode=PREV_MODE, fan=PREV_FAN),
    ]
    timers[0][2].assert_called_once()
    assert not manager.is_active(UID_A)
    coordinator.async_request_refresh.assert_awaited()


async def test_turn_on_without_mold_proof_is_plain(entity, coordinator):
    await entity.async_turn_on()

    assert coordinator.api.mock_calls == [call.turn_on(UID_A)]


async def test_set_hvac_mode_dry_restores_fan(entity, manager, coordinator, timers):
    await _start(manager, coordinator)

    await entity.async_set_hvac_mode(HVACMode.DRY)

    assert coordinator.api.mock_calls == [
        call.set_state(UID_A, on=True, mode=AircondMode.DRY, fan=PREV_FAN),
    ]
    timers[0][2].assert_called_once()
    assert not manager.is_active(UID_A)


async def test_set_hvac_mode_off_restores_then_turns_off(
    entity, manager, coordinator, timers
):
    await _start(manager, coordinator)

    await entity.async_set_hvac_mode(HVACMode.OFF)

    assert coordinator.api.mock_calls == [
        call.set_state(UID_A, on=False, mode=PREV_MODE, fan=PREV_FAN),
    ]
    assert not manager.is_active(UID_A)
    assert len(timers) == 1  # no new cycle


async def test_set_hvac_mode_off_normally_starts_cycle(
    entity, manager, coordinator, timers
):
    await entity.async_set_hvac_mode(HVACMode.OFF)

    assert manager.is_active(UID_A)
    assert call.turn_off(UID_A) not in coordinator.api.mock_calls


async def test_set_temperature_with_hvac_mode_interrupts(
    entity, manager, coordinator, timers
):
    await _start(manager, coordinator)

    await entity.async_set_temperature(hvac_mode=HVACMode.COOL, temperature=24)

    assert coordinator.api.mock_calls == [
        call.set_state(UID_A, on=True, mode=AircondMode.COOL, fan=PREV_FAN),
        call.set_temperature(UID_A, temperature=24),
    ]
    assert not manager.is_active(UID_A)


async def test_set_fan_mode_during_mold_proof_updates_saved_state(
    entity, manager, coordinator, store, timers
):
    await _start(manager, coordinator)

    await entity.async_set_fan_mode("medium")

    assert coordinator.api.mock_calls == []
    assert manager.get_state(UID_A).previous_fan_speed == FanSpeed.MEDIUM
    assert store.saved[-1]["active"][UID_A]["previous_fan_speed"] == int(
        FanSpeed.MEDIUM
    )

    # ...and it is applied when the user turns the AC on
    await entity.async_turn_on()
    assert coordinator.api.mock_calls == [
        call.set_state(UID_A, on=True, mode=PREV_MODE, fan=FanSpeed.MEDIUM)
    ]


async def test_set_fan_mode_without_mold_proof_hits_device(entity, coordinator):
    await entity.async_set_fan_mode("low")

    assert coordinator.api.mock_calls == [call.set_fan_mode(UID_A, fan=FanSpeed.LOW)]


async def test_set_hvac_mode_cool_restores_fan(entity, manager, coordinator, timers):
    await _start(manager, coordinator)

    await entity.async_set_hvac_mode(HVACMode.COOL)

    assert coordinator.api.mock_calls == [
        call.set_state(UID_A, on=True, mode=AircondMode.COOL, fan=PREV_FAN),
    ]


async def test_off_restores_and_ends_cycle_when_start_fails(
    entity, manager, coordinator, store, timers
):
    """Start may have applied despite the error: restore-and-off that cycle."""
    coordinator.api.set_state.side_effect = [RuntimeError("boom"), None]
    await entity.async_set_hvac_mode(HVACMode.OFF)

    assert not manager.is_active(UID_A)
    assert store.data["active"] == {}
    assert coordinator.api.mock_calls == [
        call.set_state(UID_A, on=True, mode=AircondMode.FAN_ONLY, fan=FanSpeed.LOW),
        call.set_state(UID_A, on=False, mode=PREV_MODE, fan=PREV_FAN),
    ]


async def test_off_keeps_cycle_and_reschedules_when_start_and_fallback_fail(
    entity, manager, coordinator, store, timers
):
    coordinator.api.set_state.side_effect = RuntimeError("down")

    with pytest.raises(RuntimeError):
        await entity.async_set_hvac_mode(HVACMode.OFF)

    assert manager.is_active(UID_A)
    assert UID_A in store.data["active"]
    assert timers[-1][0] == FINISH_RETRY_SECONDS
    assert timers[-1][1].args == (UID_A, manager.get_state(UID_A).token)


async def test_turn_on_during_inflight_finish_is_not_overridden(
    entity, manager, coordinator, timers
):
    """F3: the user's turn_on waits for the finish, then wins."""
    await _start(manager, coordinator)
    gate = asyncio.Event()
    orig = coordinator.api.set_state.side_effect

    async def slow_fan(*a, **k):
        await gate.wait()

    coordinator.api.set_state.side_effect = slow_fan
    finish = asyncio.ensure_future(timers[0][1](None))
    await asyncio.sleep(0)  # finish blocked inside set_state
    coordinator.api.set_state.side_effect = orig
    turn_on = asyncio.ensure_future(entity.async_turn_on())
    await asyncio.sleep(0)
    assert not turn_on.done()

    gate.set()
    await finish
    await turn_on

    assert coordinator.api.mock_calls == [
        call.set_state(UID_A, on=False, mode=PREV_MODE, fan=PREV_FAN),  # the finish
        call.turn_on(UID_A),  # the user's turn_on comes last and wins
    ]


async def test_set_temperature_does_not_deadlock_on_lock(entity, manager, coordinator):
    await asyncio.wait_for(
        entity.async_set_temperature(hvac_mode=HVACMode.COOL, temperature=22), 1
    )

    assert call.set_temperature(UID_A, temperature=22) in coordinator.api.mock_calls


async def test_turn_on_failure_keeps_cycle(entity, manager, coordinator, store, timers):
    await _start(manager, coordinator)
    coordinator.api.set_state.side_effect = RuntimeError("cloud")

    with pytest.raises(RuntimeError):
        await entity.async_turn_on()

    assert manager.is_active(UID_A)
    assert UID_A in store.data["active"]
    timers[0][2].assert_not_called()


async def test_off_failure_keeps_cycle(entity, manager, coordinator, store, timers):
    await _start(manager, coordinator)
    coordinator.api.set_state.side_effect = RuntimeError("cloud")

    with pytest.raises(RuntimeError):
        await entity.async_set_hvac_mode(HVACMode.OFF)

    # Cycle (and its persisted entry) is kept, but its finish is brought forward
    assert manager.is_active(UID_A)
    assert UID_A in store.data["active"]
    timers[0][2].assert_called_once()
    assert timers[-1][0] == FINISH_RETRY_SECONDS
    assert timers[-1][1].args == (UID_A, manager.get_state(UID_A).token)


async def test_off_retry_via_rescheduled_timer_succeeds(
    entity, manager, coordinator, timers
):
    await _start(manager, coordinator)
    coordinator.api.set_state.side_effect = RuntimeError("timeout")

    with pytest.raises(RuntimeError):
        await entity.async_set_hvac_mode(HVACMode.OFF)

    assert entity.hvac_mode == HVACMode.OFF
    assert manager.get_remaining_time(UID_A) > 600  # original end_time unchanged
    assert timers[-1][0] == FINISH_RETRY_SECONDS  # but the finish runs soon
    coordinator.api.set_state.side_effect = None
    coordinator.api.reset_mock()
    await timers[-1][1](None)
    assert coordinator.api.mock_calls == [
        call.set_state(UID_A, on=False, mode=PREV_MODE, fan=PREV_FAN)
    ]
    assert not manager.is_active(UID_A)


async def test_mode_change_failure_keeps_cycle(
    entity, manager, coordinator, store, timers
):
    await _start(manager, coordinator)
    coordinator.api.set_state.side_effect = RuntimeError("cloud")

    with pytest.raises(RuntimeError):
        await entity.async_set_hvac_mode(HVACMode.COOL)

    assert manager.is_active(UID_A)
    assert UID_A in store.data["active"]


async def test_mold_proof_restores_use_single_request(entity, manager, coordinator):
    """F7: each restore is one atomic request, never mode/fan/power separately."""
    for action in (
        lambda: entity.async_turn_on(),
        lambda: entity.async_set_hvac_mode(HVACMode.COOL),
        lambda: entity.async_set_hvac_mode(HVACMode.OFF),
    ):
        await _start(manager, coordinator)
        await action()
        assert len(coordinator.api.mock_calls) == 1
        assert coordinator.api.mock_calls[0][0] == "set_state"
        assert not manager.is_active(UID_A)


async def test_set_temperature_failure_keeps_cycle(
    entity, manager, coordinator, store, timers
):
    await _start(manager, coordinator)
    coordinator.api.set_state.side_effect = RuntimeError("cloud")

    with pytest.raises(RuntimeError):
        await entity.async_set_temperature(hvac_mode=HVACMode.COOL, temperature=24)

    assert manager.is_active(UID_A)
    coordinator.api.set_temperature.assert_not_called()


async def test_queued_old_timer_does_not_finish_new_cycle(
    entity, manager, coordinator, timers
):
    """C2: with the lock held, turn_on, turn_off and the old timer queue up."""
    await _start(manager, coordinator)
    old_timer = timers[0][1]
    old_token = manager.get_state(UID_A).token

    await manager.device_lock(UID_A).acquire()
    turn_on = asyncio.ensure_future(entity.async_turn_on())
    await asyncio.sleep(0)
    entity.coordinator.data[UID_A].is_on = True
    turn_off = asyncio.ensure_future(entity.async_turn_off())
    await asyncio.sleep(0)
    stale = asyncio.ensure_future(old_timer(None))
    await asyncio.sleep(0)
    coordinator.api.reset_mock()
    manager.device_lock(UID_A).release()
    await asyncio.gather(turn_on, turn_off, stale)

    state = manager.get_state(UID_A)
    assert state is not None and state.token != old_token
    assert call.turn_off(UID_A) not in coordinator.api.mock_calls

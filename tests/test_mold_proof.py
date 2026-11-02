"""Tests for MoldProofManager."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from functools import partial
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from homeassistant.util import dt as dt_util

from custom_components.godaikin.mold_proof import (
    FINISH_RETRY_SECONDS,
    MAX_FINISH_RETRY_SECONDS,
    finish_retry_delay,
    MoldProofManager,
)
from custom_components.godaikin.types import AircondMode, FanSpeed

from .conftest import ENTRY_ID, PREV_FAN, PREV_MODE, UID_A, UID_B

pytestmark = pytest.mark.asyncio


async def test_start_registers_state_before_api_calls(manager, coordinator, timers):
    seen = {}

    async def check(*args, **kwargs):
        seen["active"] = manager.is_active(UID_A)
        seen["timers"] = len(timers)

    coordinator.api.set_state.side_effect = check

    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)

    assert seen == {"active": True, "timers": 1}
    assert coordinator.api.mock_calls == [
        call.set_state(UID_A, on=True, mode=AircondMode.FAN_ONLY, fan=FanSpeed.LOW),
    ]
    assert manager.is_active(UID_A)
    assert timers[0][0] == 60 * 60


async def test_start_api_failure_keeps_cycle(manager, coordinator, timers, store):
    coordinator.api.set_state.side_effect = RuntimeError("boom")

    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)

    # The request may have been applied despite the error: the cycle is kept
    assert manager.is_active(UID_A)
    timers[0][2].assert_not_called()
    assert UID_A in store.data["active"]


async def test_interrupt_returns_state_and_cancels_timer(manager, timers, store):
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)

    state = await manager.interrupt_mold_proof(UID_A)

    assert state.previous_mode == PREV_MODE
    assert state.previous_fan_speed == PREV_FAN
    assert not manager.is_active(UID_A)
    timers[0][2].assert_called_once()
    assert store.saved[-1]["active"] == {}
    assert await manager.interrupt_mold_proof(UID_A) is None


async def test_finish_only_touches_its_own_device(manager, coordinator, timers):
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)
    await manager.start_mold_proof(UID_B, AircondMode.DRY, FanSpeed.AUTO)
    coordinator.api.reset_mock()

    action_a = timers[0][1]
    assert isinstance(action_a, partial)
    await action_a(None)

    assert coordinator.api.mock_calls == [
        call.set_state(UID_A, on=False, mode=PREV_MODE, fan=PREV_FAN),
    ]
    assert not manager.is_active(UID_A)
    assert manager.is_active(UID_B)
    timers[1][2].assert_not_called()

    # A second firing for a device that is gone is a no-op
    coordinator.api.reset_mock()
    await action_a(None)
    assert coordinator.api.mock_calls == []


async def test_persist_format_and_backward_compat(manager, store):
    await manager.set_enabled(UID_A, True)
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)

    saved = store.saved[-1]
    assert UID_A in saved["enabled_devices"]
    entry = saved["active"][UID_A]
    assert entry["previous_mode"] == int(PREV_MODE)
    assert entry["previous_fan_speed"] == int(PREV_FAN)
    assert dt_util.parse_datetime(entry["end_time"]) is not None

    # Old storage without "active" loads fine
    store.data = {"enabled_devices": [UID_B]}
    fresh = MoldProofManager(manager.hass, manager.coordinator, manager._entry)
    await fresh.async_load()
    assert fresh.is_enabled(UID_B)
    assert not fresh.is_active(UID_B)


async def test_load_future_end_time_rearms_timer(manager, store, timers):
    end = dt_util.utcnow() + timedelta(minutes=10)
    store.data = {
        "enabled_devices": [UID_A],
        "active": {
            UID_A: {
                "end_time": end.isoformat(),
                "previous_mode": int(PREV_MODE),
                "previous_fan_speed": int(PREV_FAN),
            }
        },
    }

    await manager.async_load()

    assert manager.is_active(UID_A)
    assert len(timers) == 1
    delay, action, _ = timers[0]
    assert 590 <= delay <= 600
    assert action.func == manager._finish_mold_proof and action.args[0] == UID_A
    assert 0 < manager.get_remaining_time(UID_A) <= 600


async def test_load_past_end_time_finishes(manager, coordinator, store, timers):
    end = dt_util.utcnow() - timedelta(minutes=1)
    store.data = {
        "active": {
            UID_A: {
                "end_time": end.isoformat(),
                "previous_mode": int(PREV_MODE),
                "previous_fan_speed": int(PREV_FAN),
            }
        },
    }

    await manager.async_load()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert coordinator.api.mock_calls == [
        call.set_state(UID_A, on=False, mode=PREV_MODE, fan=PREV_FAN),
    ]
    assert not manager.is_active(UID_A)
    assert timers == []
    assert store.saved[-1]["active"] == {}


async def test_load_drops_corrupt_and_unknown(manager, coordinator, store, timers):
    coordinator.data["bad"] = (
        object()
    )  # known device with a non-dict entry (TypeError path)
    end = (dt_util.utcnow() + timedelta(minutes=5)).isoformat()
    store.data = {
        "active": {
            UID_A: {"end_time": end, "previous_mode": 99, "previous_fan_speed": 2},
            UID_B: {"end_time": "garbage", "previous_mode": 1, "previous_fan_speed": 2},
            "bad": "not-a-dict",
            "gone": {"end_time": end, "previous_mode": 1, "previous_fan_speed": 2},
        },
    }

    await manager.async_load()

    assert manager._active_states == {}
    assert timers == []
    assert store.saved[-1]["active"] == {}


async def test_unload_cancels_timers_but_keeps_persisted(manager, store, timers):
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)
    persisted = store.data["active"]
    saves = len(store.saved)

    manager.async_unload()

    timers[0][2].assert_called_once()
    assert not manager.is_active(UID_A)
    assert len(store.saved) == saves
    assert store.data["active"] == persisted
    assert UID_A in persisted


def _entry(end):
    return {
        "end_time": end.isoformat(),
        "previous_mode": int(PREV_MODE),
        "previous_fan_speed": int(PREV_FAN),
    }


async def test_load_expired_before_live_keeps_live_persisted(manager, store, timers):
    """F1: eager finish tasks must not persist a partial view of the cycles."""
    now = dt_util.utcnow()
    store.data = {
        "enabled_devices": [UID_A, UID_B],
        "active": {
            UID_A: _entry(now - timedelta(minutes=1)),
            UID_B: _entry(now + timedelta(minutes=30)),
        },
    }

    await manager.async_load()
    for _ in range(5):
        await asyncio.sleep(0)

    assert manager.is_active(UID_B)
    assert not manager.is_active(UID_A)
    assert set(store.data["active"]) == {UID_B}
    assert all(UID_B in saved["active"] for saved in store.saved)


async def test_load_non_dict_active_is_ignored(manager, store):
    store.data = {"enabled_devices": [UID_A], "active": ["oops"]}

    await manager.async_load()

    assert manager.is_enabled(UID_A)
    assert manager._active_states == {}
    assert store.data["active"] == {}


async def test_finish_failure_keeps_state_and_retries(
    manager, coordinator, store, timers
):
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)
    coordinator.api.set_state.side_effect = RuntimeError("cloud down")
    action = timers[0][1]

    await action(None)

    assert manager.is_active(UID_A)
    assert UID_A in store.data["active"]
    assert len(timers) == 2 and timers[1][0] == FINISH_RETRY_SECONDS

    # Retry succeeds
    coordinator.api.set_state.side_effect = None
    coordinator.api.reset_mock()
    await timers[1][1](None)

    assert not manager.is_active(UID_A)
    assert store.data["active"] == {}
    assert (
        call.set_state(UID_A, on=False, mode=PREV_MODE, fan=PREV_FAN)
        in coordinator.api.mock_calls
    )


async def test_finish_retries_back_off_without_limit(
    manager, coordinator, store, timers
):
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)
    coordinator.api.set_state.side_effect = RuntimeError("down")

    # Drive each retry through the timer callback that was actually armed
    for i in range(7):
        await timers[i][1](None)

    delays = [t[0] for t in timers[1:]]
    assert delays == [180, 360, 720, 1440, 1800, 1800, 1800]
    assert delays == [finish_retry_delay(n) for n in range(1, 8)]
    assert max(delays) == MAX_FINISH_RETRY_SECONDS
    assert manager.get_state(UID_A).cancel_timer is timers[-1][2]
    assert UID_A in store.data["active"]

    # The device comes back: the next retry restores and turns off
    coordinator.api.set_state.side_effect = None
    await timers[-1][1](None)
    assert not manager.is_active(UID_A)
    assert store.data["active"] == {}


async def test_state_not_hidden_while_retrying(manager, coordinator, timers):
    """N1: after many failures a retry is still armed."""
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)
    coordinator.api.set_state.side_effect = RuntimeError("cloud down")
    for i in range(10):
        await timers[i][1](None)

    assert manager.get_state(UID_A).cancel_timer is timers[-1][2]
    assert len(timers) == 11


async def test_set_enabled_false_mid_cycle_finishes(manager, coordinator, store):
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)
    coordinator.api.reset_mock()

    await manager.set_enabled(UID_A, False)

    assert coordinator.api.mock_calls == [
        call.set_state(UID_A, on=False, mode=PREV_MODE, fan=PREV_FAN),
    ]
    assert not manager.is_active(UID_A)
    assert UID_A not in store.data["enabled_devices"]
    assert store.data["active"] == {}


async def test_unload_flag_disables_saves_finishes_and_retries(
    manager, coordinator, store, timers
):
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)
    saves = len(store.saved)
    coordinator.api.reset_mock()

    manager.async_unload()
    await manager._finish_mold_proof(UID_A)
    await manager.set_enabled(UID_B, False)
    await manager.async_persist()

    assert coordinator.api.mock_calls == []
    assert len(store.saved) == saves
    assert UID_A in store.data["active"]


async def test_unload_during_failing_finish_does_not_retry(
    manager, coordinator, store, timers
):
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)
    gate = asyncio.Event()

    async def slow_fail(*a, **k):
        await gate.wait()
        raise RuntimeError("session closed")

    coordinator.api.set_state.side_effect = slow_fail
    finish = asyncio.ensure_future(timers[0][1](None))
    await asyncio.sleep(0)
    manager.async_unload()
    gate.set()
    await finish

    assert len(timers) == 1
    assert UID_A in store.data["active"]


async def test_start_race_with_interrupt_is_serialised(manager, coordinator, timers):
    """Codex #1: an interrupt must wait for an in-flight start."""
    gate = asyncio.Event()

    async def slow_mode(*a, **k):
        await gate.wait()

    coordinator.api.set_state.side_effect = slow_mode
    start = asyncio.ensure_future(manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN))
    await asyncio.sleep(0)

    async def interrupt():
        async with manager.device_lock(UID_A):
            return await manager.interrupt_mold_proof(UID_A)

    interrupter = asyncio.ensure_future(interrupt())
    await asyncio.sleep(0)
    assert not interrupter.done()  # blocked behind start

    gate.set()
    assert await start is True
    state = await interrupter
    assert state is not None and state.previous_mode == PREV_MODE
    # start's FAN_ONLY/LOW calls both completed before the interrupt ran
    assert coordinator.api.mock_calls[-1] == call.set_state(
        UID_A, on=True, mode=AircondMode.FAN_ONLY, fan=FanSpeed.LOW
    )


async def test_start_failure_returns_false(manager, coordinator):
    coordinator.api.set_state.side_effect = RuntimeError("boom")

    assert await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN) is False


async def test_legacy_store_migrates_only_enabled_devices(
    manager, coordinator, store, legacy_store, timers
):
    end = dt_util.utcnow() + timedelta(minutes=10)
    legacy = {
        "enabled_devices": [UID_A, "other-entry-device"],
        "active": {UID_A: _entry(end)},
    }
    legacy_store.data = dict(legacy)

    await manager.async_load()

    assert manager.is_enabled(UID_A)
    assert manager.is_enabled("other-entry-device")  # not filtered
    assert not manager.is_active(UID_A)  # legacy "active" is ignored
    assert timers == []
    assert sorted(store.data["enabled_devices"]) == sorted(
        [UID_A, "other-entry-device"]
    )
    assert store.data["active"] == {}
    # legacy file keeps its content; this entry is no longer pending
    assert legacy_store.data == {**legacy, "pending_entries": []}


async def test_legacy_migration_with_empty_device_list_keeps_enabled(
    manager, coordinator, store, legacy_store
):
    """N2: a transiently empty coordinator.data must not drop enabled devices."""
    coordinator.data = {}
    legacy_store.data = {"enabled_devices": [UID_A]}
    await manager.async_load()

    coordinator.data = {UID_A: MagicMock()}
    fresh = MoldProofManager(manager.hass, coordinator, manager._entry)
    await fresh.async_load()

    assert fresh.is_enabled(UID_A), store.data


async def test_per_entry_store_wins_over_legacy(manager, store, legacy_store):
    store.data = {"enabled_devices": [UID_B]}
    legacy_store.data = {"enabled_devices": [UID_A]}

    await manager.async_load()

    assert manager._enabled_devices == {UID_B}


async def test_token_is_persisted_and_bound_to_timer(manager, store, timers):
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)

    token = manager.get_state(UID_A).token
    assert store.data["active"][UID_A]["token"] == token
    assert timers[0][1].args == (UID_A, token)

    fresh = MoldProofManager(manager.hass, manager.coordinator, manager._entry)
    await fresh.async_load()
    assert fresh.get_state(UID_A).token == token


async def test_stale_timer_does_not_finish_newer_cycle(manager, coordinator, timers):
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)
    old_timer = timers[0][1]
    async with manager.device_lock(UID_A):
        await manager.interrupt_mold_proof(UID_A)
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)
    coordinator.api.reset_mock()

    await old_timer(None)

    assert manager.is_active(UID_A)
    assert coordinator.api.mock_calls == []


async def test_interrupt_leaves_cycle_until_committed(manager, store, timers):
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)

    assert manager.get_state(UID_A) is not None  # read-only access
    assert UID_A in store.data["active"]
    timers[0][2].assert_not_called()


async def test_unload_waits_for_inflight_save_before_reload(
    manager, coordinator, store, timers
):
    order = []
    gate = asyncio.Event()

    async def slow_save(data):
        await gate.wait()
        order.append("old save done")
        store.data = data

    store.async_save = slow_save
    old_save = asyncio.ensure_future(manager.set_enabled(UID_B, False))
    await asyncio.sleep(0)

    manager.async_unload()
    waiter = asyncio.ensure_future(manager.async_wait_pending())
    await asyncio.sleep(0)
    assert not waiter.done()

    gate.set()
    await waiter
    await old_save

    # Only now does the reloaded manager load/persist
    async def fast_save(data):
        order.append("new save")
        store.data = data

    store.async_save = fast_save
    fresh = MoldProofManager(manager.hass, coordinator, manager._entry)
    fresh._enabled_devices = {UID_A}
    await fresh.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)

    assert order[0] == "old save done"
    assert UID_A in store.data["active"]


async def test_wait_pending_waits_for_inflight_finish(manager, coordinator, timers):
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)
    gate = asyncio.Event()

    async def slow(*a, **k):
        await gate.wait()

    coordinator.api.set_state.side_effect = slow
    finish = asyncio.ensure_future(timers[0][1](None))
    await asyncio.sleep(0)
    manager.async_unload()
    waiter = asyncio.ensure_future(manager.async_wait_pending())
    await asyncio.sleep(0)
    assert not waiter.done()

    gate.set()
    await waiter
    await finish


def _entries(hass, *ids):
    hass.config_entries.async_entries.return_value = [
        MagicMock(entry_id=i) for i in ids
    ]


def _mgr(hass, coordinator, entry_id):
    return MoldProofManager(hass, coordinator, MagicMock(entry_id=entry_id))


async def test_two_entries_first_upgrade_both_import(
    hass, coordinator, stores, legacy_store, timers
):
    """Several accounts on first upgrade all import; pending list empties."""
    _entries(hass, "E1", "E2")
    legacy_store.data = {"enabled_devices": [UID_A, UID_B]}
    m1, m2 = _mgr(hass, coordinator, "E1"), _mgr(hass, coordinator, "E2")

    await m1.async_load()
    assert legacy_store.data["pending_entries"] == ["E2"]
    await m2.async_load()

    assert m1.is_enabled(UID_A) and m1.is_enabled(UID_B)
    assert m2.is_enabled(UID_A) and m2.is_enabled(UID_B)
    assert legacy_store.data == {
        "enabled_devices": [UID_A, UID_B],
        "pending_entries": [],
    }


async def test_entry_that_loads_late_stays_pending_and_imports_later(
    hass, coordinator, stores, legacy_store, timers
):
    _entries(hass, "E1", "E2")
    legacy_store.data = {"enabled_devices": [UID_A]}
    await _mgr(hass, coordinator, "E1").async_load()
    assert legacy_store.data["pending_entries"] == ["E2"]  # E2 failed to load

    late = _mgr(hass, coordinator, "E2")
    await late.async_load()

    assert late.is_enabled(UID_A)
    assert legacy_store.data["pending_entries"] == []


async def test_re_added_entry_does_not_import(
    hass, coordinator, stores, legacy_store, timers
):
    _entries(hass, "E1")
    legacy_store.data = {"enabled_devices": [UID_A]}
    m1 = _mgr(hass, coordinator, "E1")
    await m1.async_load()
    await m1.set_enabled(UID_A, False)

    _entries(hass, "E2")  # user removed E1 and added a new entry
    m2 = _mgr(hass, coordinator, "E2")
    await m2.async_load()

    assert not m2.is_enabled(UID_A)


async def test_entry_added_fresh_later_does_not_import(
    hass, coordinator, stores, legacy_store, timers
):
    _entries(hass, "E1")
    legacy_store.data = {"enabled_devices": [UID_A]}
    await _mgr(hass, coordinator, "E1").async_load()

    _entries(hass, "E1", "E9")
    fresh = _mgr(hass, coordinator, "E9")
    await fresh.async_load()

    assert not fresh.is_enabled(UID_A)


async def test_legacy_marked_migrated_is_not_imported(
    hass, coordinator, stores, legacy_store
):
    legacy_store.data = {"enabled_devices": [UID_A], "migrated": True}
    mgr = _mgr(hass, coordinator, ENTRY_ID)

    await mgr.async_load()

    assert not mgr.is_enabled(UID_A)
    assert legacy_store.saved == []


async def test_concurrent_loads_do_not_lose_pending_updates(
    hass, coordinator, stores, legacy_store, timers
):
    _entries(hass, "E1", "E2", "E3")
    legacy_store.data = {"enabled_devices": [UID_A]}
    managers = [_mgr(hass, coordinator, e) for e in ("E1", "E2", "E3")]
    orig_save = legacy_store.async_save

    async def slow_save(data):
        await asyncio.sleep(0)  # yield mid read-modify-write
        await orig_save(data)

    legacy_store.async_save = slow_save

    await asyncio.gather(*(m.async_load() for m in managers))

    assert all(m.is_enabled(UID_A) for m in managers)
    assert legacy_store.data["pending_entries"] == []


async def test_finish_failure_for_removed_device_drops_cycle(
    manager, coordinator, store, timers
):
    """R2: no endless retries for a device that left the account."""
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)
    coordinator.api.set_state.side_effect = KeyError(UID_A)
    del coordinator.data[UID_A]

    await timers[0][1](None)

    assert not manager.is_active(UID_A)
    assert store.data["active"] == {}
    assert len(timers) == 1  # no retry armed


async def test_shutdown_lets_inflight_command_commit_before_unload(
    manager, coordinator, store, timers
):
    """Codex T-010: a turn_on finishing during unload must un-persist its cycle."""
    from custom_components.godaikin.climate import GodaikinClimate

    ent = GodaikinClimate(coordinator, UID_A)
    ent.async_write_ha_state = MagicMock()
    await manager.start_mold_proof(UID_A, PREV_MODE, PREV_FAN)
    gate = asyncio.Event()

    async def slow(*a, **k):
        await gate.wait()

    coordinator.api.set_state.side_effect = slow
    turn_on = asyncio.ensure_future(ent.async_turn_on())
    await asyncio.sleep(0)

    shutdown = asyncio.ensure_future(manager.async_shutdown())
    await asyncio.sleep(0)
    timers[0][2].assert_called_once()  # timers are cancelled first
    assert not shutdown.done()
    assert UID_A in store.data["active"]

    gate.set()
    await turn_on
    await shutdown

    assert store.data["active"] == {}  # the committed interrupt was persisted
    assert not manager.is_active(UID_A)
    assert manager._unloaded

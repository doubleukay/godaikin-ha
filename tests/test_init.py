"""Tests for config entry unload/remove wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.godaikin.mold_proof import (
    MoldProofManager,
    async_init_legacy_pending,
)

import pytest

from custom_components.godaikin import async_remove_entry, async_unload_entry
from custom_components.godaikin.const import DOMAIN, STORAGE_KEY

pytestmark = pytest.mark.asyncio


async def test_unload_entry_cancels_timers_and_waits_before_closing_session():
    parent = MagicMock()
    coordinator = MagicMock()
    coordinator.mold_proof.async_shutdown = AsyncMock(
        side_effect=lambda: parent.shutdown()
    )
    coordinator.api.session.close = AsyncMock(
        side_effect=lambda: parent.session_close()
    )
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.data = {DOMAIN: {"e1": coordinator}}
    entry = MagicMock(entry_id="e1")

    assert await async_unload_entry(hass, entry) is True

    assert [c[0] for c in parent.mock_calls] == [
        "shutdown",
        "session_close",
    ]
    assert "e1" not in hass.data[DOMAIN]


async def test_unload_entry_failure_touches_nothing():
    coordinator = MagicMock()
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
    hass.data = {DOMAIN: {"e1": coordinator}}

    assert await async_unload_entry(hass, MagicMock(entry_id="e1")) is False

    coordinator.mold_proof.async_shutdown.assert_not_called()


def _fake_stores(legacy_data):
    """Patch Store in the package with fakes; returns (patcher, stores)."""
    stores: dict[str, MagicMock] = {}

    def factory(hass, version, key):
        if key in stores:
            return stores[key]
        fake = MagicMock(name=key)
        fake.data = legacy_data if key == STORAGE_KEY else None
        fake.removed = False
        fake.saved = []

        async def load():
            return fake.data

        async def save(data):
            fake.saved.append(data)
            fake.data = data

        async def remove():
            fake.removed = True
            fake.data = None

        fake.async_load, fake.async_save, fake.async_remove = load, save, remove
        stores[key] = fake
        return fake

    return factory, stores


async def test_remove_entry_removes_store_and_drops_entry_from_pending():
    factory, stores = _fake_stores(
        {"enabled_devices": ["a"], "pending_entries": ["e1", "e2"]}
    )
    with patch("custom_components.godaikin.Store", side_effect=factory):
        await async_remove_entry(MagicMock(), MagicMock(entry_id="e1"))

    assert stores[f"{STORAGE_KEY}_e1"].removed
    assert stores[STORAGE_KEY].data == {
        "enabled_devices": ["a"],
        "pending_entries": ["e2"],
    }


async def test_remove_entry_leaves_legacy_alone_when_not_pending():
    legacy = {"enabled_devices": ["a"], "pending_entries": ["e2"]}
    factory, stores = _fake_stores(dict(legacy))
    with patch("custom_components.godaikin.Store", side_effect=factory):
        await async_remove_entry(MagicMock(), MagicMock(entry_id="e1"))

    assert stores[STORAGE_KEY].data == legacy
    assert stores[STORAGE_KEY].saved == []


async def test_remove_entry_does_not_create_missing_legacy_store():
    factory, stores = _fake_stores(None)
    with patch("custom_components.godaikin.Store", side_effect=factory):
        await async_remove_entry(MagicMock(), MagicMock(entry_id="e1"))

    assert stores[f"{STORAGE_KEY}_e1"].removed
    assert stores[STORAGE_KEY].saved == []
    assert stores[STORAGE_KEY].data is None


async def test_entry_added_after_removal_does_not_reimport():
    """R3: remove + re-add must not resurrect settings from the legacy store."""
    factory, stores = _fake_stores({"enabled_devices": ["device-a"]})
    coordinator = MagicMock()
    coordinator.data = {"device-a": MagicMock()}
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [MagicMock(entry_id="e1")]
    with (
        patch("custom_components.godaikin.Store", side_effect=factory),
        patch("custom_components.godaikin.mold_proof.Store", side_effect=factory),
    ):
        first = MoldProofManager(hass, coordinator, MagicMock(entry_id="e1"))
        await first.async_load()
        assert first.is_enabled("device-a")

        await async_remove_entry(hass, MagicMock(entry_id="e1"))

        hass.config_entries.async_entries.return_value = [MagicMock(entry_id="e2")]
        readded = MoldProofManager(hass, coordinator, MagicMock(entry_id="e2"))
        await readded.async_load()

    assert not readded.is_enabled("device-a")


def _hass(*entry_ids):
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [
        MagicMock(entry_id=i) for i in entry_ids
    ]
    return hass


async def test_setup_failure_still_initializes_pending_list():
    """The allow-list exists even if setup fails before any legacy read."""
    from custom_components.godaikin import async_setup_entry

    factory, stores = _fake_stores({"enabled_devices": ["a"]})
    entry = MagicMock(entry_id="A")
    entry.data = {"username": "u", "password": "p"}
    with (
        patch("custom_components.godaikin.Store", side_effect=factory),
        patch("custom_components.godaikin.AuthClient", side_effect=RuntimeError("x")),
        pytest.raises(RuntimeError),
    ):
        await async_setup_entry(_hass("A", "B"), entry)

    assert stores[STORAGE_KEY].data["pending_entries"] == ["A", "B"]


async def test_removed_failed_entry_then_new_entry_does_not_import():
    """Codex T-022: A and B fail setup, A is removed, C is added: C stays out."""
    factory, stores = _fake_stores({"enabled_devices": ["device-a"]})
    coordinator = MagicMock()
    coordinator.data = {"device-a": MagicMock()}
    hass = _hass("A", "B")
    with (
        patch("custom_components.godaikin.Store", side_effect=factory),
        patch("custom_components.godaikin.mold_proof.Store", side_effect=factory),
    ):
        legacy = stores.setdefault(STORAGE_KEY, factory(None, 1, STORAGE_KEY))
        await async_init_legacy_pending(hass, legacy)  # start of setup for A / B

        await async_remove_entry(hass, MagicMock(entry_id="A"))
        assert legacy.data["pending_entries"] == ["B"]

        hass.config_entries.async_entries.return_value = [
            MagicMock(entry_id="B"),
            MagicMock(entry_id="C"),
        ]
        new = MoldProofManager(hass, coordinator, MagicMock(entry_id="C"))
        await new.async_load()
        assert not new.is_enabled("device-a")

        old = MoldProofManager(hass, coordinator, MagicMock(entry_id="B"))
        await old.async_load()
        assert old.is_enabled("device-a")


@pytest.mark.parametrize("still_listed", [True, False])
async def test_remove_on_uninitialized_list_initializes_without_removed_id(
    still_listed,
):
    factory, stores = _fake_stores({"enabled_devices": ["a"]})
    hass = _hass("A", "B") if still_listed else _hass("B")
    with patch("custom_components.godaikin.Store", side_effect=factory):
        await async_remove_entry(hass, MagicMock(entry_id="A"))

    assert stores[STORAGE_KEY].data["pending_entries"] == ["B"]


async def test_remove_entry_survives_legacy_save_failure():
    factory, stores = _fake_stores(
        {"enabled_devices": ["a"], "pending_entries": ["e1"]}
    )

    async def boom(data):
        raise OSError("disk full")

    with patch("custom_components.godaikin.Store", side_effect=factory):
        factory(None, 1, STORAGE_KEY).async_save = boom
        await async_remove_entry(_hass("e1"), MagicMock(entry_id="e1"))  # no raise

    assert stores[f"{STORAGE_KEY}_e1"].removed


async def test_load_survives_legacy_clear_failure():
    factory, stores = _fake_stores(
        {"enabled_devices": ["device-a"], "pending_entries": ["e1"]}
    )
    coordinator = MagicMock()
    coordinator.data = {"device-a": MagicMock()}

    async def boom(data):
        raise OSError("disk full")

    with patch("custom_components.godaikin.mold_proof.Store", side_effect=factory):
        factory(None, 1, STORAGE_KEY).async_save = boom
        mgr = MoldProofManager(_hass("e1"), coordinator, MagicMock(entry_id="e1"))
        await mgr.async_load()  # must not raise

    assert mgr.is_enabled("device-a")
    assert stores[f"{STORAGE_KEY}_e1"].data["enabled_devices"] == ["device-a"]

"""Shared fixtures for GO DAIKIN tests (plain mocks, no HA test harness)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.godaikin.const import STORAGE_KEY
from custom_components.godaikin.mold_proof import MoldProofManager
from custom_components.godaikin.types import AircondMode, FanSpeed

UID_A = "device-a"
UID_B = "device-b"
ENTRY_ID = "entry1"


@pytest.fixture
def timers():
    """Patch async_call_later; yields a list of (delay, action, cancel_mock)."""
    scheduled: list[tuple[float, object, MagicMock]] = []

    def fake_call_later(hass, delay, action):
        cancel = MagicMock(name="cancel_timer")
        scheduled.append((delay, action, cancel))
        return cancel

    with patch(
        "custom_components.godaikin.mold_proof.async_call_later",
        side_effect=fake_call_later,
    ):
        yield scheduled


def _make_fake_store():
    fake = MagicMock(name="store")
    fake.data = None
    fake.saved = []

    async def _load():
        return fake.data

    async def _save(data):
        fake.saved.append(data)
        fake.data = data

    fake.async_load = _load
    fake.async_save = _save
    return fake


@pytest.fixture
def stores():
    """Patch Store with in-memory fakes keyed by storage key."""
    fakes: dict[str, MagicMock] = {}

    def factory(hass, version, key):
        return fakes.setdefault(key, _make_fake_store())

    with patch("custom_components.godaikin.mold_proof.Store", side_effect=factory):
        yield fakes


@pytest.fixture
def store(stores):
    """The per-entry store (.data holds the content, .saved every save)."""
    return stores.setdefault(f"{STORAGE_KEY}_{ENTRY_ID}", _make_fake_store())


@pytest.fixture
def legacy_store(stores):
    """The legacy shared store."""
    return stores.setdefault(STORAGE_KEY, _make_fake_store())


@pytest.fixture
def entry():
    """Mock config entry whose background tasks start eagerly, like HA."""
    ent = MagicMock(name="entry")
    ent.entry_id = ENTRY_ID

    def create_background_task(hass, coro, name):
        return asyncio.Task(coro, loop=asyncio.get_running_loop(), eager_start=True)

    ent.async_create_background_task.side_effect = create_background_task
    return ent


@pytest.fixture
def coordinator():
    """Mock coordinator with an AsyncMock api and two known devices."""
    coord = MagicMock(name="coordinator")
    coord.api = AsyncMock(name="api")
    coord.async_request_refresh = AsyncMock()
    coord.data = {UID_A: MagicMock(), UID_B: MagicMock()}
    return coord


@pytest.fixture
def hass():
    """MagicMock hass."""
    h = MagicMock(name="hass")
    h.config_entries.async_entries.return_value = [MagicMock(entry_id=ENTRY_ID)]
    return h


@pytest.fixture
def manager(hass, coordinator, entry, stores, store, legacy_store, timers):
    """A MoldProofManager with both devices enabled."""
    mgr = MoldProofManager(hass, coordinator, entry)
    mgr._enabled_devices = {UID_A, UID_B}
    coordinator.mold_proof = mgr
    return mgr


PREV_MODE = AircondMode.COOL
PREV_FAN = FanSpeed.HIGH

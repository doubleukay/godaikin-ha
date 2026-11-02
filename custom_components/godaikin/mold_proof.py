"""Mold-proof manager for GO DAIKIN integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import partial
import logging
import uuid
import weakref
from typing import Any, Callable, TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
from .types import AircondMode, FanSpeed, UniqueID

if TYPE_CHECKING:
    from .coordinator import GodaikinDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# A failed finish (e.g. cloud outage) is retried while the entry is loaded,
# with exponential backoff: 180 s, 360 s, 720 s ... capped at 30 minutes
FINISH_RETRY_SECONDS = 180
MAX_FINISH_RETRY_SECONDS = 1800


def finish_retry_delay(attempts: int) -> int:
    """Return the retry delay in seconds after the given number of failures."""
    return min(FINISH_RETRY_SECONDS * 2 ** (attempts - 1), MAX_FINISH_RETRY_SECONDS)


_LEGACY_LOCKS: weakref.WeakKeyDictionary[HomeAssistant, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)


def legacy_lock(hass: HomeAssistant) -> asyncio.Lock:
    """Lock serialising read-modify-write of the shared legacy store.

    Config entries load concurrently at startup and all touch that store.
    """
    lock = _LEGACY_LOCKS.get(hass)
    if lock is None:
        lock = _LEGACY_LOCKS[hass] = asyncio.Lock()
    return lock


def _with_pending_entries(hass: HomeAssistant, legacy: dict) -> dict:
    """Return legacy with "pending_entries" created if it does not exist yet.

    The list is the allow-list of config entries that exist at upgrade time and
    may import the old shared settings. Legacy data already marked "migrated"
    (dev builds) never gets one. Caller holds the legacy lock.
    """
    if "pending_entries" in legacy or legacy.get("migrated"):
        return legacy
    return {
        **legacy,
        "pending_entries": [
            e.entry_id for e in hass.config_entries.async_entries(DOMAIN)
        ],
    }


async def async_init_legacy_pending(hass: HomeAssistant, legacy_store: Store) -> None:
    """Create the legacy store's pending-entries list if it is missing.

    Called at the very start of setup, before anything that can fail, so the
    list reflects the entries that existed when the integration was upgraded.
    Never creates the legacy store.
    """
    async with legacy_lock(hass):
        legacy = await legacy_store.async_load()
        if not isinstance(legacy, dict):
            return
        updated = _with_pending_entries(hass, legacy)
        if updated is not legacy:
            await legacy_store.async_save(updated)


async def async_clear_legacy_pending(
    hass: HomeAssistant, legacy_store: Store, entry_id: str
) -> None:
    """Remove an entry id from the legacy store's pending list.

    Initializes the list first if it does not exist yet, so a removal on an
    uninitialized list cannot let a later entry in. Never creates the legacy
    store and preserves all other content.
    """
    async with legacy_lock(hass):
        legacy = await legacy_store.async_load()
        if not isinstance(legacy, dict):
            return
        updated = _with_pending_entries(hass, legacy)
        pending = updated.get("pending_entries")
        if isinstance(pending, list) and entry_id in pending:
            updated = {
                **updated,
                "pending_entries": [e for e in pending if e != entry_id],
            }
        if updated is not legacy:
            await legacy_store.async_save(updated)


@dataclass
class MoldProofState:
    """State for mold-proof operation."""

    unique_id: UniqueID
    start_time: datetime
    end_time: datetime
    previous_mode: AircondMode
    previous_fan_speed: FanSpeed
    cancel_timer: Callable | None = None
    finish_attempts: int = 0
    # Identifies this cycle so a stale timer cannot finish a newer one
    token: str = field(default_factory=lambda: uuid.uuid4().hex)


class MoldProofManager:
    """Manage mold-proof operations for air conditioners."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: GodaikinDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the mold-proof manager."""
        self.hass = hass
        self.coordinator = coordinator
        self._entry = entry
        self._active_states: dict[UniqueID, MoldProofState] = {}
        self._enabled_devices: set[UniqueID] = set()
        self._duration_minutes = 60
        self._locks: dict[UniqueID, asyncio.Lock] = {}
        self._unloaded = False
        self._pending_saves: set[asyncio.Future] = set()
        # Storage is per config entry so entries cannot overwrite each other
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
        self._legacy_store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    def device_lock(self, unique_id: UniqueID) -> asyncio.Lock:
        """Return the (non-reentrant) lock serialising commands for a device."""
        return self._locks.setdefault(unique_id, asyncio.Lock())

    async def async_load(self) -> None:
        """Load enabled devices and active cycles from storage."""
        data = await self._store.async_load()
        migrated = False
        if data is None:
            data = await self._async_load_legacy()
            migrated = data is not None
        if not isinstance(data, dict):
            _LOGGER.debug("No mold-proof storage data found")
            return

        enabled = data.get("enabled_devices")
        if not isinstance(enabled, list):
            enabled = []
        self._enabled_devices = set(enabled)
        _LOGGER.debug(
            "Loaded %d enabled devices from storage", len(self._enabled_devices)
        )

        dropped = migrated
        active = data.get("active")
        if active is None:
            active = {}
        elif not isinstance(active, dict):
            _LOGGER.warning("Ignoring invalid persisted mold-proof cycles")
            active = {}
            dropped = True

        now = dt_util.utcnow()
        expired: list[UniqueID] = []
        for unique_id, entry in active.items():
            state = self._parse_active(unique_id, entry)
            if state is None:
                dropped = True
                continue

            self._active_states[unique_id] = state
            remaining = (state.end_time - now).total_seconds()
            if remaining <= 0:
                expired.append(unique_id)
            else:
                _LOGGER.info(
                    "Resuming mold-proof for %s (%d seconds left)",
                    unique_id,
                    int(remaining),
                )
                state.cancel_timer = self._arm_timer(unique_id, state.token, remaining)

        # Save once, after every cycle is registered, so a finish started
        # below never persists a partial view of the active cycles
        if dropped:
            await self._async_save()
        if migrated:
            # Not needed for correctness: a crash before the per-entry store
            # was saved simply migrates again on the next start, and once it
            # exists the per-entry store wins, so a leftover id is harmless
            try:
                await self._async_clear_pending()
            except Exception as err:
                _LOGGER.warning("Could not update the legacy migration list: %s", err)

        for unique_id in expired:
            _LOGGER.info("Mold-proof for %s elapsed while offline", unique_id)
            self._entry.async_create_background_task(
                self.hass,
                self._finish_mold_proof(unique_id),
                f"godaikin mold-proof finish {unique_id}",
            )

    async def _async_load_legacy(self) -> dict | None:
        """Take the enabled devices from the legacy shared store, if this
        entry is still pending migration.

        The first entry to read the legacy store after the upgrade records every
        config entry known at that moment in "pending_entries". Only those
        entries import (and then remove themselves from the list), so an entry
        added later, or re-added after a removal, never imports stale settings,
        while an entry that could not load at first still can later.
        The legacy store never held active cycles in a released version, and
        foreign device ids in the set are harmless, so nothing is filtered.
        """
        async with legacy_lock(self.hass):
            legacy = await self._legacy_store.async_load()
            if not isinstance(legacy, dict) or legacy.get("migrated"):
                return None

            # Normally already created at the start of setup; this covers
            # callers that did not go through async_setup_entry
            updated = _with_pending_entries(self.hass, legacy)
            if updated is not legacy:
                legacy = updated
                await self._legacy_store.async_save(legacy)

            pending = legacy.get("pending_entries")
            if not isinstance(pending, list) or self._entry.entry_id not in pending:
                return None

            enabled = legacy.get("enabled_devices")
            _LOGGER.info("Migrating mold-proof settings from the shared legacy store")
            return {"enabled_devices": enabled if isinstance(enabled, list) else []}

    async def _async_clear_pending(self) -> None:
        """Remove this entry from the legacy store's pending list."""
        await async_clear_legacy_pending(
            self.hass, self._legacy_store, self._entry.entry_id
        )

    def _parse_active(self, unique_id: UniqueID, entry: Any) -> MoldProofState | None:
        """Build a state from persisted data, or None if it is invalid/stale."""
        if unique_id not in self.coordinator.data:
            _LOGGER.warning(
                "Dropping persisted mold-proof for unknown device %s", unique_id
            )
            return None

        try:
            end_time = dt_util.parse_datetime(entry["end_time"])
            if end_time is None:
                raise ValueError("invalid end_time")
            end_time = dt_util.as_utc(end_time)
            previous_mode = AircondMode(entry["previous_mode"])
            previous_fan_speed = FanSpeed(entry["previous_fan_speed"])
            token = entry.get("token")
            if not isinstance(token, str) or not token:
                token = uuid.uuid4().hex
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning(
                "Dropping invalid persisted mold-proof for %s: %s", unique_id, err
            )
            return None

        return MoldProofState(
            unique_id=unique_id,
            start_time=end_time - timedelta(minutes=self._duration_minutes),
            end_time=end_time,
            previous_mode=previous_mode,
            previous_fan_speed=previous_fan_speed,
            token=token,
        )

    async def _async_save(self) -> None:
        """Save enabled devices and active cycles to storage."""
        if self._unloaded:
            return

        data = {
            "enabled_devices": list(self._enabled_devices),
            "active": {
                unique_id: {
                    "end_time": state.end_time.isoformat(),
                    "previous_mode": int(state.previous_mode),
                    "previous_fan_speed": int(state.previous_fan_speed),
                    "token": state.token,
                }
                for unique_id, state in self._active_states.items()
            },
        }
        # Track the write so unload can wait for it; shield keeps it running
        # (and tracked) even if the caller is cancelled
        task = asyncio.ensure_future(self._store.async_save(data))
        self._pending_saves.add(task)
        task.add_done_callback(self._pending_saves.discard)
        await asyncio.shield(task)
        _LOGGER.debug(
            "Saved %d enabled devices and %d active cycles to storage",
            len(self._enabled_devices),
            len(self._active_states),
        )

    async def async_persist(self) -> None:
        """Persist the current state (after an in-place state change)."""
        await self._async_save()

    def _arm_timer(
        self, unique_id: UniqueID, token: str, delay: float
    ) -> Callable[[], None]:
        """Schedule the finish of one specific cycle of a device."""
        return async_call_later(
            self.hass, delay, partial(self._finish_mold_proof, unique_id, token)
        )

    def _pop_state(self, unique_id: UniqueID) -> MoldProofState | None:
        """Remove a device's state and cancel its timer."""
        state = self._active_states.pop(unique_id, None)
        if state is not None and state.cancel_timer:
            state.cancel_timer()
            state.cancel_timer = None
        return state

    def set_duration(self, minutes: int) -> None:
        """Set the mold-proof duration in minutes."""
        self._duration_minutes = minutes
        _LOGGER.debug("Mold-proof duration set to %d minutes", minutes)

    async def set_enabled(self, unique_id: UniqueID, enabled: bool) -> None:
        """Enable or disable mold-proof for a specific device."""
        if enabled:
            self._enabled_devices.add(unique_id)
            _LOGGER.debug("Mold-proof enabled for %s", unique_id)
        else:
            self._enabled_devices.discard(unique_id)
            # End any active cycle properly: the device is still in
            # FAN_ONLY/LOW, so restore it and turn it off
            if unique_id in self._active_states:
                await self._finish_mold_proof(unique_id)
            _LOGGER.debug("Mold-proof disabled for %s", unique_id)

        # Save to storage
        await self._async_save()

    def is_enabled(self, unique_id: UniqueID) -> bool:
        """Check if mold-proof is enabled for a device."""
        return unique_id in self._enabled_devices

    def is_active(self, unique_id: UniqueID) -> bool:
        """Check if mold-proof is currently active for a device."""
        return unique_id in self._active_states

    async def start_mold_proof(
        self,
        unique_id: UniqueID,
        previous_mode: AircondMode,
        previous_fan_speed: FanSpeed,
    ) -> bool:
        """Start mold-proof for a device, taking the device lock.

        Callers that already hold the device lock use start_mold_proof_locked.
        """
        async with self.device_lock(unique_id):
            return await self.start_mold_proof_locked(
                unique_id, previous_mode, previous_fan_speed
            )

    async def start_mold_proof_locked(
        self,
        unique_id: UniqueID,
        previous_mode: AircondMode,
        previous_fan_speed: FanSpeed,
    ) -> bool:
        """Start mold-proof; the caller holds the device lock.

        Returns True if a cycle is running afterwards.
        """
        if not self.is_enabled(unique_id):
            _LOGGER.debug("Mold-proof not enabled for %s, skipping", unique_id)
            return False

        # Cancel any existing mold-proof
        self._pop_state(unique_id)

        _LOGGER.info(
            "Starting mold-proof for %s (duration: %d minutes)",
            unique_id,
            self._duration_minutes,
        )

        # Register (and persist) the state and arm the timer before touching
        # the device, so a crash or reload mid-start still finishes the cycle
        now = dt_util.utcnow()
        duration = timedelta(minutes=self._duration_minutes)
        state = MoldProofState(
            unique_id=unique_id,
            start_time=now,
            end_time=now + duration,
            previous_mode=previous_mode,
            previous_fan_speed=previous_fan_speed,
        )
        state.cancel_timer = self._arm_timer(
            unique_id, state.token, duration.total_seconds()
        )
        self._active_states[unique_id] = state
        await self._async_save()

        # Set to fan mode with low speed
        try:
            await self.coordinator.api.set_state(
                unique_id, on=True, mode=AircondMode.FAN_ONLY, fan=FanSpeed.LOW
            )
        except Exception as err:
            # The request may have been applied despite the error (e.g. a
            # timeout), so keep the cycle registered, persisted and armed: the
            # caller falls back to restore-and-off for it, or its timer will
            _LOGGER.error("Failed to start mold-proof for %s: %s", unique_id, err)
            return False

        # Commands are serialised by the device lock, so only an unload can
        # have removed the state by now
        return self._active_states.get(unique_id) is state

    async def _finish_mold_proof(
        self, unique_id: UniqueID, token: str | None = None, _now=None
    ) -> None:
        """Finish mold-proof for a device: restore settings and turn it off.

        A timer passes the token of the cycle that scheduled it; if that cycle
        is gone (or replaced by a newer one) there is nothing to finish.
        """
        async with self.device_lock(unique_id):
            if self._unloaded:
                return
            state = self._active_states.get(unique_id)
            if state is None or (token is not None and state.token != token):
                return

            if state.cancel_timer:
                state.cancel_timer()
                state.cancel_timer = None

            _LOGGER.info("Finishing mold-proof for %s", unique_id)
            try:
                # Restore previous mode and fan speed and power off in one request
                await self.coordinator.api.set_state(
                    unique_id,
                    on=False,
                    mode=state.previous_mode,
                    fan=state.previous_fan_speed,
                )
            except Exception as err:
                # Keep the state (and the persisted entry) so it is retried
                # now and, failing that, after a restart
                state.finish_attempts += 1
                _LOGGER.error(
                    "Failed to turn off AC after mold-proof for %s " "(attempt %d): %s",
                    unique_id,
                    state.finish_attempts,
                    err,
                )
                if self._unloaded or self._active_states.get(unique_id) is not state:
                    return
                if unique_id not in self.coordinator.data:
                    # The device left the account: nothing left to finish
                    _LOGGER.warning(
                        "Dropping mold-proof for %s: device no longer present",
                        unique_id,
                    )
                    self._pop_state(unique_id)
                    await self._async_save()
                    return
                state.cancel_timer = self._arm_timer(
                    unique_id,
                    state.token,
                    finish_retry_delay(state.finish_attempts),
                )
                return

            if self._active_states.get(unique_id) is state:
                self._pop_state(unique_id)
            await self._async_save()

        try:
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.debug("Refresh after mold-proof failed: %s", err)

    def reschedule_finish(
        self, state: MoldProofState, delay: float = FINISH_RETRY_SECONDS
    ) -> None:
        """Finish the given cycle soon, if it is still the active one."""
        if self._unloaded or self._active_states.get(state.unique_id) is not state:
            return
        if state.cancel_timer:
            state.cancel_timer()
        state.cancel_timer = self._arm_timer(state.unique_id, state.token, delay)

    async def interrupt_mold_proof(self, unique_id: UniqueID) -> MoldProofState | None:
        """End the active cycle (the user's request has been carried out).

        Callers hold the device lock, read the state with get_state, perform
        their device commands, and call this only once those succeeded. If the
        commands fail the cycle (and its timer) stays in place. Returns the
        removed state, or None if there was none.
        """
        state = self._pop_state(unique_id)
        if state is None:
            return None

        await self._async_save()
        _LOGGER.info("Mold-proof interrupted for %s", unique_id)
        return state

    @callback
    def async_unload(self) -> None:
        """Cancel all pending timers and stop all activity (sync, idempotent).

        Persisted cycles are kept so they resume after a reload or restart;
        after this the manager no longer saves or finishes anything. Prefer
        async_shutdown, which first lets in-flight commands complete.
        """
        self._unloaded = True
        for unique_id in list(self._active_states):
            self._pop_state(unique_id)

    async def async_shutdown(self) -> None:
        """Unload gracefully (called before the API session is closed).

        Timers are cancelled first, then in-flight commands, finishes and saves
        are awaited while the manager is still live, so a command that completes
        meanwhile can still end (and un-persist) its cycle. Only then is the
        manager marked unloaded.
        """
        for state in self._active_states.values():
            if state.cancel_timer:
                state.cancel_timer()
                state.cancel_timer = None
        await self.async_wait_pending()
        self.async_unload()

    async def async_wait_pending(self) -> None:
        """Wait for in-flight saves and device operations (call after unload).

        Acquiring each device lock once waits for any finish or climate command
        that is still running; queued finishes are no-ops after unload.
        """
        for lock in list(self._locks.values()):
            async with lock:
                pass
        if self._pending_saves:
            await asyncio.gather(*self._pending_saves, return_exceptions=True)

    def get_state(self, unique_id: UniqueID) -> MoldProofState | None:
        """Get the mold-proof state for a device."""
        return self._active_states.get(unique_id)

    def get_remaining_time(self, unique_id: UniqueID) -> int:
        """Get remaining mold-proof time in seconds."""
        if unique_id not in self._active_states:
            return 0

        state = self._active_states[unique_id]
        remaining = (state.end_time - dt_util.utcnow()).total_seconds()

        return max(0, int(remaining))

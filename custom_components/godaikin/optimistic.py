"""
Pending-change overlay: shows commands sent to the cloud right away.

The cloud lags behind a command, so for a while the polled shadow state still
holds the old values. Commands are recorded here and laid over the polled state
until the cloud confirms them (or they expire and the cloud wins).
"""

from dataclasses import fields
import logging

from .types import Aircond, ShadowState, UniqueID

_LOGGER = logging.getLogger(__name__)

_SHADOW_FIELDS = frozenset(f.name for f in fields(ShadowState))
_MISSING = object()


class OptimisticOverlay:
    def __init__(self, ttl: float):
        self.ttl = ttl
        # unique_id -> {key: (value, expires_at, cloud_value)}; cloud_value is the
        # stale value last seen from the cloud while overriding (None until then)
        self._pending: dict[UniqueID, dict[str, tuple[object, float, object]]] = {}

    def record(self, unique_id: UniqueID, desired: dict, now: float) -> None:
        """Remember the sent Set_* values. Never raises."""
        try:
            for key, value in desired.items():
                if not (key.startswith("Set_") and key in _SHADOW_FIELDS):
                    _LOGGER.debug("Not tracking non-shadow key %r", key)
                    continue
                self._pending.setdefault(unique_id, {})[key] = (
                    value,
                    now + self.ttl,
                    None,
                )
        except Exception:
            _LOGGER.exception("Failed to record optimistic state")

    def apply(self, aircond: Aircond, now: float) -> None:
        """Reconcile pending values with a freshly polled aircond. Never raises.

        Confirms or expires entries and overlays the rest. Only call this with
        objects fresh from the API: an already overlaid object would falsely
        confirm every pending value.
        """
        try:
            pending = self._pending.get(aircond.unique_id)
            if not pending:
                return
            shadow = aircond.shadowState
            for key, (value, expires_at, _old) in list(pending.items()):
                if getattr(shadow, key, _MISSING) == value:
                    del pending[key]  # confirmed by the cloud
                elif now >= expires_at:
                    del pending[key]  # expired: the cloud wins
                else:
                    cloud_value = getattr(shadow, key, None)
                    pending[key] = (value, expires_at, cloud_value)
                    setattr(shadow, key, value)
            if not pending:
                self._pending.pop(aircond.unique_id, None)
        except Exception:
            _LOGGER.exception("Failed to apply optimistic state")

    def paint(self, aircond: Aircond) -> None:
        """Set pending values on the shadow state only. Never raises.

        Unlike apply this never confirms, expires or deletes anything, so it is
        safe on an object that is already overlaid.
        """
        try:
            shadow = aircond.shadowState
            for key, (value, _expires, _old) in self._pending.get(
                aircond.unique_id, {}
            ).items():
                setattr(shadow, key, value)
        except Exception:
            _LOGGER.exception("Failed to paint optimistic state")

    def prune(self, unique_ids) -> None:
        """Drop entries for devices that are no longer present."""
        keep = set(unique_ids)
        for unique_id in [u for u in self._pending if u not in keep]:
            del self._pending[unique_id]

    def snapshot(self, now: float) -> dict[UniqueID, dict[str, dict]]:
        """Pending entries for diagnostics.

        cloud_value is the stale value the cloud last reported (None if not
        seen yet).
        """
        return {
            unique_id: {
                key: {
                    "value": value,
                    "cloud_value": cloud_value,
                    "seconds_left": round(expires_at - now, 1),
                }
                for key, (value, expires_at, cloud_value) in pending.items()
            }
            for unique_id, pending in self._pending.items()
        }

"""Tests for the pure OptimisticOverlay."""

from __future__ import annotations

from custom_components.godaikin.optimistic import OptimisticOverlay
from custom_components.godaikin.types import Aircond, ShadowState

TTL = 30.0


def _aircond(uid="u1", **shadow) -> Aircond:
    ac = Aircond(shadowState=ShadowState(**shadow))
    ac.ThingName = uid
    return ac


def _uid(ac) -> str:
    return ac.unique_id


def _overlay():
    return OptimisticOverlay(TTL)


def test_record_filters_non_set_and_unknown_keys():
    ov = _overlay()
    ov.record("u", {"Set_Mode": 1, "Sta_Mode": 2, "Set_Bogus": 3, "foo": 4}, 0)

    assert set(ov.snapshot(0)["u"]) == {"Set_Mode"}


def test_record_never_raises():
    ov = _overlay()
    ov.record("u", None, 0)  # type: ignore[arg-type]
    ov.record("u", {1: 2}, 0)  # type: ignore[dict-item]


def test_apply_stale_overlay_wins():
    ac = _aircond(Set_Mode=2)
    ov = _overlay()
    ov.record(_uid(ac), {"Set_Mode": 1}, 0)

    ov.apply(ac, 5)

    assert ac.shadowState.Set_Mode == 1
    assert "Set_Mode" in ov.snapshot(5)[_uid(ac)]


def test_apply_matching_confirms_and_drops():
    ac = _aircond(Set_Mode=1)
    ov = _overlay()
    ov.record(_uid(ac), {"Set_Mode": 1}, 0)

    ov.apply(ac, 5)

    assert ov.snapshot(5) == {}


def test_apply_expired_cloud_wins():
    ac = _aircond(Set_Mode=2)
    ov = _overlay()
    ov.record(_uid(ac), {"Set_Mode": 1}, 0)

    ov.apply(ac, TTL)

    assert ac.shadowState.Set_Mode == 2
    assert ov.snapshot(TTL) == {}


def test_partial_multi_key_confirmation():
    ac = _aircond(Set_Turbo=1, Set_Silent=0)
    ov = _overlay()
    ov.record(_uid(ac), {"Set_Turbo": 1, "Set_Silent": 1}, 0)

    ov.apply(ac, 5)  # turbo confirmed, silent still stale
    assert ac.shadowState.Set_Silent == 1
    assert set(ov.snapshot(5)[_uid(ac)]) == {"Set_Silent"}

    ac2 = _aircond(Set_Turbo=1, Set_Silent=1)
    ov.apply(ac2, 12)
    assert ov.snapshot(12) == {}


def test_a_b_a_confirms_early_pinned():
    """Known limitation: a stale poll matching the final A confirms early."""
    ac = _aircond(Set_Mode=1)  # cloud still shows the original A
    ov = _overlay()
    ov.record(_uid(ac), {"Set_Mode": 2}, 0)  # A -> B
    ov.record(_uid(ac), {"Set_Mode": 1}, 1)  # B -> A

    ov.apply(ac, 5)

    assert ov.snapshot(5) == {}  # dropped on the stale match
    ac_b = _aircond(Set_Mode=2)  # cloud then passes through B
    ov.apply(ac_b, 8)
    assert ac_b.shadowState.Set_Mode == 2  # B shows briefly


def test_apply_never_raises_on_bad_aircond():
    ov = _overlay()
    ov.record("u", {"Set_Mode": 1}, 0)
    ov.apply(object(), 0)  # type: ignore[arg-type]


def test_prune_drops_gone_devices():
    ov = _overlay()
    ov.record("a", {"Set_Mode": 1}, 0)
    ov.record("b", {"Set_Mode": 1}, 0)

    ov.prune(["a"])

    assert set(ov.snapshot(0)) == {"a"}


def test_snapshot_reports_value_and_seconds_left():
    ov = _overlay()
    ov.record("a", {"Set_Mode": 1}, 10)

    assert ov.snapshot(15) == {
        "a": {"Set_Mode": {"value": 1, "cloud_value": None, "seconds_left": 25.0}}
    }


def test_snapshot_records_stale_cloud_value_when_overriding():
    ov = _overlay()
    ac = _aircond(Set_Mode=2)
    ov.record(_uid(ac), {"Set_Mode": 1}, 0)

    ov.apply(_aircond(Set_Mode=2), 5)

    assert ov.snapshot(5)[_uid(ac)]["Set_Mode"] == {
        "value": 1,
        "cloud_value": 2,
        "seconds_left": 25.0,
    }


def test_paint_sets_values_without_confirming_or_expiring():
    ov = _overlay()
    ac = _aircond(Set_Mode=1, Set_Temp=24)
    ov.record(_uid(ac), {"Set_Mode": 1, "Set_Temp": 22}, 0)

    ov.paint(ac)  # Set_Mode already equals the pending value: must stay pending

    assert ac.shadowState.Set_Temp == 22
    assert set(ov.snapshot(0)[_uid(ac)]) == {"Set_Mode", "Set_Temp"}


def test_paint_ignores_expiry_and_never_raises():
    ov = _overlay()
    ov.record("u", {"Set_Mode": 1}, 0)

    ov.paint(object())  # no unique_id/shadowState: swallowed
    assert set(ov.snapshot(0)["u"]) == {"Set_Mode"}

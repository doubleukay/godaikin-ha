"""Tests for EnergyCounter."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.godaikin import energy
from custom_components.godaikin.energy import EnergyCounter

T0 = datetime(2026, 1, 1, 12, 0, 0)


def make_aircond(power=1000, connected=True):
    return SimpleNamespace(
        unique_id="abc",
        is_connected=connected,
        shadowState=SimpleNamespace(Sta_ODPwrCon=power),
    )


def poll(counter, aircond, at):
    with patch.object(energy, "dt") as mock_dt:
        mock_dt.now.return_value = at
        return counter.accumulate_energy_usage_for_aircond(aircond)


def test_first_accumulation_returns_zero():
    assert poll(EnergyCounter(), make_aircond(), T0) == 0.0


def test_connected_integrates():
    c = EnergyCounter()
    a = make_aircond(1000)
    poll(c, a, T0)
    total = poll(c, a, T0 + timedelta(seconds=7))
    assert total == pytest.approx(1000 * 7 / 3600 / 1000)
    assert c.get_energy_usage("abc") == pytest.approx(total)


def test_lagging_power_still_integrates():
    # Unit switched off but power not yet back to 0: still counted.
    c = EnergyCounter()
    a = make_aircond(500)
    a.power_on = False
    poll(c, a, T0)
    total = poll(c, a, T0 + timedelta(seconds=7))
    assert total == pytest.approx(500 * 7 / 3600 / 1000)


def test_disconnected_adds_nothing_and_no_jump_on_reconnect():
    c = EnergyCounter()
    a = make_aircond(1000)
    poll(c, a, T0)
    base = poll(c, a, T0 + timedelta(seconds=7))
    a.is_connected = False
    t = T0 + timedelta(seconds=7)
    for _ in range(100):
        t += timedelta(seconds=7)
        assert poll(c, a, t) == pytest.approx(base)
    a.is_connected = True
    t += timedelta(seconds=7)
    assert poll(c, a, t) == pytest.approx(base + 1000 * 7 / 3600 / 1000)


def test_gap_skipped_then_resumes():
    c = EnergyCounter()
    a = make_aircond(1000)
    poll(c, a, T0)
    base = poll(c, a, T0 + timedelta(seconds=7))
    t = T0 + timedelta(seconds=7 + 61)
    assert poll(c, a, t) == pytest.approx(base)
    t += timedelta(seconds=7)
    assert poll(c, a, t) == pytest.approx(base + 1000 * 7 / 3600 / 1000)

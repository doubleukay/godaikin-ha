"""Tests for the combined desired-state API call."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.godaikin.api import ApiClient
from custom_components.godaikin.types import AircondMode, FanSpeed

pytestmark = pytest.mark.asyncio


@pytest.fixture
def api():
    with patch("aiohttp.ClientSession"):
        client = ApiClient(MagicMock())
    client._set_desired_state = AsyncMock()
    return client


async def test_set_state_sends_one_combined_request(api):
    await api.set_state("uid", on=False, mode=AircondMode.COOL, fan=FanSpeed.MEDIUM)

    api._set_desired_state.assert_awaited_once_with(
        "uid", Set_OnOff=0, Set_Mode=1, Set_Fan=4
    )


async def test_set_state_power_only_and_partial(api):
    await api.set_state("uid", on=True)
    await api.set_state("uid", on=True, fan=FanSpeed.LOW)

    assert [c.kwargs for c in api._set_desired_state.await_args_list] == [
        {"Set_OnOff": 1},
        {"Set_OnOff": 1, "Set_Fan": 2},
    ]

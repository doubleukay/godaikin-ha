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


@pytest.fixture
def raw_api():
    """ApiClient with only the HTTP layer mocked."""
    with patch("aiohttp.ClientSession"):
        client = ApiClient(MagicMock())
    client._api_request = AsyncMock(return_value={})
    aircond = MagicMock()
    client.airconds_by_unique_id = {"uid": aircond}
    return client


async def test_hook_receives_sent_dict_on_success(raw_api):
    hook = MagicMock()
    raw_api.on_desired_sent = hook

    await raw_api.set_state("uid", on=False, mode=AircondMode.COOL)

    hook.assert_called_once_with("uid", {"Set_OnOff": 0, "Set_Mode": 1})


async def test_hook_not_called_when_post_raises(raw_api):
    hook = MagicMock()
    raw_api.on_desired_sent = hook
    raw_api._api_request.side_effect = RuntimeError("http 500")

    with pytest.raises(RuntimeError):
        await raw_api.set_state("uid", on=True)

    hook.assert_not_called()


async def test_hook_exception_is_swallowed(raw_api):
    raw_api.on_desired_sent = MagicMock(side_effect=RuntimeError("boom"))

    await raw_api.set_state("uid", on=True)  # does not raise

    raw_api.on_desired_sent.assert_called_once()


async def test_no_hook_is_fine(raw_api):
    assert raw_api.on_desired_sent is None
    await raw_api.set_state("uid", on=True)

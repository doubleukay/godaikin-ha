"""Tests that AuthClient never blocks the event loop (plain mocks)."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime as dt, timedelta
from unittest.mock import MagicMock, patch

import pytest

from custom_components.godaikin.auth import AuthClient, CognitoToken

pytestmark = pytest.mark.asyncio


def _token(expires_in: timedelta, id_token: str = "id") -> CognitoToken:
    return CognitoToken("access", id_token, "refresh", dt.now() + expires_in)


def _client() -> AuthClient:
    with patch("custom_components.godaikin.auth.boto3.Session"):
        return AuthClient("user", "pass")


async def test_initial_auth_runs_off_loop():
    client = _client()
    main = threading.get_ident()
    seen = []

    def fake_init():
        seen.append(threading.get_ident())
        return _token(timedelta(hours=1))

    client.init_cognito_token = fake_init
    assert await client.async_get_jwt_token() == "id"
    assert seen and seen[0] != main


async def test_refresh_runs_off_loop():
    client = _client()
    client.token = _token(timedelta(minutes=1))
    main = threading.get_ident()
    seen = []

    def fake_refresh(token):
        seen.append(threading.get_ident())
        return _token(timedelta(hours=1), "new")

    client.refresh_jwt_token = fake_refresh
    assert await client.async_get_jwt_token() == "new"
    assert seen and seen[0] != main


async def test_refresh_only_when_near_expiry():
    client = _client()
    client.token = _token(timedelta(hours=1), "fresh")
    client.refresh_jwt_token = MagicMock()
    assert await client.async_get_jwt_token() == "fresh"
    client.refresh_jwt_token.assert_not_called()

    client.token = _token(timedelta(minutes=2), "stale")
    client.refresh_jwt_token = MagicMock(return_value=_token(timedelta(hours=1), "n"))
    assert await client.async_get_jwt_token() == "n"
    client.refresh_jwt_token.assert_called_once()


async def test_concurrent_calls_refresh_once():
    client = _client()
    client.token = _token(timedelta(minutes=1))
    calls = []

    def slow_refresh(token):
        calls.append(1)
        time.sleep(0.1)
        return _token(timedelta(hours=1), "new")

    client.refresh_jwt_token = slow_refresh
    results = await asyncio.gather(*(client.async_get_jwt_token() for _ in range(5)))
    assert results == ["new"] * 5
    assert len(calls) == 1

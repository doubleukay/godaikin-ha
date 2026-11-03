"""
Authenticates against GO DAIKIN universallogin endpoint to obtain JWT tokens.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime as dt, timedelta
import json
import logging

import aiohttp

LOGIN_URL = "https://qr5sjbuvhd.execute-api.ap-southeast-1.amazonaws.com/prod/universallogin"
EXPIRY_BUFFER = timedelta(minutes=5)

_LOGGER = logging.getLogger(__name__)


class AuthClient:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

        self._lock = asyncio.Lock()
        self._token: CognitoToken | None = None

    async def async_get_jwt_token(self) -> str:
        async with self._lock:
            if not self._token or self._token.expires_at <= dt.now() + EXPIRY_BUFFER:
                _LOGGER.debug("Fetching new token from universallogin")
                self._token = await self._login()
            return self._token.access_token

    async def async_get_user_id(self) -> str:
        await self.async_get_jwt_token()
        return self._token.user_id

    async def _login(self) -> CognitoToken:
        session = aiohttp.ClientSession()
        try:
            async with session.post(
                LOGIN_URL,
                json={"requestData": {"username": self.username, "password": self.password}},
            ) as resp:
                if resp.status == 401:
                    raise AuthError("Invalid credentials")
                resp.raise_for_status()
                data = await resp.json()
        finally:
            await session.close()

        if "IdToken" not in data:
            raise AuthError(f"Unexpected login response: {data}")

        id_token = data["IdToken"]
        user_id = _decode_jwt_sub(id_token)

        token = CognitoToken(
            id_token=id_token,
            access_token=data.get("AccessToken", ""),
            refresh_token=data.get("RefreshToken", ""),
            expires_at=dt.now() + timedelta(seconds=data.get("ExpiresIn", 3600)),
            user_id=user_id,
        )
        _LOGGER.debug("Login successful, token expires at %s", token.expires_at.isoformat())
        return token


def _decode_jwt_sub(token: str) -> str:
    payload = token.split(".")[1]
    payload += "=" * (4 - len(payload) % 4)
    data = json.loads(base64.b64decode(payload))
    return data["sub"]


class AuthError(Exception):
    pass


@dataclass
class CognitoToken:
    id_token: str
    access_token: str
    refresh_token: str
    expires_at: dt
    user_id: str = ""

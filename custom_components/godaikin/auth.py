"""
Authenticates against AWS Cognito to obtain JWT tokens for GO DAIKIN API access.
"""

from __future__ import annotations

import asyncio
import boto3
from dataclasses import dataclass
from datetime import datetime as dt, timedelta
import logging

REGION = "ap-southeast-1"
CLIENT_ID = "36f6piu770fotfscvhi3jb1vb7"
EXPIRY_BUFFER = timedelta(
    minutes=5
)  # refresh this much before expiry, in case of clock drift

_LOGGER = logging.getLogger(__name__)


class AuthClient:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

        self.get_jwt_token_semaphore = asyncio.Semaphore(1)
        self.session = boto3.Session()
        self.token: CognitoToken | None = None

    async def async_get_jwt_token(self) -> str:
        # Semaphore to prevent stampede on token init/refresh
        async with self.get_jwt_token_semaphore:
            return await asyncio.to_thread(self.get_jwt_token)

    def get_jwt_token(self) -> str:
        if not self.token:
            _LOGGER.debug("Initializing cognito token")
            self.token = self.init_cognito_token()

        if self.token.expires_at <= dt.now() + EXPIRY_BUFFER:
            _LOGGER.debug("Refreshing cognito token")
            self.token = self.refresh_jwt_token(self.token)

        return self.token.id_token

    def init_cognito_token(self) -> CognitoToken:
        cognito = self.session.client("cognito-idp", region_name=REGION)
        resp = cognito.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": self.username,
                "PASSWORD": self.password,
            },
        )

        auth = resp.get("AuthenticationResult")
        if not auth:
            _LOGGER.error("Authentication failed - no AuthenticationResult received")
            raise AuthError(
                "Did not receive AuthenticationResult (auth failed or unhandled challenge)."
            )

        token = CognitoToken(
            access_token=auth["AccessToken"],
            id_token=auth["IdToken"],
            refresh_token=auth["RefreshToken"],
            expires_at=dt.now() + timedelta(seconds=auth["ExpiresIn"]),
        )
        _LOGGER.debug(
            "Cognito authentication successful, expires at %s",
            token.expires_at.isoformat(),
        )

        return token

    def refresh_jwt_token(self, token: CognitoToken) -> CognitoToken:
        cognito = self.session.client("cognito-idp", region_name=REGION)
        resp = cognito.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={
                "REFRESH_TOKEN": token.refresh_token,
            },
        )

        auth = resp.get("AuthenticationResult")
        if not auth:
            _LOGGER.error("Token refresh failed - no AuthenticationResult received")
            raise AuthError(
                "Did not receive AuthenticationResult (refresh failed or unhandled challenge)."
            )

        token = CognitoToken(
            access_token=auth["AccessToken"],
            id_token=auth["IdToken"],
            refresh_token=token.refresh_token,  # reuse the prior refresh token
            expires_at=dt.now() + timedelta(seconds=auth["ExpiresIn"]),
        )
        _LOGGER.debug(
            "Cognito token refresh successful, expires at %s",
            token.expires_at.isoformat(),
        )

        return token


class AuthError(Exception):
    pass


@dataclass
class CognitoToken:
    access_token: str
    id_token: str
    refresh_token: str
    expires_at: dt

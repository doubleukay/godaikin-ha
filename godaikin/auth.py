"""
Authenticates against AWS Cognito to obtain JWT tokens for GO DAIKIN API access.
"""

from __future__ import annotations

import aioboto3
from dataclasses import dataclass
from datetime import datetime as dt, timedelta
import structlog

REGION = "ap-southeast-1"
CLIENT_ID = "36f6piu770fotfscvhi3jb1vb7"
EXPIRY_BUFFER = timedelta(
    minutes=5
)  # refresh this much before expiry, in case of clock drift

logger = structlog.get_logger(__name__)


class AuthClient:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

        self.session = aioboto3.Session()
        self.token: CognitoToken | None = None

    async def get_jwt_token(self) -> str:
        if not self.token:
            logger.debug("Initializing cognito token")
            self.token = await self.init_cognito_token()

        if self.token.expires_at <= dt.now() + EXPIRY_BUFFER:
            logger.debug("Refreshing cognito token")
            self.token = await self.refresh_jwt_token(self.token)

        return self.token.id_token

    async def init_cognito_token(self) -> CognitoToken:
        async with self.session.client("cognito-idp", region_name=REGION) as cognito:  # type: ignore
            resp = await cognito.initiate_auth(
                ClientId=CLIENT_ID,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={
                    "USERNAME": self.username,
                    "PASSWORD": self.password,
                },
            )

            auth = resp.get("AuthenticationResult")
            if not auth:
                logger.error("Authentication failed - no AuthenticationResult received")
                raise AuthError(
                    "Did not receive AuthenticationResult (auth failed or unhandled challenge)."
                )

            token = CognitoToken(
                access_token=auth["AccessToken"],
                id_token=auth["IdToken"],
                refresh_token=auth["RefreshToken"],
                expires_at=dt.now() + timedelta(seconds=auth["ExpiresIn"]),
            )
            logger.debug(
                "Cognito authentication successful",
                expires_at=token.expires_at.isoformat(),
            )

            return token

    async def refresh_jwt_token(self, token: CognitoToken) -> CognitoToken:
        async with self.session.client("cognito-idp", region_name=REGION) as cognito:  # type: ignore
            resp = await cognito.initiate_auth(
                ClientId=CLIENT_ID,
                AuthFlow="REFRESH_TOKEN_AUTH",
                AuthParameters={
                    "REFRESH_TOKEN": token.refresh_token,
                },
            )

            auth = resp.get("AuthenticationResult")
            if not auth:
                logger.error("Token refresh failed - no AuthenticationResult received")
                raise AuthError(
                    "Did not receive AuthenticationResult (refresh failed or unhandled challenge)."
                )

            token = CognitoToken(
                access_token=auth["AccessToken"],
                id_token=auth["IdToken"],
                refresh_token=token.refresh_token,  # reuse the prior refresh token
                expires_at=dt.now() + timedelta(seconds=auth["ExpiresIn"]),
            )
            logger.debug(
                "Cognito token refresh successful",
                expires_at=token.expires_at.isoformat(),
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

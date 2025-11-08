"""Config flow for GO DAIKIN integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .api import ApiClient
from .auth import AuthClient, AuthError
from .const import CONF_MOLD_PROOF_DURATION, DEFAULT_MOLD_PROOF_DURATION, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    auth = AuthClient(username=data[CONF_USERNAME], password=data[CONF_PASSWORD])

    try:
        # Try to authenticate
        await auth.get_jwt_token()

        # Try to fetch air conditioners
        api = ApiClient(auth)
        airconds = await api.get_airconds()

        if not airconds:
            raise NoAirConditionersFound()

    except AuthError as err:
        raise InvalidAuth() from err
    except Exception as err:
        _LOGGER.exception("Unexpected error during authentication")
        raise CannotConnect() from err

    # Return info that you want to store in the config entry.
    return {"title": f"GO DAIKIN ({data[CONF_USERNAME]})"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GO DAIKIN."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except NoAirConditionersFound:
                errors["base"] = "no_airconds"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create unique ID from username
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class NoAirConditionersFound(HomeAssistantError):
    """Error to indicate no air conditioners were found."""


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for GO DAIKIN."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_MOLD_PROOF_DURATION,
                        default=self.config_entry.options.get(
                            CONF_MOLD_PROOF_DURATION, DEFAULT_MOLD_PROOF_DURATION
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=180)),
                }
            ),
        )

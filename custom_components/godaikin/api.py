"""
API Client for interacting with the GO DAIKIN cloud service.
"""

import asyncio
from datetime import datetime as dt, timedelta
import aiohttp
import logging

from .auth import AuthClient
from .types import *

BASE_URL = "https://jm41kogy2b.execute-api.ap-southeast-1.amazonaws.com/prod/"

_LOGGER = logging.getLogger(__name__)


class ApiClient:
    def __init__(self, auth: AuthClient):
        self.auth = auth

        self.airconds_by_unique_id: dict[UniqueID, Aircond] = {}
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))

    async def _api_request(self, endpoint: str, payload: dict) -> dict:
        jwt_token = await self.auth.async_get_jwt_token()
        async with self.session.post(
            f"{BASE_URL}{endpoint}",
            json=payload,
            headers={"authorization": jwt_token},
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_airconds(self) -> list[Aircond]:
        _LOGGER.debug("Getting airconds")

        user_id = await self.auth.async_get_user_id()
        response_data = await self._api_request(
            "gethomepage",
            {
                "requestData": {
                    "type": 1,
                    "userID": user_id,
                }
            },
        )

        airconds = [
            Aircond.from_api(aircond_data)
            for aircond_data in response_data.get("data", [])
        ]
        self.airconds_by_unique_id = {a.unique_id: a for a in airconds}

        return airconds

    async def get_shadow_state(self, aircond: Aircond) -> ShadowState:
        _LOGGER.debug("Getting shadow state for %s", aircond.unique_id)

        await self._set_desired_state(aircond.unique_id)
        response_data = await self._api_request(
            "publishdevicestate",
            {
                "requestData": {
                    "type": 1,
                    "username": self.auth.username,
                    "thingName": aircond.ThingName,
                    "key": aircond.shadowState.key,
                }
            },
        )
        shadow_state = ShadowState.from_dict(response_data)

        return shadow_state

    async def set_mode(self, unique_id: UniqueID, mode: AircondMode):
        _LOGGER.info("Setting mode %s for %s", mode.value, unique_id)

        await self._set_desired_state(
            unique_id,
            Set_OnOff=1,
            Set_Mode=mode.value,
        )

    async def set_state(
        self,
        unique_id: UniqueID,
        *,
        on: bool,
        mode: AircondMode | None = None,
        fan: FanSpeed | None = None,
    ):
        """Set power and optionally mode and fan speed in one request."""
        _LOGGER.info(
            "Setting state on=%s mode=%s fan=%s for %s",
            on,
            mode.value if mode is not None else None,
            fan.value if fan is not None else None,
            unique_id,
        )

        state: dict[str, int] = {"Set_OnOff": int(on)}
        if mode is not None:
            state["Set_Mode"] = mode.value
        if fan is not None:
            state["Set_Fan"] = fan.value

        await self._set_desired_state(unique_id, **state)

    async def set_preset(self, unique_id: UniqueID, preset: AircondPreset):
        _LOGGER.info("Setting preset %s for %s", preset.value, unique_id)

        default_settings = dict(
            Set_Breeze=0,
            Set_Ecoplus=0,
            Set_Silent=0,
            Set_Sleep=0,
            Set_SmEcomax=0,
            Set_SmSleepplus=0,
            Set_SmPwrfulplus=0,
            Set_Turbo=0,
        )

        match preset:
            case AircondPreset.NONE:
                pass
            case AircondPreset.COMFORT:
                default_settings["Set_Breeze"] = 1
            case AircondPreset.ECO:
                default_settings["Set_Ecoplus"] = 1
                default_settings["Set_SmEcomax"] = 0
            case AircondPreset.BOOST:
                default_settings["Set_Silent"] = 0
                default_settings["Set_Turbo"] = 1
            case AircondPreset.SLEEP:
                default_settings["Set_Sleep"] = 1
                default_settings["Set_SmSleepplus"] = 0

        await self._set_desired_state(unique_id, **default_settings)

    async def set_fan_mode(self, unique_id: UniqueID, fan: FanSpeed):
        _LOGGER.info("Setting fan mode %s for %s", fan.value, unique_id)

        await self._set_desired_state(
            unique_id,
            Set_Fan=fan.value,
        )

    async def set_swing(
        self, unique_id: UniqueID, swing: AircondSwing, horizontal: bool = False
    ):
        _LOGGER.info(
            "Setting swing %s (horizontal=%s) for %s",
            swing.value,
            horizontal,
            unique_id,
        )

        if horizontal:
            await self._set_desired_state(
                unique_id,
                Set_LRLvr=swing.value,
            )
        else:
            await self._set_desired_state(
                unique_id,
                Set_Swing=1 if swing == AircondSwing.AUTO else 0,
                Set_UDLvr=swing.value,
            )

    async def set_temperature(self, unique_id: UniqueID, temperature: int):
        _LOGGER.info("Setting temperature %s for %s", temperature, unique_id)

        await self._set_desired_state(
            unique_id,
            Set_Temp=temperature,
        )

    async def turn_off(self, unique_id: UniqueID):
        _LOGGER.info("Turning off %s", unique_id)

        await self._set_desired_state(unique_id, Set_OnOff=0)

    async def turn_on(self, unique_id: UniqueID):
        _LOGGER.info("Turning on %s", unique_id)

        await self._set_desired_state(unique_id, Set_OnOff=1)

    async def set_status_led(self, unique_id: UniqueID, on: bool):
        _LOGGER.info("Setting status LED %s for %s", on, unique_id)

        if on:
            await self._set_desired_state(unique_id, Set_LEDOff=0, Set_PwrInd=1)
        else:
            await self._set_desired_state(unique_id, Set_LEDOff=1, Set_PwrInd=0)

    async def _set_desired_state(self, unique_id: UniqueID, **state):
        aircond = self.airconds_by_unique_id[unique_id]

        response_data = await self._api_request(
            "publishdevicestate",
            {
                "requestData": {
                    "type": 3,
                    "username": self.auth.username,
                    "thingName": aircond.ThingName,
                    "key": aircond.shadowState.key,
                    "payload": {"state": {"desired": state}},
                }
            },
        )
        _LOGGER.debug(
            "Set state request: ac_name=%s, unique_id=%s, state=%s",
            aircond.ACName,
            unique_id,
            state,
        )
        _LOGGER.debug(
            "Set state response: ac_name=%s, unique_id=%s, response=%s",
            aircond.ACName,
            unique_id,
            response_data,
        )

    async def get_total_energy_today(self, aircond: Aircond) -> float:
        # NOTE: unused for now - getacgraphdata API isn't timely with new data. Kept for reference.
        today = dt.now()

        response_data = []

        # mainly to refresh the data...
        for x in (1, 2):
            monday_this_week = today - timedelta(days=today.weekday())
            sunday_this_week = monday_this_week + timedelta(days=6)
            week = today.isocalendar().week

            payload = {
                "requestData": {
                    "type": str(x),
                    "email": self.auth.username,
                    "day": "weekly",
                    "thingName": aircond.ThingName,
                    "passDate": monday_this_week.strftime("%Y-%m-%d"),
                    "date": sunday_this_week.strftime("%Y-%m-%d"),
                    "lastData": "N",
                    "week": week,
                }
            }
            _LOGGER.debug("payload for getacgraphdata: %s", payload)

            response_data = await self._api_request("getacgraphdata", payload)
            await asyncio.sleep(1)

        for x in (1, 2):
            response_data = await self._api_request(
                "getacgraphdata",
                {
                    "requestData": {
                        "type": str(x),
                        "email": self.auth.username,
                        "day": "daily",
                        "thingName": aircond.ThingName,
                        "passDate": today.strftime("%Y-%m-%d"),
                        "date": today.strftime("%Y-%m-%d"),
                        "lastData": "Y",
                    }
                },
            )
            """
            [
                {"updatedOn": "0:00", "kWh": "0.1000"},
                {"updatedOn": "1:00", "kWh": "0.0530"},
                ...
            ]
            """

        _LOGGER.debug("energy data for today: %s", response_data)

        if not response_data:
            return 0.0

        total_energy_today = sum(float(entry["kWh"]) for entry in response_data)

        return total_energy_today


def print_aircond(aircond: Aircond):
    print("\nDetailed Information:")
    print(f"  🏠 Name: {aircond.ACName}")
    print(f"  🌐 IP: {aircond.IP}")
    print(f"  ⚡ Power: {'ON' if aircond.is_on else 'OFF'}")
    print(f"  ⚡ Power usage: {aircond.shadowState.Sta_ODPwrCon}W")
    print(f"  🌡️  Mode: {aircond.mode}")
    print(f"  📊 Current Temperature: {aircond.current_temp}°C")
    print(f"  🎯 Target Temperature: {aircond.target_temp}°C")
    print(f"  💨 Fan Speed: {aircond.fan_speed}")
    print(f"  🔄 Swing: {'Enabled' if aircond.swing_enabled else 'Disabled'}")
    print(f"  📅 Plan Expires: {aircond.plan_expired_date}")
    print(f"  📅 Subscription Started: {aircond.subscription_start_date}")
    print(f"  🏭 Manufacturer: {aircond.manufacturer}")

    if aircond.shadowState:
        print(f"\nShadow State Info:")
        print(f"  🔧 Version: {aircond.shadowState.version}")
        print(f"  📊 State Version: {aircond.shadowState.shadowStateVersion}")
        print(f"  🕒 Last Updated: {aircond.shadowState.updatedOn}")
        print(f"  💧 Indoor RH: {aircond.shadowState.Sta_IDRh}")
        print(f"  🌡️  Indoor Coil Temp: {aircond.shadowState.Sta_IDCoilTemp}°C")
        print(f"  🌡️  Outdoor Air Temp: {aircond.shadowState.Sta_ODAirTemp}°C")
        print(f"  ⚠️  Error Code: {aircond.shadowState.Sta_ErrCode}")

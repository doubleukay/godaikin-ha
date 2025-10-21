"""
API Client for interacting with the GO DAIKIN cloud service.
"""

import asyncio
from datetime import datetime as dt, timedelta
import httpx
import structlog

from .auth import AuthClient
from .types import *

BASE_URL = "https://c7zkf7l933.execute-api.ap-southeast-1.amazonaws.com/prod/"

logger = structlog.get_logger(__name__)


class ApiClient:
    def __init__(self, auth: AuthClient):
        self.auth = auth

        self.airconds_by_unique_id: dict[UniqueID, Aircond] = {}
        self.httpx = httpx.AsyncClient()

    async def _api_request(self, endpoint: str, payload: dict) -> dict:
        jwt_token = await self.auth.get_jwt_token()
        resp = await self.httpx.post(
            f"{BASE_URL}{endpoint}",
            json=payload,
            headers={"authorization": jwt_token},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_airconds(self) -> list[Aircond]:
        logger.debug("Getting airconds")

        response_data = await self._api_request(
            "gethomepageinfowithsubscription",
            {
                "requestData": {
                    "type": 1,
                    "value": self.auth.username,
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
        logger.debug("Getting shadow state", unique_id=aircond.unique_id)

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
        logger.info("Setting mode", unique_id=unique_id, mode=mode.value)

        await self._set_desired_state(
            unique_id,
            Set_OnOff=1,
            Set_Mode=mode.value,
        )

    async def set_preset(self, unique_id: UniqueID, preset: AircondPreset):
        logger.info("Setting preset", unique_id=unique_id, preset=preset.value)

        match preset:
            case AircondPreset.NONE:
                await self._set_desired_state(
                    unique_id,
                    Set_Breeze=0,
                    Set_Ecoplus=0,
                    Set_Silent=0,
                    Set_Sleep=0,
                    Set_SmEcomax=0,
                    Set_SmSleepplus=0,
                    Set_SmPwrfulplus=0,
                    Set_Turbo=0,
                )
            case AircondPreset.COMFORT:
                await self._set_desired_state(
                    unique_id,
                    Set_Breeze=1,
                    Set_LRLvr=0,
                    Set_Swing=0,
                )
            case AircondPreset.ECO:
                await self._set_desired_state(
                    unique_id,
                    Set_Ecoplus=1,
                    Set_SmEcomax=0,
                )
            case AircondPreset.BOOST:
                await self._set_desired_state(
                    unique_id,
                    Set_Silent=0,
                    Set_Turbo=1,
                )
            case AircondPreset.SLEEP:
                await self._set_desired_state(
                    unique_id,
                    Set_Sleep=1,
                    SetSmSleepplus=0,
                )

    async def set_fan_mode(self, unique_id: UniqueID, fan: FanSpeed):
        logger.info("Setting fan mode", unique_id=unique_id, fan=fan.value)

        await self._set_desired_state(
            unique_id,
            Set_Fan=fan.value,
        )

    async def set_swing(
        self, unique_id: UniqueID, swing: AircondSwing, horizontal: bool = False
    ):
        logger.info(
            "Setting swing",
            unique_id=unique_id,
            swing=swing.value,
            horizontal=horizontal,
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
        logger.info("Setting temperature", unique_id=unique_id, temperature=temperature)

        await self._set_desired_state(
            unique_id,
            Set_Temp=temperature,
        )

    async def turn_off(self, unique_id: UniqueID):
        logger.info("Turning off", unique_id=unique_id)

        await self._set_desired_state(unique_id, Set_OnOff=0)

    async def turn_on(self, unique_id: UniqueID):
        logger.info("Turning on", unique_id=unique_id)

        await self._set_desired_state(unique_id, Set_OnOff=1)

    async def set_status_led(self, unique_id: UniqueID, on: bool):
        logger.info("Setting status LED", unique_id=unique_id, on=on)

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
        logger.debug(
            "Set state request",
            ac_name=aircond.ACName,
            unique_id=unique_id,
            state=state,
        )
        logger.debug(
            "Set state response",
            ac_name=aircond.ACName,
            unique_id=unique_id,
            response=response_data,
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
            logger.debug("payload for getacgraphdata", payload=payload)

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

        logger.debug("energy data for today", data=response_data)

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

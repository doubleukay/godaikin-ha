"""
Controller for bridging between the GO DAIKIN API and MQTT.
"""

import aiomqtt
import asyncio
import json
import structlog

from .api import ApiClient
from .discovery import make_discovery_messages
from .energy import EnergyCounter
from .mqtt import BRIDGE_AVAILABILITY_TOPIC, MQTT_PREFIX
from .types import *


logger = structlog.get_logger(__name__)


class Controller:
    def __init__(self, api: ApiClient, mqtt: aiomqtt.Client, refresh_interval: int):
        self.api = api
        self.mqtt = mqtt
        self.refresh_interval = refresh_interval

        self.energy = EnergyCounter()
        self.mqtt_topics_by_unique_id: dict[UniqueID, AircondMqttTopics] = {}
        self.preempt_state_refresh = asyncio.Event()
        self.payload_cache_by_topic: dict[str, str] = {}

    async def run(self):
        await self.publish_bridge_availability()

        await asyncio.gather(
            self.controller_loop(),
            self.message_loop(),
        )

    async def controller_loop(self):
        await self.publish_discovery()

        while True:
            await self.refresh_state()

            try:
                await asyncio.wait_for(
                    self.preempt_state_refresh.wait(),
                    timeout=self.refresh_interval,
                )
                self.preempt_state_refresh.clear()
            except asyncio.TimeoutError:
                pass

    async def publish_bridge_availability(self):
        """
        Announce that the MQTT bridge is online
        """

        await self.mqtt_publish(BRIDGE_AVAILABILITY_TOPIC, "online", qos=1, retain=True)

    async def message_loop(self):
        topics = [f"{MQTT_PREFIX}/+/set/+"]

        for t in topics:
            await self.mqtt.subscribe(t, qos=1)

        async for message in self.mqtt.messages:
            await self.handle_message(message)

    async def handle_message(self, message: aiomqtt.Message):
        if isinstance(message.payload, bytes):
            payload = message.payload.decode()
        else:
            payload = str(message.payload)

        _, unique_id, action, key = message.topic.value.split("/")

        match action:
            case "set":
                await self.handle_set_message(key, UniqueID(unique_id), payload)
            case _:
                logger.warning(
                    "Unknown MQTT action",
                    action=action,
                    unique_id=unique_id,
                    key=key,
                    payload=payload,
                )

    async def handle_set_message(self, set_key: str, unique_id: UniqueID, payload: str):
        logger.debug(
            "Handling set message",
            unique_id=unique_id,
            set_key=set_key,
            payload=payload,
        )

        match set_key:
            case "mode":
                await self.handle_set_mode(unique_id, payload)
            case "fan_mode":
                await self.handle_set_fan_mode(unique_id, payload)
            case "preset_mode":
                await self.handle_set_preset_mode(unique_id, payload)
            case "temperature":
                temp = int(float(payload))
                await self.handle_set_temperature(unique_id, temp)
            case "swing_mode":
                await self.handle_set_swing(unique_id, payload)
            case "swing_horizontal_mode":
                await self.handle_set_swing_horizontal(unique_id, payload)

        # Preempt a state refresh so that changes are reflected immediately in HA
        self.preempt_state_refresh.set()

    async def handle_set_mode(self, unique_id: UniqueID, mode: str):
        logger.info("Handling set mode", unique_id=unique_id, mode=mode)

        match mode:
            case "off":
                await self.api.turn_off(unique_id)
            case "cool":
                await self.api.set_mode(unique_id, mode=AircondMode.COOL)
            case "dry":
                await self.api.set_mode(unique_id, mode=AircondMode.DRY)
            case "fan_only":
                await self.api.set_mode(unique_id, mode=AircondMode.FAN_ONLY)
            case _:
                logger.warning("Unknown mode", mode=mode)

    async def handle_set_preset_mode(self, unique_id: UniqueID, preset_mode: str):
        logger.info(
            "Handling set preset mode", unique_id=unique_id, preset_mode=preset_mode
        )

        match preset_mode:
            case "boost":
                preset = AircondPreset.BOOST
            case "comfort":
                preset = AircondPreset.COMFORT
            case "eco":
                preset = AircondPreset.ECO
            case "none":
                preset = AircondPreset.NONE
            case "sleep":
                preset = AircondPreset.SLEEP
            case _:
                logger.warning("Unknown preset mode", preset_mode=preset_mode)
                return

        await self.api.set_preset(unique_id, preset=preset)

    async def handle_set_temperature(self, unique_id: UniqueID, temperature: int):
        logger.info(
            "Handling set temperature", unique_id=unique_id, temperature=temperature
        )
        await self.api.set_temperature(unique_id, temperature=temperature)

    async def handle_set_fan_mode(self, unique_id: UniqueID, fan_mode: str):
        logger.info("Handling set fan mode", unique_id=unique_id, fan_mode=fan_mode)

        fan = FanSpeed[fan_mode.upper()]
        await self.api.set_fan_mode(unique_id, fan=fan)

    async def handle_set_swing(self, unique_id: UniqueID, swing: str):
        logger.info("Handling set swing", unique_id=unique_id, swing=swing)

        swing_ = AircondSwing[swing.upper()]
        await self.api.set_swing(unique_id, swing=swing_, horizontal=False)

    async def handle_set_swing_horizontal(self, unique_id: UniqueID, swing: str):
        logger.info("Handling set swing horizontal", unique_id=unique_id, swing=swing)

        swing_ = AircondSwing[swing.upper()]
        await self.api.set_swing(unique_id, swing=swing_, horizontal=True)

    async def publish_discovery(self):
        logger.info("Publishing discovery messages")

        airconds = await self.api.get_airconds()
        for aircond in airconds:
            discovery_messages = make_discovery_messages(
                aircond,
                self.get_mqtt_topics(aircond),
            )
            for msg in discovery_messages:
                await self.mqtt_publish(msg.topic, msg.payload, qos=1, retain=True)

    def get_mqtt_topics(self, aircond: Aircond):
        # Cache these MQTT topics to avoid reevaluating them multiple times
        if aircond.unique_id not in self.mqtt_topics_by_unique_id:
            self.mqtt_topics_by_unique_id[aircond.unique_id] = (
                AircondMqttTopics.from_aircond(aircond)
            )

        return self.mqtt_topics_by_unique_id[aircond.unique_id]

    async def refresh_state(self):
        logger.debug("Refreshing state")

        airconds = await self.api.get_airconds()
        for aircond in airconds:
            await self.publish_aircond_state(aircond)
            await self.publish_sensor_state(aircond)

    async def refresh_aircond_state(self):
        logger.debug("Refreshing air conditioner states")

        for aircond in await self.api.get_airconds():
            await self.publish_aircond_state(aircond)
            await self.publish_sensor_state(aircond)

    async def publish_aircond_state(self, aircond: Aircond):
        topics = self.mqtt_topics_by_unique_id[aircond.unique_id]

        if not aircond.is_on:
            mode = "off"
        else:
            mode = AircondMode(aircond.shadowState.Set_Mode).name.lower()

        if aircond.shadowState.Set_Turbo:
            preset_mode = "boost"
        elif aircond.shadowState.Set_Breeze:
            preset_mode = "comfort"
        elif aircond.shadowState.Set_Ecoplus:
            preset_mode = "eco"
        elif aircond.shadowState.Set_Sleep:
            preset_mode = "sleep"
        else:
            preset_mode = "none"

        fan_mode = FanSpeed(aircond.shadowState.Set_Fan)
        swing_mode = AircondSwing(aircond.shadowState.Set_UDLvr)
        swing_horizontal_mode = AircondSwing(aircond.shadowState.Set_LRLvr)

        payload = {
            "mode": mode,
            "temperature": aircond.shadowState.Set_Temp,
            "current_temperature": aircond.shadowState.Sta_IDRoomTemp,
            "fan_mode": fan_mode.name.lower(),
            "swing_mode": swing_mode.name.title(),
            "swing_horizontal_mode": swing_horizontal_mode.name.title(),
            "preset_mode": preset_mode,
        }
        await self.mqtt_publish(
            topics.status, payload, qos=1, retain=True, only_if_changed=True
        )

        availability_payload = "online" if aircond.is_connected else "offline"
        await self.mqtt_publish(
            topics.availability,
            availability_payload,
            qos=1,
            retain=True,
            only_if_changed=True,
        )

    async def publish_sensor_state(self, aircond: Aircond):
        topics = self.mqtt_topics_by_unique_id[aircond.unique_id]

        energy_usage = self.energy.accumulate_energy_usage_for_aircond(aircond)

        payload = {
            "Sta_ODPwrCon": aircond.shadowState.Sta_ODPwrCon,
            "Sta_IDRoomTemp": aircond.shadowState.Sta_IDRoomTemp,
            "Sta_ODAirTemp": aircond.shadowState.Sta_ODAirTemp,
            "energy": round(
                energy_usage, 2
            ),  # round to 2 decimal places to reduce mqtt chattiness
        }

        await self.mqtt_publish(
            topics.sensor, payload, qos=1, retain=True, only_if_changed=True
        )

    async def mqtt_publish(
        self,
        topic: str,
        payload: dict | str,
        qos: int,
        retain: bool,
        only_if_changed: bool = False,
    ):
        """
        Publish to MQTT only if the payload has changed since the last publish; mainly for state changes.
        """

        if isinstance(payload, dict):
            payload_str = json.dumps(payload)
        else:
            payload_str = payload

        if only_if_changed:
            # Check if payload has changed, if so, publish. Otherwise skip to reduce MQTT chattiness.
            cached_payload = self.payload_cache_by_topic.get(topic)
            if cached_payload == payload_str:
                return
            else:
                self.payload_cache_by_topic[topic] = payload_str

        logger.debug("Publishing to MQTT", topic=topic, payload=payload)
        await self.mqtt.publish(topic, payload_str, qos=qos, retain=retain)

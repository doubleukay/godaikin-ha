"""
MQTT discovery message generation for Home Assistant.
"""

from .mqtt import BRIDGE_AVAILABILITY_TOPIC
from .types import *


def make_discovery_messages(
    aircond: Aircond, topics: AircondMqttTopics
) -> list[DiscoveryMessage]:
    return make_device_discovery_messages(
        aircond, topics
    ) + make_sensor_discovery_messages(aircond, topics)


def make_device_discovery_messages(
    aircond: Aircond, topics: AircondMqttTopics
) -> list[DiscoveryMessage]:
    payload = {
        "name": None,
        "object_id": aircond.object_id,
        "unique_id": aircond.unique_id,
        "modes": HVAC_MODES,
        "mode_command_topic": topics.cmd_mode,
        "mode_state_topic": topics.status,
        "mode_state_template": "{{ value_json.mode }}",
        "temperature_command_topic": topics.cmd_temp,
        "temperature_state_topic": topics.status,
        "temperature_state_template": "{{ value_json.temperature }}",
        "current_temperature_topic": topics.status,
        "current_temperature_template": "{{ value_json.current_temperature }}",
        "fan_modes": FAN_MODES,
        "fan_mode_command_topic": topics.cmd_fan,
        "fan_mode_state_topic": topics.status,
        "fan_mode_state_template": "{{ value_json.fan_mode }}",
        "swing_modes": SWING_MODES,
        "swing_mode_command_topic": topics.cmd_swing,
        "swing_mode_state_topic": topics.status,
        "swing_mode_state_template": "{{ value_json.swing_mode }}",
        "swing_horizontal_modes": SWING_MODES,
        "swing_horizontal_mode_command_topic": topics.cmd_swing_horizontal,
        "swing_horizontal_mode_state_topic": topics.status,
        "swing_horizontal_mode_state_template": "{{ value_json.swing_horizontal_mode }}",
        "preset_modes": PRESET_MODES,
        "preset_mode_command_topic": topics.cmd_preset,
        "preset_mode_state_topic": topics.status,
        "preset_mode_value_template": "{{ value_json.preset_mode }}",
        "temp_step": TEMP_STEP_AND_PRECISION,
        "min_temp": MIN_TEMP,
        "max_temp": MAX_TEMP,
        "precision": TEMP_STEP_AND_PRECISION,
        "icon": "mdi:air-conditioner",
        "qos": 0,
        "retain": False,
        "availability_mode": "all",
        "availability": [
            {"topic": BRIDGE_AVAILABILITY_TOPIC},
            {"topic": topics.availability},
        ],
        "device": {
            "identifiers": [aircond.unique_id],
            "manufacturer": "Daikin",
            "model": "GO DAIKIN",
            "name": aircond.ACName,
            "connections": [["mac", aircond.mac_address]],
        },
    }

    return [DiscoveryMessage(topic=topics.discovery, payload=payload)]


def make_sensor_discovery_messages(
    aircond: Aircond, topics: AircondMqttTopics
) -> list[DiscoveryMessage]:

    messages: list[DiscoveryMessage] = []

    for (
        sensor_name,
        sensor_field,
        sensor_unit,
        sensor_class,
        state_class,
    ) in [
        (
            "Power",
            "Sta_ODPwrCon",
            "W",
            "power",
            "measurement",
        ),
        (
            "Indoor temperature",
            "Sta_IDRoomTemp",
            "°C",
            "temperature",
            "measurement",
        ),
        (
            "Outdoor temperature",
            "Sta_ODAirTemp",
            "°C",
            "temperature",
            "measurement",
        ),
        (
            "Energy",
            "energy",
            "kWh",
            "energy",
            "total_increasing",
        ),
    ]:

        def _normalize_name(sensor_name: str) -> str:
            return sensor_name.lower().replace(" ", "_")

        sensor_norm_name = _normalize_name(sensor_name)

        sensor_discovery_topic = (
            f"{DISCOVERY_PREFIX}/sensor/{aircond.unique_id}/{sensor_norm_name}/config"
        )
        payload = {
            "name": sensor_name,
            "unique_id": f"{aircond.unique_id}_{sensor_norm_name}",
            "state_topic": topics.sensor,
            "value_template": "{{ value_json." + sensor_field + " }}",
            "state_class": state_class,
            "unit_of_measurement": sensor_unit,
            "device_class": sensor_class,
            "qos": 0,
            "retain": True,
            "availability_mode": "all",
            "availability": [
                {"topic": BRIDGE_AVAILABILITY_TOPIC},
                {"topic": topics.availability},
            ],
            "device": {
                "identifiers": [aircond.unique_id],
            },
        }

        messages.append(DiscoveryMessage(topic=sensor_discovery_topic, payload=payload))

    return messages

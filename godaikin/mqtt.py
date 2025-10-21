import aiomqtt
import structlog

MQTT_PREFIX = "godaikin"
DISCOVERY_PREFIX = "homeassistant"
BRIDGE_AVAILABILITY_TOPIC = f"{MQTT_PREFIX}/bridge/availability"

logger = structlog.get_logger(__name__)


def init_mqtt(host: str, port: int, username: str, password: str) -> aiomqtt.Client:
    return aiomqtt.Client(
        hostname=host,
        port=port,
        username=username,
        password=password,
        will=aiomqtt.Will(
            topic=BRIDGE_AVAILABILITY_TOPIC,
            payload="offline",
            qos=1,
            retain=True,
        ),
        keepalive=30,
    )

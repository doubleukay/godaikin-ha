import asyncio
import logging
import os
import structlog

from .api import ApiClient
from .auth import AuthClient
from .controller import Controller
from .mqtt import init_mqtt

logger = structlog.get_logger(__name__)


async def main():
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG)
    )

    logger.info("Starting GO DAIKIN integration")

    auth = AuthClient(
        username=os.environ["GODAIKIN_USERNAME"],
        password=os.environ["GODAIKIN_PASSWORD"],
    )
    api = ApiClient(auth)
    mqtt = init_mqtt(
        host=os.environ["MQTT_HOST"],
        port=int(os.environ["MQTT_PORT"]),
        username=os.environ["MQTT_USERNAME"],
        password=os.environ["MQTT_PASSWORD"],
    )

    async with mqtt:
        logger.debug("MQTT connected")

        controller = Controller(
            api,
            mqtt,
            refresh_interval=int(os.environ["REFRESH_INTERVAL"]),
        )
        await controller.run()


if __name__ == "__main__":
    asyncio.run(main())

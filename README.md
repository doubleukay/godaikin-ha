# GO DAIKIN unofficial integration with Home Assistant

## Features
- Auto-discover airconds in GO DAIKIN
- Cool/Dry/Fan modes
- Temperature sensor and setting
- Fan speeds
- Eco/Breeze/Powerful/Sleep preset modes
- Vertical and Horizontal fan swings
- Power and Energy sensors
- Status LED control

## Installation
[![Open your Home Assistant instance with the godaikin-ha repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fdoubleukay%2Fgodaikin-ha)

1. Install an MQTT broker and MQTT integration.
1. Add the repository to Home Assistant.
1. Install the add-on in the store.
1. Configure the add-on with your GO DAIKIN username and password.
1. Start the add-on. Check the add-on logs to see if API authentication and access are successful.
1. Devices and entities should be created automatically.

## License

Copyright 2025 Woon Wai Keen

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

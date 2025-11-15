# GO DAIKIN - Home Assistant Integration

A native Home Assistant integration for GO DAIKIN air conditioners. This integration communicates directly with the GO DAIKIN cloud API.

NOTE: This is an unofficial integration and is not affiliated with Daikin.

## Features
- Auto-discover air conditioners in GO DAIKIN
- Cool/Dry/Fan modes
- Temperature sensor and setting
- Fan speeds
- Eco/Breeze/Powerful/Sleep preset modes
- Vertical and Horizontal fan swings
- Power and Energy sensors
- Status LED control
- Simulated mold-proof

## Installation

### HACS (Recommended)
1. Open HACS in Home Assistant
2. Search for "GO DAIKIN" and install

### Manual Installation
1. Copy the `custom_components/godaikin` directory to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration
1. Go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "GO DAIKIN"
4. Enter your GO DAIKIN username (email) and password
5. Click Submit

Your air conditioners will be automatically discovered and added as devices.

## Entities

For each air conditioner, the following entities will be created:

### Climate Entity
- **Control**: HVAC mode (Off, Cool, Dry, Fan Only)
- **Temperature**: Set and view current/target temperatures
- **Fan Mode**: Auto, Low, Medium, High
- **Swing Mode**: Off, Auto, Step 1-5 (vertical and horizontal)
- **Preset Modes**: None, Boost, Comfort, Eco, Sleep (availability depends on unit capabilities)

### Sensors
- **Power**: Current power consumption (W)
- **Indoor Temperature**: Indoor room temperature (°C)
- **Outdoor Temperature**: Outdoor air temperature (°C)
- **Energy**: Total energy consumption (kWh). This counter resets every time HA restarts.

### Configuration
- **Mold-proof**: After the aircond is turned off, run it on fan mode for an hour to reduce mold and bacteria buildup. This is simulated and does not use Daikin's built-in mold-proof mode.
- **Status LED**: Control the air conditioner's status LED light (if supported)

## Troubleshooting

### Authentication Failed
- Verify your GO DAIKIN username (email) and password are correct
- Ensure your GO DAIKIN account is active and has active subscriptions

### No Air Conditioners Found
- Check that your air conditioners are properly registered in the GO DAIKIN app
- Ensure your GO DAIKIN subscription is active

### Entities Not Updating
- Check the integration logs in Settings → System → Logs
- Verify your internet connection

## Development

This integration uses the GO DAIKIN cloud API to control Daikin air conditioners. It authenticates via AWS Cognito and polls the API at regular intervals for updates.

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/doubleukay/godaikin-ha/issues).

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

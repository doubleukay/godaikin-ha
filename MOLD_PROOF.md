# Mold Proof Feature Implementation

## Overview
The mold proof feature emulates the traditional Daikin air conditioner mold prevention function. After turning off the AC from cool or dry mode, it automatically runs the fan at low speed for a configurable duration (default: 60 minutes) to dry out the indoor unit and prevent mold growth.

## Files Created/Modified

### New Files
1. **`mold_proof.py`** - MoldProofManager class that handles the mold proof logic
2. **`switch.py`** - Switch platform for per-device mold proof enable/disable

### Modified Files
1. **`const.py`** - Added mold proof constants and configuration keys
2. **`coordinator.py`** - Added mold_proof manager reference
3. **`__init__.py`** - Initialize mold proof manager and handle options updates
4. **`climate.py`** - Integrated mold proof into HVAC control logic
5. **`config_flow.py`** - Added options flow for global mold proof duration setting
6. **`strings.json`** - Added UI strings for mold proof configuration

## Features Implemented

### 1. Per-Device Enable/Disable
- Each air conditioner gets a **"Mold Proof"** switch entity (configuration entity)
- Toggle on/off to enable/disable mold proof for that specific device
- Switch shows current status (active/idle) and remaining time as attributes

### 2. Global Duration Setting
- Configure mold proof duration through integration options
- Default: 60 minutes
- Range: 1-180 minutes
- Access via: Integration settings → Options

### 3. Automatic Mold Proof Activation
When turning off the AC (via HVAC mode = OFF or turn_off service):
- **Only activates** if:
  - Mold proof is enabled for that device
  - AC is currently ON
  - AC is in COOL or DRY mode (not FAN_ONLY)
- **Activates by**:
  - Switching to FAN_ONLY mode
  - Setting fan speed to LOW
  - Starting a timer for the configured duration
- **State display**:
  - Climate entity shows as "OFF" even though fan is running
  - This matches the user expectation (they turned it off)

### 4. Interrupt Handling
Mold proof is automatically interrupted and cancelled when:
- Turning the AC back ON (restores both the previous mode and the previous fan speed)
- Changing HVAC mode (to COOL, DRY, or FAN_ONLY); the previous fan speed is restored
- Setting the temperature together with an HVAC mode
- Turning the AC OFF during mold proof (previous mode and fan speed are restored, then the AC is turned off; no new cycle is started)
- Disabling mold proof via the switch (previous mode and fan speed are restored and the AC is turned off)

Changing the fan speed during mold proof does not touch the device; the new
speed is remembered and applied when the cycle ends or the AC is turned on.

Every restore (turn on, mode change, OFF during a cycle, and the end-of-cycle
finish) is sent to the AC as a single atomic request carrying power, mode and
fan speed together, so there is no brief cooling burst at the end of a cycle and
a failed request never leaves the unit half-restored.

Commands for one AC (turn on/off, mode, fan, temperature) and the completion
timer are serialised per device, so a user command can never be overridden by
a completion that was already in progress.

### 5. Automatic Completion
After the configured duration:
- The previous mode and fan speed are restored and the AC is turned completely OFF in one single request
- Mold proof state is cleared only after that request succeeded
- If the cloud call fails, it is retried for as long as the integration is loaded, with exponential backoff (3, 6, 12 ... minutes, capped at 30 minutes); the cycle stays stored so a restart also finishes it
- Timer is cleaned up

## User Interface

### Switch Entity
```
Entity: switch.<aircond_name>_mold_proof
Name: <Aircond Name> Mold Proof
Category: Configuration
Icon: mdi:air-filter

Attributes:
- status: "active" | "idle"
- remaining_seconds: <int> (when active)
- remaining_minutes: <float> (when active)
```

### Integration Options
Go to: **Settings → Devices & Services → GO DAIKIN → Configure**
- **Mold Proof Duration**: 1-180 minutes (default: 60)

## How It Works

### Scenario 1: Normal Mold Proof
1. User has AC in COOL mode at 24°C, fan on AUTO
2. User turns OFF the AC (mold proof enabled)
3. **Behind the scenes**:
   - Saves current mode (COOL) and fan speed (AUTO)
   - Changes to FAN_ONLY mode, fan LOW
   - Starts 60-minute timer
4. **User sees**: AC shows as OFF
5. After 60 minutes: AC turns completely OFF

### Scenario 2: Interrupted Mold Proof
1. Mold proof is running (20 minutes remaining)
2. User turns AC back ON or changes mode to COOL
3. **Behind the scenes**:
   - Cancels mold proof timer
   - Restores previous fan speed (AUTO)
   - Changes to requested mode (COOL); for a plain turn on, restores the previous mode (COOL)
4. **User sees**: AC turns on normally

### Scenario 3: Disabled Mold Proof
1. Mold proof switch is OFF for this device
2. User turns OFF the AC
3. **Result**: AC turns off immediately (normal behavior)

## Technical Details

### MoldProofManager
```python
- set_duration(minutes: int) - Set global duration
- set_enabled(unique_id, enabled: bool) - Enable/disable per device
- is_enabled(unique_id) -> bool - Check if enabled
- is_active(unique_id) -> bool - Check if currently running
- start_mold_proof(unique_id, prev_mode, prev_fan) - Start operation
- get_state(unique_id) -> MoldProofState | None - Read the saved state (previous mode and fan speed)
- interrupt_mold_proof(unique_id) -> MoldProofState | None - End the cycle and return its state. Call it only after the device command for the user's request succeeded, and while holding the device lock (device_lock(unique_id)); if the command fails the cycle must stay in place
- get_remaining_time(unique_id) -> int - Get remaining seconds
```

### State Tracking
```python
@dataclass
class MoldProofState:
    unique_id: UniqueID
    start_time: datetime
    previous_mode: AircondMode
    previous_fan_speed: FanSpeed
    cancel_timer: callable | None
```

## Installation & Setup

1. **Copy files** to Home Assistant
2. **Restart** Home Assistant
3. **Configure** (optional):
   - Go to Integration → Options
   - Set desired mold proof duration
4. **Enable** per device:
   - Find switch entity for each AC
   - Turn on mold proof switch
5. **Use normally**:
   - Turn off AC as usual
   - Mold proof runs automatically

## Benefits

- **Prevents mold growth** in indoor unit
- **Extends AC lifespan** by keeping coils dry
- **Reduces odors** from mold and bacteria
- **Automatic operation** - no manual intervention needed
- **Flexible configuration** - enable only where needed
- **Non-intrusive** - appears as normal off to user

## Notes

- Mold proof only activates from COOL/DRY modes (not from FAN_ONLY)
- Fan speed is always set to LOW during mold proof (regardless of previous setting)
- Previous mode and fan speed are restored when interrupted (turn on, mode change, or off)
- Duration setting applies to all devices (global)
- Enable/disable is per-device (individual control)
- Settings and active cycles are stored per config entry.
- Migration from the old shared storage: the first config entry that reads the legacy shared storage after the upgrade records every config entry known at that moment in a `pending_entries` list inside it. Each pending entry that has no storage of its own imports the enabled-device list (so several accounts all upgrade, and an entry that could not load at first still imports when it does) and then removes itself from the list. The list is created at the very start of setup (before any network access that could fail), and also when an entry is deleted if it does not exist yet. Entries added later, including one re-added after a removal, are not in the list and never import old settings. Deleting an entry also removes it from the list; the legacy file is never created or deleted by the integration. A legacy file already marked `migrated` is never imported.
- If starting mold proof fails (the request may still have been applied, e.g. after a timeout), the cycle is kept stored and armed. Turning the AC OFF then restores the previous mode and fan speed and powers off in one request; if that also fails, the cycle's finish is retried within 3 minutes instead of waiting for the full duration.
- Active cycles are stored with an absolute UTC end time and survive integration reloads and Home Assistant restarts: the timer is re-armed for the remaining time, or, if the end time already passed, the AC is restored and turned off right after startup

If the cloud is completely unreachable when the AC is turned off during or after a mold proof cycle, Home Assistant shows OFF while the unit keeps running until a retry succeeds (3, 6, 12 ... minutes, capped at 30 minutes); the user gets a service error at the time of the request.

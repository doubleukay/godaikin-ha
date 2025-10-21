from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Optional, Dict, Any, NewType

from .mqtt import DISCOVERY_PREFIX, MQTT_PREFIX

UniqueID = NewType("UniqueID", str)

"""
Example API response
{
    "ACGroup": "All Units",
    "ACName": "bedroom",
    "IP": "192.168.1.137",
    "Logo": "5.png",
    "ThingName": "Daikin_4c50dd423066",
    "ThingType": "AC",
    "gatewayIP": "-",
    "groupIndex": -1,
    "guestPaired": 0,
    "isGooglePreferredDevice": 0,
    "isPreferredDevice": 0,
    "manufacturer": "Realtek",
    "planExpiredDate": "2027-01-04",
    "planID": "2",
    "qx": "15",
    "shadowState": {
        "Bar_AutoF": 0,
        "Bar_AutoM": 1,
        "Bar_CoolM": 0,
        "Bar_DryM": 0,
        "Bar_FanM": 0,
        "Bar_HeatM": 1,
        "Bar_LowF": 0,
        "Bar_Sleep": 0,
        "Bar_Swing": 0,
        "Bar_Timer": 0,
        "Ena_ACoilCln": 0,
        "Ena_Breeze": 1,
        "Ena_CKSwing": 0,
        "Ena_Cmode": 0,
        "Ena_CoilCln": 0,
        "Ena_DOTA": 0,
        "Ena_Ecoplus": 1,
        "Ena_Icoolx": 0,
        "Ena_LEDOff": 1,
        "Ena_LRStep": 1,
        "Ena_LRSwing": 1,
        "Ena_MDemand": 0,
        "Ena_MoSupp": 0,
        "Ena_PwrInd": 1,
        "Ena_Sense": 0,
        "Ena_Silent": 1,
        "Ena_SmDrift": 0,
        "Ena_SmEcomax": 0,
        "Ena_SmPerDiag": 0,
        "Ena_SmPwrfulplus": 0,
        "Ena_SmSleepplus": 0,
        "Ena_Streamer": 0,
        "Ena_Turbo": 1,
        "Ena_UDStep": 1,
        "Ena_eLight": 0,
        "Inf_IDAlgo": 0,
        "Inf_IDCap": 26,
        "Inf_IDType": 1,
        "Inf_MaxPL": 0,
        "Inf_MinPL": 0,
        "Inf_NSVer": 4,
        "Inf_ODPwrCon": 1,
        "Inf_Prod": 0,
        "Inf_ProdBrand": 0,
        "Inf_ProdSys": 0,
        "Set_ACoilCln": 0,
        "Set_Breeze": 0,
        "Set_CKSwing": 0,
        "Set_CoilCln": 0,
        "Set_CommStep": 0,
        "Set_Ecoplus": 0,
        "Set_Fan": 2,
        "Set_FanExtend": 0,
        "Set_Icoolx": 0,
        "Set_Ion": 0,
        "Set_LEDOff": 0,
        "Set_LRLvr": 3,
        "Set_MDemand": 0,
        "Set_MoSupp": 0,
        "Set_Mode": 2,
        "Set_OnOff": 1,
        "Set_PL": 0,
        "Set_Pdown": 0,
        "Set_PwrInd": 1,
        "Set_SancMode": 0,
        "Set_Sense": 0,
        "Set_Silent": 0,
        "Set_Sleep": 0,
        "Set_SmDrift": 0,
        "Set_SmEcomax": 0,
        "Set_SmPerDiag": 0,
        "Set_SmPwrfulplus": 0,
        "Set_SmSleepplus": 0,
        "Set_Streamer": 0,
        "Set_Swing": 1,
        "Set_Temp": 26,
        "Set_Turbo": 0,
        "Set_Turboplus": 0,
        "Set_UDLvr": 15,
        "Set_eLight": 0,
        "Sta_AutoM": 0,
        "Sta_Cmode": 0,
        "Sta_Cmode_C": 0,
        "Sta_CoilCln": 0,
        "Sta_CpOnOff": 0,
        "Sta_CpRT": 0,
        "Sta_DCBus": 320,
        "Sta_ErrCode": 0,
        "Sta_Faht": 0,
        "Sta_HumanDct": 0,
        "Sta_IDCoilTemp": 29,
        "Sta_IDRPM": 0,
        "Sta_IDRh": 0,
        "Sta_IDRoomTemp": 28,
        "Sta_ODAirTemp": 27,
        "Sta_ODCoilTemp": 28,
        "Sta_ODCpFreq": 0,
        "Sta_ODCurrConsp": 0,
        "Sta_ODDiscTemp": 36,
        "Sta_ODEXVPulse": 400,
        "Sta_ODPwrCon": 0,
        "Sta_ODRPM": 0,
        "cfg": 0,
        "d_ota_flag": 0,
        "eventType": "connected",
        "ip": "",
        "key": "cb656411dc972d26b8f79830f7148c1c",
        "ota_flag": 0,
        "port": "",
        "rbt": 0,
        "remote_ota_flag": 0,
        "sch": 1,
        "shadowStateVersion": 13915,
        "thingName": "Daikin_4c50dd423066",
        "timerState": 0,
        "updatedOn": "2025-09-24 02:46:07",
        "version": "V2.1.0",
    },
    "subStartDate": "2025-01-04 18:53:15",
    "subnetMask": "-",
    "thingName": "Daikin_4c50dd423066=AC",
    "unitIndex": 1,
}
"""


@dataclass
class ShadowState:
    """Shadow state containing the air conditioner's current settings and status"""

    # Bar settings (UI elements)
    Bar_AutoF: int = 0
    Bar_AutoM: int = 0
    Bar_CoolM: int = 0
    Bar_DryM: int = 0
    Bar_FanM: int = 0
    Bar_HeatM: int = 0
    Bar_LowF: int = 0
    Bar_Sleep: int = 0
    Bar_Swing: int = 0
    Bar_Timer: int = 0

    # Enable flags for features
    Ena_ACoilCln: int = 0
    Ena_Breeze: int = 0
    Ena_CKSwing: int = 0
    Ena_Cmode: int = 0
    Ena_CoilCln: int = 0
    Ena_DOTA: int = 0
    Ena_Ecoplus: int = 0
    Ena_Icoolx: int = 0
    Ena_LEDOff: int = 0
    Ena_LRStep: int = 0
    Ena_LRSwing: int = 0
    Ena_MDemand: int = 0
    Ena_MoSupp: int = 0
    Ena_PwrInd: int = 0
    Ena_Sense: int = 0
    Ena_Silent: int = 0
    Ena_SmDrift: int = 0
    Ena_SmEcomax: int = 0
    Ena_SmPerDiag: int = 0
    Ena_SmPwrfulplus: int = 0
    Ena_SmSleepplus: int = 0
    Ena_Streamer: int = 0
    Ena_Turbo: int = 0
    Ena_UDStep: int = 0
    Ena_eLight: int = 0

    # Information fields
    Inf_IDAlgo: int = 0
    Inf_IDCap: int = 0
    Inf_IDType: int = 0
    Inf_MaxPL: int = 0
    Inf_MinPL: int = 0
    Inf_NSVer: int = 0
    Inf_ODPwrCon: int = 0
    Inf_Prod: int = 0
    Inf_ProdBrand: int = 0
    Inf_ProdSys: int = 0

    # Settings
    Set_ACoilCln: int = 0
    Set_Breeze: int = 0
    Set_CKSwing: int = 0
    Set_CoilCln: int = 0
    Set_CommStep: int = 0
    Set_Ecoplus: int = 0
    Set_Fan: int = 0
    Set_FanExtend: int = 0
    Set_Icoolx: int = 0
    Set_Ion: int = 0
    Set_LEDOff: int = 0
    Set_LRLvr: int = 0
    Set_MDemand: int = 0
    Set_MoSupp: int = 0
    Set_Mode: int = 0  # Operating mode (0=Off, 1=Auto, 2=Heat, 3=Cool, 4=Dry, 5=Fan)
    Set_OnOff: int = 0  # Power state (0=Off, 1=On)
    Set_PL: int = 0
    Set_Pdown: int = 0
    Set_PwrInd: int = 0
    Set_SancMode: int = 0
    Set_Sense: int = 0
    Set_Silent: int = 0
    Set_Sleep: int = 0
    Set_SmDrift: int = 0
    Set_SmEcomax: int = 0
    Set_SmPerDiag: int = 0
    Set_SmPwrfulplus: int = 0
    Set_SmSleepplus: int = 0
    Set_Streamer: int = 0
    Set_Swing: int = 0
    Set_Temp: int = 0  # Target temperature
    Set_Turbo: int = 0
    Set_Turboplus: int = 0
    Set_UDLvr: int = 0
    Set_eLight: int = 0

    # Status readings
    Sta_AutoM: int = 0
    Sta_Cmode: int = 0
    Sta_Cmode_C: int = 0
    Sta_CoilCln: int = 0
    Sta_CpOnOff: int = 0
    Sta_CpRT: int = 0
    Sta_DCBus: int = 0
    Sta_ErrCode: int = 0
    Sta_Faht: int = 0
    Sta_HumanDct: int = 0
    Sta_IDCoilTemp: int = 0  # Indoor coil temperature
    Sta_IDRPM: int = 0
    Sta_IDRh: int = 0  # Indoor relative humidity
    Sta_IDRoomTemp: int = 0  # Indoor room temperature
    Sta_ODAirTemp: int = 0  # Outdoor air temperature
    Sta_ODCoilTemp: int = 0  # Outdoor coil temperature
    Sta_ODCpFreq: int = 0
    Sta_ODCurrConsp: int = 0
    Sta_ODDiscTemp: int = 0  # Outdoor discharge temperature
    Sta_ODEXVPulse: int = 0
    Sta_ODPwrCon: int = 0
    Sta_ODRPM: int = 0

    # System fields
    cfg: int = 0
    d_ota_flag: int = 0
    eventType: str = ""
    ip: str = ""
    key: str = ""
    ota_flag: int = 0
    port: str = ""
    rbt: int = 0
    remote_ota_flag: int = 0
    sch: int = 0
    shadowStateVersion: int = 0
    thingName: str = ""
    timerState: int = 0
    updatedOn: str = ""
    version: str = ""

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ShadowState":
        """Parse shadow state from API response dictionary"""
        return ShadowState(**{k: v for k, v in data.items() if hasattr(ShadowState, k)})


@dataclass
class Aircond:
    """Air conditioner unit data class"""

    ACGroup: str = ""
    ACName: str = ""
    IP: str = ""
    Logo: str = ""
    ThingName: str = ""
    ThingType: str = ""
    gatewayIP: str = ""
    groupIndex: int = 0
    guestPaired: int = 0
    isGooglePreferredDevice: int = 0
    isPreferredDevice: int = 0
    manufacturer: str = ""
    planExpiredDate: str = ""
    planID: str = ""
    qx: str = ""
    shadowState: ShadowState = field(default_factory=ShadowState)
    subStartDate: str = ""
    subnetMask: str = ""
    thingName: str = ""
    unitIndex: int = 0

    @property
    def is_on(self) -> bool:
        """Check if the air conditioner is powered on"""
        return self.shadowState.Set_OnOff == 1

    @property
    def current_temp(self) -> Optional[int]:
        """Get current room temperature"""
        return self.shadowState.Sta_IDRoomTemp

    @property
    def target_temp(self) -> Optional[int]:
        """Get target temperature"""
        return self.shadowState.Set_Temp

    @property
    def mode(self) -> Optional[str]:
        """Get operating mode as string"""
        if not self.shadowState:
            return None

        return (
            AircondMode(self.shadowState.Set_Mode).name
            if self.shadowState.Set_Mode in AircondMode._value2member_map_
            else "Unknown"
        )

    @property
    def fan_speed(self) -> Optional[int]:
        """Get fan speed setting"""
        return self.shadowState.Set_Fan

    @property
    def swing_enabled(self) -> bool:
        """Check if swing is enabled"""
        return self.shadowState.Set_Swing == 1

    @property
    def plan_expired_date(self) -> Optional[datetime]:
        """Get plan expiration date as datetime object"""
        if not self.planExpiredDate:
            return None
        try:
            return datetime.strptime(self.planExpiredDate, "%Y-%m-%d")
        except ValueError:
            return None

    @property
    def subscription_start_date(self) -> Optional[datetime]:
        """Get subscription start date as datetime object"""
        if not self.subStartDate:
            return None
        try:
            return datetime.strptime(self.subStartDate, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    @property
    def mac_address(self) -> str:
        """Generate a MAC address from the ThingName"""
        if not self.ThingName or len(self.ThingName) < 12:
            return "00:00:00:00:00:00"
        hex_part = self.ThingName[-12:]
        return ":".join(hex_part[i : i + 2] for i in range(0, 12, 2))

    @staticmethod
    def from_api(data: dict) -> "Aircond":
        """Create Aircond instance from API response dictionary"""
        # Extract shadow state
        shadow_state = ShadowState.from_dict(data["shadowState"])

        # Create the main aircond object
        aircond_data = {
            k: v for k, v in data.items() if k != "shadowState" and hasattr(Aircond, k)
        }
        aircond = Aircond(**aircond_data)
        aircond.shadowState = shadow_state

        return aircond

    @property
    def object_id(self) -> str:
        return f"{self.ACName.lower().replace(' ', '_')}_ac"

    @property
    def unique_id(self) -> UniqueID:
        return UniqueID(self.ThingName.lower())

    @property
    def is_connected(self) -> bool:
        return self.shadowState.eventType == "connected"

    def __str__(self) -> str:
        """String representation of the air conditioner"""
        status = "ON" if self.is_on else "OFF"
        temp_info = (
            f" ({self.current_temp}°C → {self.target_temp}°C)"
            if self.current_temp and self.target_temp
            else ""
        )
        mode_info = f" [{self.mode}]" if self.mode else ""
        return f"{self.ACName} ({self.IP}): {status}{mode_info}{temp_info}"

    def __hash__(self) -> int:
        return hash(self.unique_id)


@dataclass
class AircondState:
    pass


class AircondMode(IntEnum):
    COOL = 1
    FAN_ONLY = 2
    DRY = 4


class FanSpeed(IntEnum):
    AUTO = 128
    UNKNOWN = 1
    LOW = 2
    MEDIUM = 4
    HIGH = 8


class AircondSwing(IntEnum):
    OFF = 0
    STEP_1 = 1
    STEP_2 = 2
    STEP_3 = 3
    STEP_4 = 4
    STEP_5 = 5
    AUTO = 15


class AircondPreset(Enum):
    NONE = "none"
    COMFORT = "comfort"
    ECO = "eco"
    BOOST = "boost"
    SLEEP = "sleep"


@dataclass
class AircondMqttTopics:
    base: str
    availability: str
    cmd_mode: str
    cmd_temp: str
    cmd_fan: str
    cmd_swing: str
    cmd_swing_horizontal: str
    cmd_preset: str
    status: str
    discovery: str
    sensor: str

    @staticmethod
    def from_aircond(aircond: Aircond) -> "AircondMqttTopics":
        base = f"{MQTT_PREFIX}/{aircond.unique_id}"

        return AircondMqttTopics(
            base=base,
            availability=f"{base}/availability",
            cmd_mode=f"{base}/set/mode",
            cmd_temp=f"{base}/set/temperature",
            cmd_fan=f"{base}/set/fan_mode",
            cmd_swing=f"{base}/set/swing_mode",
            cmd_swing_horizontal=f"{base}/set/swing_horizontal_mode",
            cmd_preset=f"{base}/set/preset_mode",
            status=f"{base}/status",
            discovery=f"{DISCOVERY_PREFIX}/climate/{aircond.unique_id}/config",
            sensor=f"{base}/sensor",
        )


# HASS mappings
HVAC_MODES = ["off", "cool", "dry", "fan_only"]
FAN_MODES = ["auto", "low", "medium", "high"]

# Daikin-specific constants
MIN_TEMP = 16
MAX_TEMP = 31
TEMP_STEP_AND_PRECISION = 1.0


@dataclass
class DiscoveryMessage:
    topic: str
    payload: dict


@dataclass
class EnergyResponse:
    aircond: Aircond
    energy: float
    energy_alternate: float

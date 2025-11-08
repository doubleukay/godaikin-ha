"""Constants for the GO DAIKIN integration."""

DOMAIN = "godaikin"

# Storage
STORAGE_KEY = "godaikin_mold_proof"
STORAGE_VERSION = 1

# Configuration keys
CONF_MOLD_PROOF_DURATION = "mold_proof_duration"
CONF_MOLD_PROOF_ENABLED = "mold_proof_enabled"

# Defaults
DEFAULT_MOLD_PROOF_DURATION = 60  # minutes
DEFAULT_MOLD_PROOF_ENABLED = False

# Platforms
PLATFORMS = ["climate", "sensor", "light", "switch"]

# HVAC modes
HVAC_MODES = ["off", "cool", "dry", "fan_only"]
FAN_MODES = ["auto", "low", "medium", "high"]

# Temperature settings
MIN_TEMP = 16
MAX_TEMP = 31
TEMP_STEP = 1.0
PRECISION = 1.0

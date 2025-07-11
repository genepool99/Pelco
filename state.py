import threading
import json

# Lock for thread safety
lock = threading.Lock()

# Shared serial handle and device address
DEVICE_ADDRESS = 0x01
ser = None

# Load limits from JSON
LIMITS_PATH = "limits.json"
with open(LIMITS_PATH, "r") as f:
    limits = json.load(f)

AZ_MIN = limits.get("az_min", 0)
AZ_MAX = limits.get("az_max", 359)
EL_MIN = limits.get("el_min", -45)
EL_MAX = limits.get("el_max", 45)

# Internal position state
_position = {
    "az": 0.0,
    "el": 0.0,
    "target_az": 0.0,
    "target_el": 0.0,
}

def get_position(target=False):
    with lock:
        if target:
            return _position["target_az"], _position["target_el"]
        else:
            return _position["az"], _position["el"]

def set_position(az, el):
    with lock:
        _position["az"] = az
        _position["el"] = el

def update_position(az=None, el=None, target=False):
    with lock:
        if target:
            if az is not None:
                _position["target_az"] = az
            if el is not None:
                _position["target_el"] = el
        else:
            if az is not None:
                _position["az"] = az
            if el is not None:
                _position["el"] = el
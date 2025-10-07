# Sensori dinamici per ogni centrale
import logging

DOMAIN = "lince_cloud"
LOGGER = logging.getLogger(__package__)
MANUFACTURER = "Lince Italia SpA"
MANUFACTURER_URL = "https://www.lince.net"

API_BASE = "https://goldcloud.lince.net/api"
API_SESSION_URL = f"{API_BASE}/sessions"
API_SYSTEMS_URL = f"{API_BASE}/system"
API_SYSTEM_ACCESS_URL = f"{API_BASE}/system-access"
API_SOCKET_IO_URL = f"{API_BASE}/socket.io"

SOCKET_NAMESPACE = "/socket"
MODEL_IMAGE_BASE = "https://goldcloud.lince.net/static/images/model"
PROJECT_LOGO_URL = "https://goldcloud.lince.net/static/images/testalince.png"

# Bitmask programmi per type=240
MASK_G1 = 1
MASK_G2 = 2
MASK_G3 = 4
MASK_GEXT = 8

# Default mapping stati -> programmi (se non configuri niente)
DEFAULT_MODE_MAP = {
    "home":  ["g1"],
    "away":  ["g1", "g2", "g3", "gext"],
    "night": ["g2"],
}

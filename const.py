"""Costanti per l'integrazione LinceCloud."""
import logging

# Core - OBBLIGATORIO per Home Assistant
DOMAIN = "lince_cloud"

# Logger
LOGGER = logging.getLogger(__package__)

# Manufacturer info
MANUFACTURER = "Lince Italia SpA"
MANUFACTURER_URL = "https://www.lince.net"

# API Base URLs
API_BASE = "https://goldcloud.lince.net/api"
API_SESSION_URL = f"{API_BASE}/sessions"
API_SYSTEMS_URL = f"{API_BASE}/system"
API_SYSTEM_ACCESS_URL = f"{API_BASE}/system-access"
API_SOCKET_IO_URL = f"{API_BASE}/socket.io"

# Model and images
MODEL_IMAGE_BASE = "https://goldcloud.lince.net/static/images/model"
PROJECT_LOGO_URL = "https://goldcloud.lince.net/static/images/testalince.png"

# Retry configuration
RETRY_INTERVAL = 300  # 5 minuti
MAX_RETRY_INTERVAL = 1800  # 30 minuti massimo
INITIAL_RETRY_INTERVAL = 60  # 1 minuto per il primo retry

# Token management
TOKEN_EXPIRY_MINUTES = 60
TOKEN_SAFETY_SKEW_SECONDS = 30
AUTH_FAIL_NOTIFY_COOLDOWN = 15 * 60  # 15 minuti

# Default mapping stati (cloud)
DEFAULT_MODE_MAP = {
    "home": ["g1"],
    "away": ["g1", "g2", "g3"],
    "night": ["g2"],
    "vacation": ["g3"],
}
DEFAULT_LOCAL_TIMEOUT = 10
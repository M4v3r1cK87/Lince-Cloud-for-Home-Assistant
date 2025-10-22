"""Costanti specifiche per Lince Europlus."""

# Zone limits - SPECIFICI PER EUROPLUS
MAX_FILARI = 35
MAX_RADIO = 64
DEFAULT_FILARI = 0
DEFAULT_RADIO = 0

# Programs - SPECIFICI PER EUROPLUS
SUPPORTS_GEXT = True
PROGRAMS = ["g1", "g2", "g3", "gext"]

# Bitmask programmi per type=240 - SPECIFICI PER EUROPLUS
MASK_G1 = 1
MASK_G2 = 2
MASK_G3 = 4
MASK_GEXT = 8

PROGRAM_BITS = {
    "g1": MASK_G1,
    "g2": MASK_G2,
    "g3": MASK_G3,
    "gext": MASK_GEXT
}

# Socket messages - SPECIFICI PER EUROPLUS
SOCKET_MESSAGE_TYPE_PIN = 251
SOCKET_MESSAGE_TYPE_PROGRAMS = 240
SOCKET_NAMESPACE = "/socket"

# Default mode mapping for Europlus
DEFAULT_MODE_MAP = {
    "home": ["g1"],
    "away": ["g1", "g2", "g3", "gext"],
    "night": ["g2"],
    "vacation": ["g3"],
}
"""
EuroNET Local Client Package.

Questo package fornisce l'interfaccia locale per centrali Lince EuroNET.
"""

from .client import (
    EuroNetClient,
    StatoCentrale,
    StatoZonaFilare,
    StatoZonaRadio,
    ConfigZonaFilare,
    ConfigZonaRadio,
    ConfigTempi,
    TipoIngresso,
    Logica,
    TempoTrigger,
    ZonaFilareParser,
    ZonaRadioParser,
    TempiParser,
)
from .coordinator import EuroNetCoordinator
from .sensor import setup_euronet_sensors
from .binary_sensor import setup_euronet_binary_sensors
from .alarm_control_panel import setup_euronet_alarm_panels
from .switch import setup_euronet_switches

__all__ = [
    "EuroNetClient",
    "EuroNetCoordinator",
    "StatoCentrale",
    "StatoZonaFilare",
    "StatoZonaRadio",
    "ConfigZonaFilare",
    "ConfigZonaRadio",
    "ConfigTempi",
    "TipoIngresso",
    "Logica",
    "TempoTrigger",
    "ZonaFilareParser",
    "ZonaRadioParser",
    "TempiParser",
    # Setup functions
    "setup_euronet_sensors",
    "setup_euronet_binary_sensors",
    "setup_euronet_alarm_panels",
    "setup_euronet_switches",
]

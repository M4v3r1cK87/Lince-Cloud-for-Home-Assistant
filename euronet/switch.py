"""Switches per EuroPlus/EuroNET modalità locale."""
from __future__ import annotations
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


# ============================================================================
# SETUP FUNCTION
# ============================================================================

def setup_euronet_switches(coordinator, config_entry: ConfigEntry, hass):
    """
    Setup switches per EuroNET.
    
    In modalità locale non ci sono switch cloud (socket, notifiche).
    In futuro potrebbe essere aggiunta l'esclusione zone.
    """
    entities = []
    
    # Per ora nessuno switch in modalità locale
    _LOGGER.info("Nessuno switch creato per EuroNET (non applicabile)")
    
    return entities

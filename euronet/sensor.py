"""Sensors specifici per EuroPlus/EuroNET modalità locale."""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory

from ..const import DOMAIN, MANUFACTURER
from .entity_mapping import SENSOR_MAPPING

_LOGGER = logging.getLogger(__name__)


# ============================================================================
# DEVICE CLASS MAPPING
# ============================================================================

SENSOR_DEVICE_CLASS_MAP = {
    "temperature": SensorDeviceClass.TEMPERATURE,
    "voltage": SensorDeviceClass.VOLTAGE,
    "battery": SensorDeviceClass.BATTERY,
    "power": SensorDeviceClass.POWER,
    "current": SensorDeviceClass.CURRENT,
}

STATE_CLASS_MAP = {
    "measurement": SensorStateClass.MEASUREMENT,
    "total": SensorStateClass.TOTAL,
    "total_increasing": SensorStateClass.TOTAL_INCREASING,
}


# ============================================================================
# SETUP FUNCTION
# ============================================================================

def setup_euronet_sensors(coordinator, config_entry: ConfigEntry, hass):
    """
    Setup COMPLETO dei sensors per EuroNET.
    Crea dinamicamente i sensori basandosi su SENSOR_MAPPING.
    """
    entities = []
    
    for data_key, mapping in SENSOR_MAPPING.items():
        entity = EuroNetSensor(
            coordinator=coordinator,
            config_entry=config_entry,
            data_key=data_key,
            mapping=mapping,
        )
        entities.append(entity)
        _LOGGER.debug(f"Creato sensore locale: {data_key}")
    
    _LOGGER.info(f"Creati {len(entities)} sensori per EuroNET")
    return entities


# ============================================================================
# SENSOR ENTITY
# ============================================================================

class EuroNetSensor(CoordinatorEntity, SensorEntity):
    """Sensore generico per modalità locale, configurato dinamicamente."""

    def __init__(
        self,
        coordinator,
        config_entry: ConfigEntry,
        data_key: str,
        mapping: dict,
    ):
        """Inizializza il sensore."""
        super().__init__(coordinator)
        
        self._config_entry = config_entry
        self._data_key = data_key
        self._mapping = mapping
        
        # Host per unique_id
        host = coordinator.client.host
        
        # Nome dall'entity_mapping
        self._attr_name = mapping.get("friendly_name", data_key.replace("_", " ").title())
        
        # Unique ID basato su host + data_key
        self._attr_unique_id = f"euronet_{host}_{data_key}"
        
        # Entity category (se specificata)
        entity_cat = mapping.get("entity_category")
        if entity_cat == "diagnostic":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif entity_cat == "config":
            self._attr_entity_category = EntityCategory.CONFIG
        
        # Icon
        if "icon" in mapping:
            self._attr_icon = mapping["icon"]
        
        # Device class
        dc = mapping.get("device_class")
        if dc and dc in SENSOR_DEVICE_CLASS_MAP:
            self._attr_device_class = SENSOR_DEVICE_CLASS_MAP[dc]
        
        # State class
        sc = mapping.get("state_class")
        if sc and sc in STATE_CLASS_MAP:
            self._attr_state_class = STATE_CLASS_MAP[sc]
        
        # Unit of measurement
        self._attr_native_unit_of_measurement = mapping.get("unit_of_measurement")
        
        # Device info comune per raggruppare le entità
        sw_version = "N/A"
        if coordinator.data and len(coordinator.data) > 0:
            sw_version = str(coordinator.data[0].get("release_sw", "N/A"))
            
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"euronet_{host}")},
            "name": f"EuroNET ({host})",
            "manufacturer": MANUFACTURER,
            "model": "4124EURONET",
            "sw_version": sw_version,
        }

    def _get_system_data(self) -> dict | None:
        """Recupera i dati del sistema dal coordinator."""
        if self.coordinator.data and len(self.coordinator.data) > 0:
            return self.coordinator.data[0]
        return None

    @property
    def native_value(self) -> Any:
        """Restituisce il valore del sensore."""
        system = self._get_system_data()
        if system:
            return system.get(self._data_key)
        return None

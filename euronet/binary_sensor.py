"""Binary sensors specifici per EuroPlus/EuroNET modalità locale."""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory

from ..const import DOMAIN, MANUFACTURER
from .entity_mapping import (
    BINARY_SENSOR_CENTRALE_MAPPING,
    ZONE_FILARE_CONFIG,
    ZONE_RADIO_CONFIG,
    ZONE_ATTRIBUTES,
)

_LOGGER = logging.getLogger(__name__)


# ============================================================================
# DEVICE CLASS MAPPING
# ============================================================================

BINARY_SENSOR_DEVICE_CLASS_MAP = {
    "power": BinarySensorDeviceClass.POWER,
    "battery": BinarySensorDeviceClass.BATTERY,
    "safety": BinarySensorDeviceClass.SAFETY,
    "problem": BinarySensorDeviceClass.PROBLEM,
    "tamper": BinarySensorDeviceClass.TAMPER,
    "lock": BinarySensorDeviceClass.LOCK,
    "door": BinarySensorDeviceClass.DOOR,
    "window": BinarySensorDeviceClass.WINDOW,
    "opening": BinarySensorDeviceClass.OPENING,
    "motion": BinarySensorDeviceClass.MOTION,
    "smoke": BinarySensorDeviceClass.SMOKE,
    "gas": BinarySensorDeviceClass.GAS,
}


# ============================================================================
# SETUP FUNCTION
# ============================================================================

def setup_euronet_binary_sensors(coordinator, config_entry: ConfigEntry, hass):
    """
    Setup COMPLETO dei binary sensors per EuroNET.
    Crea dinamicamente i sensori basandosi su BINARY_SENSOR_CENTRALE_MAPPING
    e le zone presenti nei dati del coordinator.
    """
    entities = []
    
    # 1. Binary sensors della centrale (da mapping)
    for data_key, mapping in BINARY_SENSOR_CENTRALE_MAPPING.items():
        entity = EuroNetBinarySensor(
            coordinator=coordinator,
            config_entry=config_entry,
            data_key=data_key,
            mapping=mapping,
        )
        entities.append(entity)
        _LOGGER.debug(f"Creato binary sensor centrale: {data_key}")
    
    # 2. Zone (dinamiche dai dati del coordinator)
    if coordinator.data and len(coordinator.data) > 0:
        system = coordinator.data[0]
        entries = system.get("entries", {})
        
        for zone_key, zone_data in entries.items():
            # Determina il tipo di zona
            if zone_key.startswith("zona_filare_"):
                zone_type = "filare"
                zone_config = ZONE_FILARE_CONFIG
            elif zone_key.startswith("zona_radio_"):
                zone_type = "radio"
                zone_config = ZONE_RADIO_CONFIG
            else:
                continue  # Skip non-zone entries
            
            zone_number = zone_data.get("numero", 0)
            zone_name = zone_data.get("nome", f"Zona {zone_number}")
            
            entity = EuroNetZoneBinarySensor(
                coordinator=coordinator,
                config_entry=config_entry,
                zone_number=zone_number,
                zone_name=zone_name,
                zone_type=zone_type,
                mapping=zone_config,
            )
            entities.append(entity)
            _LOGGER.debug(f"Creato binary sensor zona {zone_type}: {zone_name}")
    
    _LOGGER.info(f"Creati {len(entities)} binary sensor per EuroNET")
    return entities


# ============================================================================
# BASE ENTITY
# ============================================================================

class EuroNetBaseBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Classe base per binary sensor locali EuroPlus."""

    def __init__(
        self,
        coordinator,
        config_entry: ConfigEntry,
        data_key: str,
        mapping: dict,
    ):
        """Inizializza l'entità base."""
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
        
        # Icon (può essere override dinamico)
        if "icon" in mapping:
            self._attr_icon = mapping["icon"]
        
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


# ============================================================================
# BINARY SENSOR ENTITY
# ============================================================================

class EuroNetBinarySensor(EuroNetBaseBinarySensor):
    """Binary sensor generico per modalità locale, configurato dinamicamente."""

    def __init__(
        self,
        coordinator,
        config_entry: ConfigEntry,
        data_key: str,
        mapping: dict,
    ):
        """Inizializza il binary sensor."""
        super().__init__(coordinator, config_entry, data_key, mapping)
        
        # Device class
        dc = mapping.get("device_class")
        if dc and dc in BINARY_SENSOR_DEVICE_CLASS_MAP:
            self._attr_device_class = BINARY_SENSOR_DEVICE_CLASS_MAP[dc]
        
        # Invert logic (per es. programmi G1/G2/G3/GEXT -> invertiti per device_class lock)
        self._invert = mapping.get("invert", False) or mapping.get("inverted", False)
        
        # Icon on/off
        self._icon_on = mapping.get("icon_on")
        self._icon_off = mapping.get("icon_off")

    @property
    def is_on(self) -> bool | None:
        """Restituisce True se il sensore è attivo."""
        system = self._get_system_data()
        if system:
            value = system.get(self._data_key)
            if value is not None:
                return not value if self._invert else value
        return None

    @property
    def icon(self) -> str | None:
        """Restituisce l'icona in base allo stato."""
        if self._icon_on and self._icon_off:
            return self._icon_on if self.is_on else self._icon_off
        return self._mapping.get("icon")


# ============================================================================
# ZONE BINARY SENSOR
# ============================================================================

class EuroNetZoneBinarySensor(EuroNetBaseBinarySensor):
    """Binary sensor per una zona (filare o radio)."""

    def __init__(
        self,
        coordinator,
        config_entry: ConfigEntry,
        zone_number: int,
        zone_name: str,
        zone_type: str,  # "filare" o "radio"
        mapping: dict,
    ):
        """Inizializza il binary sensor zona."""
        self._zone_number = zone_number
        self._zone_type = zone_type
        
        # Chiave: zona_filare_X o zona_radio_X
        data_key = f"zona_{zone_type}_{zone_number}"
        
        # Override del nome con formato "Zona <numero>: <nome>"
        mapping = mapping.copy()
        if zone_name:
            mapping["friendly_name"] = f"Zona {zone_number}: {zone_name}"
        else:
            mapping["friendly_name"] = f"Zona {zone_type.title()} {zone_number}"
        
        super().__init__(coordinator, config_entry, data_key, mapping)
        
        # Device class per zone
        dc = mapping.get("device_class", "door")
        if dc in BINARY_SENSOR_DEVICE_CLASS_MAP:
            self._attr_device_class = BINARY_SENSOR_DEVICE_CLASS_MAP[dc]
        
        # Icon on/off
        self._icon_on = mapping.get("icon_on", "mdi:door-open")
        self._icon_off = mapping.get("icon_off", "mdi:door-closed")
        
        # Override device_info per raggruppare le zone in device separati
        # (come fatto per il cloud)
        host = coordinator.client.host
        zone_type_label = "Zone Filari" if zone_type == "filare" else "Zone Radio"
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"euronet_{host}_{zone_type}")},
            "name": f"{zone_type_label} ({host})",
            "manufacturer": MANUFACTURER,
            "model": "4124EURONET",
            # Collega alla centrale principale tramite via_device
            "via_device": (DOMAIN, f"euronet_{host}"),
        }

    @property
    def is_on(self) -> bool | None:
        """Restituisce True se la zona è aperta."""
        system = self._get_system_data()
        if system:
            entries = system.get("entries", {})
            zone_key = f"zona_{self._zone_type}_{self._zone_number}"
            if zone_key in entries:
                return entries[zone_key].get("aperta", False)
        return None

    @property
    def icon(self) -> str | None:
        """Restituisce l'icona in base allo stato."""
        return self._icon_on if self.is_on else self._icon_off

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Attributi aggiuntivi della zona.
        
        Include sia lo stato runtime che la configurazione della zona
        (recuperata una volta all'init dall'interfaccia web EuroNET).
        """
        attrs = {}
        system = self._get_system_data()
        if system:
            entries = system.get("entries", {})
            zone_key = f"zona_{self._zone_type}_{self._zone_number}"
            if zone_key in entries:
                zone = entries[zone_key]
                
                # Attributi comuni di stato runtime
                for attr in ZONE_ATTRIBUTES:
                    if attr in zone:
                        attrs[attr] = zone[attr]
                
                # Attributi di configurazione (scaricati una volta all'init)
                config = zone.get("config", {})
                if config:
                    # Attributi di configurazione con nomi leggibili
                    for key, value in config.items():
                        # Converti liste in stringhe leggibili
                        if isinstance(value, list):
                            value = ", ".join(str(v) for v in value) if value else "Nessuno"
                        
                        # Formatta il nome dell'attributo (rimuovi underscore, capitalizza)
                        attr_name = key.replace("_", " ").title()
                        
                        # Aggiungi unità di misura per i tempi
                        if "tempo_ingresso" in key.lower():
                            attr_name = "Tempo ingresso (sec)"
                        elif "tempo_uscita" in key.lower():
                            attr_name = "Tempo uscita (sec)"
                        
                        attrs[attr_name] = value
                
                # Attributi extra per zone radio
                if self._zone_type == "radio":
                    if "supervisione" in zone:
                        attrs["supervisione"] = zone["supervisione"]
                    if "batteria_scarica" in zone:
                        attrs["batteria_scarica"] = zone["batteria_scarica"]
        
        return attrs

"""Binary sensor platform for Lince Alarm integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import logging

from .const import DOMAIN
from .factory import ComponentFactory
from .common.binary_sensors import CommonSocketConnectionSensor

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up binary sensors from a config entry."""
    coordinator = hass.data[DOMAIN]["coordinator"]
    local_mode = hass.data[DOMAIN].get("local_mode", False)
    entities = []

    if local_mode:
        # Modalità LOCALE: usa il coordinator locale
        from .euronet import setup_euronet_binary_sensors
        entities = setup_euronet_binary_sensors(coordinator, config_entry, hass)
    else:
        # Modalità CLOUD: loop sui systems
        api = hass.data[DOMAIN]["api"]
        for system in coordinator.data:
            row_id = system["id"]
            centrale_name = system.get("name", "Sconosciuta")
            
            # Determina il brand del sistema
            brand = ComponentFactory.get_brand_from_system(system)
            _LOGGER.debug(f"Setup binary sensors per sistema {row_id} (brand: {brand})")
            
            # 1. Sensore socket comune a TUTTI i brand
            entities.append(CommonSocketConnectionSensor(row_id, centrale_name, api))
            
            # 2. DELEGA TUTTO IL RESTO al brand specifico
            brand_entities = ComponentFactory.get_binary_sensors_for_system(
                brand=brand,
                system=system,
                coordinator=coordinator,
                api=api,
                config_entry=config_entry,
                hass=hass
            )
            entities.extend(brand_entities)

    async_add_entities(entities)

def update_buscomm_binarysensors(api, row_id, keys, isStepRecursive=False):
    """
    Funzione wrapper per compatibilità con vecchie chiamate.
    Determina il brand e chiama la funzione appropriata.
    """
    # Cerca di determinare il brand dal sistema
    if hasattr(api, 'coordinator') and api.coordinator:
        system = next((s for s in api.coordinator.data if s["id"] == row_id), None)
        if system:
            brand = ComponentFactory.get_brand_from_system(system)
            
            if brand == "lince-gold":
                from .gold.binary_sensor import update_gold_buscomm_binarysensors
                return update_gold_buscomm_binarysensors(api, row_id, keys, isStepRecursive)
            elif brand == "lince-europlus":
                from .europlus.binary_sensor import update_europlus_buscomm_binarysensors
                return update_europlus_buscomm_binarysensors(api, row_id, keys, isStepRecursive)
    
    # Default: assume Europlus
    from .europlus.binary_sensor import update_europlus_buscomm_binarysensors
    return update_europlus_buscomm_binarysensors(api, row_id, keys, isStepRecursive)

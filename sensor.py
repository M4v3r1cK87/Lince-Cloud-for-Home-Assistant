"""Sensor platform for LinceCloud integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import logging

from .const import DOMAIN
from .factory import ComponentFactory

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up sensors from a config entry."""
    coordinator = hass.data[DOMAIN]["coordinator"]
    local_mode = hass.data[DOMAIN].get("local_mode", False)
    entities = []

    if local_mode:
        # Modalità LOCALE: usa il coordinator locale
        from .euronet import setup_euronet_sensors
        entities = setup_euronet_sensors(coordinator, config_entry, hass)
    else:
        # Modalità CLOUD: loop sui systems
        api = hass.data[DOMAIN]["api"]
        for system in coordinator.data:
            row_id = system["id"]
            
            # Determina il brand del sistema
            brand = ComponentFactory.get_brand_from_system(system)
            _LOGGER.debug(f"Setup sensors per sistema {row_id} (brand: {brand})")
            
            # DELEGA TUTTO al brand specifico
            brand_entities = ComponentFactory.get_sensors_for_system(
                brand=brand,
                system=system,
                coordinator=coordinator,
                api=api,
                config_entry=config_entry,
                hass=hass
            )
            entities.extend(brand_entities)

    async_add_entities(entities)


def update_buscomm_sensors(api, row_id, keys):
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
                from .gold.sensor import update_gold_buscomm_sensors
                return update_gold_buscomm_sensors(api, row_id, keys)
            elif brand == "lince-europlus":
                from .europlus.sensor import update_europlus_buscomm_sensors
                return update_europlus_buscomm_sensors(api, row_id, keys)
    
    # Default: assume Europlus
    from .europlus.sensor import update_europlus_buscomm_sensors
    return update_europlus_buscomm_sensors(api, row_id, keys)

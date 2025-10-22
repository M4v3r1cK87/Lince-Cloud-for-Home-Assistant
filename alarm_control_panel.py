"""Alarm control panel platform for LinceCloud integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import logging

from .const import DOMAIN
from .factory import ComponentFactory

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up alarm control panels from a config entry."""
    api = hass.data[DOMAIN]["api"]
    coordinator = hass.data[DOMAIN]["coordinator"]
    entities = []

    for system in coordinator.data:
        row_id = system["id"]
        
        # Determina il brand del sistema
        brand = ComponentFactory.get_brand_from_system(system)
        _LOGGER.debug(f"Setup alarm control panel per sistema {row_id} (brand: {brand})")
        
        # DELEGA COMPLETAMENTE al brand specifico
        brand_entities = ComponentFactory.get_alarm_panels_for_system(
            brand=brand,
            system=system,
            coordinator=coordinator,
            api=api,
            config_entry=config_entry,
            hass=hass
        )
        entities.extend(brand_entities)

    async_add_entities(entities)
    
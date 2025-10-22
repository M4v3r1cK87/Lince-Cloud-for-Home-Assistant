"""Switch platform for LinceCloud integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import logging

from .const import DOMAIN
from .common.switches import CommonSocketSwitch, CommonNotificationsSwitch

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up switches from a config entry."""
    api = hass.data[DOMAIN]["api"]
    coordinator = hass.data[DOMAIN]["coordinator"]
    entities = []

    for system in coordinator.data:
        row_id = system["id"]
        centrale_name = system.get("name", "Sconosciuta")
        model = system.get("model", "Unknown")
        
        _LOGGER.debug(f"Setup switches per sistema {row_id}")
        
        # Switch Socket - comune a tutti i brand
        entities.append(CommonSocketSwitch(row_id, centrale_name, model, api))
        
        # Switch Notifiche - comune a tutti i brand
        entities.append(CommonNotificationsSwitch(hass, row_id, centrale_name))

    async_add_entities(entities)
    
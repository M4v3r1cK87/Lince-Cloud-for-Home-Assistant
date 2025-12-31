"""Button platform for Lince Alarm integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import logging

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up buttons from a config entry."""
    coordinator = hass.data[DOMAIN]["coordinator"]
    local_mode = hass.data[DOMAIN].get("local_mode", False)
    entities = []

    if local_mode:
        # Modalità LOCALE: usa i button EuroNET
        from .euronet import setup_euronet_buttons
        entities = setup_euronet_buttons(coordinator, config_entry, hass)
    else:
        # Modalità CLOUD: nessun button per ora
        pass

    async_add_entities(entities)

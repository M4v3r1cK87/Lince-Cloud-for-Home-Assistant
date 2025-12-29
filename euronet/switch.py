"""Switches per EuroPlus/EuroNET modalità locale."""
from __future__ import annotations
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.restore_state import RestoreEntity

from ..const import DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)


# ============================================================================
# SETUP FUNCTION
# ============================================================================

def setup_euronet_switches(coordinator, config_entry: ConfigEntry, hass):
    """
    Setup switches per EuroNET.
    """
    entities = []
    
    # Switch per abilitare/disabilitare le notifiche
    host = coordinator.client.host
    notifications_switch = EuroNetNotificationsSwitch(
        coordinator=coordinator,
        config_entry=config_entry,
        hass=hass,
        host=host,
    )
    entities.append(notifications_switch)
    
    _LOGGER.info("Creato switch notifiche per EuroNET")
    
    return entities


# ============================================================================
# NOTIFICATIONS SWITCH
# ============================================================================

class EuroNetNotificationsSwitch(SwitchEntity, RestoreEntity):
    """Switch per abilitare/disabilitare le notifiche della centrale."""
    
    def __init__(
        self,
        coordinator,
        config_entry: ConfigEntry,
        hass,
        host: str,
    ):
        """Inizializza lo switch notifiche."""
        self._coordinator = coordinator
        self._config_entry = config_entry
        self._hass = hass
        self._host = host
        self._is_on = True  # Default: notifiche abilitate
        
        self._attr_name = "Notifiche Allarme"
        self._attr_unique_id = f"euronet_{host}_notifications"
        self._attr_icon = "mdi:bell"
        
        # Device info - associa al device principale
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"euronet_{host}")},
            "name": f"EuroNET ({host})",
            "manufacturer": MANUFACTURER,
            "model": "4124EURONET",
        }
    
    async def async_added_to_hass(self) -> None:
        """Ripristina lo stato precedente quando l'entità viene aggiunta."""
        await super().async_added_to_hass()
        
        # Prova a ripristinare lo stato precedente
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._is_on = last_state.state == "on"
        
        # Inizializza il flag in hass.data
        self._update_hass_data()
        
        _LOGGER.debug(f"Switch notifiche ripristinato: {self._is_on}")
    
    def _update_hass_data(self) -> None:
        """Aggiorna il flag notifiche in hass.data."""
        if DOMAIN not in self._hass.data:
            self._hass.data[DOMAIN] = {}
        if "notifications_enabled" not in self._hass.data[DOMAIN]:
            self._hass.data[DOMAIN]["notifications_enabled"] = {}
        
        # Usa l'host come chiave identificativa
        self._hass.data[DOMAIN]["notifications_enabled"][self._host] = self._is_on
        _LOGGER.debug(f"Notifiche per {self._host}: {self._is_on}")
    
    @property
    def is_on(self) -> bool:
        """Restituisce lo stato dello switch."""
        return self._is_on
    
    async def async_turn_on(self, **kwargs) -> None:
        """Abilita le notifiche."""
        self._is_on = True
        self._update_hass_data()
        self.async_write_ha_state()
        _LOGGER.info(f"Notifiche abilitate per {self._host}")
    
    async def async_turn_off(self, **kwargs) -> None:
        """Disabilita le notifiche."""
        self._is_on = False
        self._update_hass_data()
        self.async_write_ha_state()
        _LOGGER.info(f"Notifiche disabilitate per {self._host}")

"""Buttons per EuroPlus/EuroNET modalità locale."""
from __future__ import annotations
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)


# ============================================================================
# SETUP FUNCTION
# ============================================================================

def setup_euronet_buttons(coordinator, config_entry: ConfigEntry, hass):
    """
    Setup buttons per EuroNET.
    """
    entities = []
    
    host = coordinator.client.host
    
    # Pulsante di reboot
    reboot_button = EuroNetRebootButton(
        coordinator=coordinator,
        config_entry=config_entry,
        hass=hass,
        host=host,
    )
    entities.append(reboot_button)
    
    _LOGGER.debug("Creato pulsante reboot per EuroNET")
    
    return entities


# ============================================================================
# REBOOT BUTTON
# ============================================================================

class EuroNetRebootButton(CoordinatorEntity, ButtonEntity):
    """Pulsante per riavviare il modulo EuroNET."""
    
    _attr_icon = "mdi:restart"
    
    def __init__(
        self,
        coordinator,
        config_entry: ConfigEntry,
        hass,
        host: str,
    ):
        """Inizializza il pulsante di reboot."""
        super().__init__(coordinator)
        
        self._config_entry = config_entry
        self._hass = hass
        self._host = host
        
        # Costruisci URL reboot per riferimento
        port = coordinator.client.port
        if port == 80:
            self._reboot_url = f"http://{host}/protect/reboot.cgi"
        else:
            self._reboot_url = f"http://{host}:{port}/protect/reboot.cgi"
        
        self._attr_name = "Riavvio EuroNET"
        self._attr_unique_id = f"euronet_{host}_reboot"
        
        # Device info - associa al device principale
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"euronet_{host}")},
            "name": f"EuroNET ({host})",
            "manufacturer": MANUFACTURER,
            "model": "4124EURONET",
        }
    
    @property
    def extra_state_attributes(self) -> dict:
        """Attributi aggiuntivi del pulsante."""
        return {
            "reboot_url": self._reboot_url,
        }
    
    async def async_press(self) -> None:
        """Gestisce la pressione del pulsante.
        
        Esegue il reboot del modulo EuroNET.
        """
        _LOGGER.warning("Richiesto reboot modulo EuroNET %s", self._host)
        
        try:
            # Esegui il reboot in un executor per non bloccare
            result = await self._hass.async_add_executor_job(
                self.coordinator.client.reboot
            )
            
            if result:
                _LOGGER.warning("Reboot EuroNET avviato con successo")
            else:
                _LOGGER.error("Reboot EuroNET fallito")
                
        except Exception as e:
            _LOGGER.error("Errore durante reboot EuroNET: %s", e)

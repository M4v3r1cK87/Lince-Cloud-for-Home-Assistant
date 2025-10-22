"""Switch comuni a tutti i brand."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.device_registry import DeviceInfo
import logging

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class CommonSocketSwitch(SwitchEntity, RestoreEntity):
    """Switch per abilitare/disabilitare la connessione WebSocket - comune a tutti i brand."""
    
    def __init__(self, row_id, centrale_name, model, api):
        self._row_id = row_id
        self._centrale_name = centrale_name
        self._model = model
        self._api = api
        self._attr_name = "Abilita WebSocket"
        self._attr_unique_id = f"lince_{self._row_id}_socketenable"
        self._attr_is_on = False  # socket disattiva all'avvio
        self._is_attempting = False  # Flag per evitare switch bounce

    @property
    def icon(self):
        if self._is_attempting:
            return "mdi:sync-circle"  # Icona che indica tentativo in corso
        return "mdi:sync" if self.is_on else "mdi:sync-off"

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self._row_id)}
        )

    @property
    def available(self):
        """Lo switch è sempre disponibile per permettere di fermare la socket."""
        return True

    async def async_added_to_hass(self):
        """Ripristina lo stato e riavvia la socket se era attiva."""
        last_state = await self.async_get_last_state()
        if last_state and last_state.state == "on":
            self._attr_is_on = True
            _LOGGER.info(f"Socket {self._row_id} era attiva prima del riavvio")
            
            # Attendi un po' più a lungo per essere sicuri che eventuali socket zombie siano chiuse
            self.hass.async_create_task(self._delayed_socket_start())
        else:
            self._attr_is_on = False
            _LOGGER.info(f"Socket {self._row_id} era OFF prima del riavvio")
    
    async def _delayed_socket_start(self):
        """Avvia la socket con un delay per permettere al sistema di stabilizzarsi."""
        import asyncio
        
        # Attendi 15 secondi invece di 10 per dare tempo al sistema di pulire socket zombie
        await asyncio.sleep(15)
        
        if self._attr_is_on and not self._api.is_socket_connected(self._row_id):
            _LOGGER.info(f"Avvio automatico socket {self._row_id} dopo riavvio...")
            success = await self._api.start_socket_connection(self._row_id)
            if success:
                _LOGGER.info(f"Socket {self._row_id} riavviata con successo")
            else:
                _LOGGER.warning(f"Socket {self._row_id} in fase di connessione")
    
    async def async_will_remove_from_hass(self):
        """Quando l'entità viene rimossa, ferma la socket."""
        if self._attr_is_on:
            _LOGGER.info(f"Rimozione switch, fermo socket {self._row_id}")
            await self._api.stop_socket_connection(self._row_id)

    async def async_turn_on(self, **kwargs):
        """Attiva la socket ma mantiene lo switch ON anche se la connessione fallisce inizialmente."""
        _LOGGER.info(f"Richiesta attivazione socket per centrale {self._row_id}")
        
        # Imposta lo switch come ON indipendentemente dal risultato
        self._attr_is_on = True
        self._is_attempting = True
        self.async_write_ha_state()
        
        # Avvia la socket (che gestirà i retry internamente)
        success = await self._api.start_socket_connection(self._row_id)
        
        if success:
            _LOGGER.info(f"Socket {self._row_id} avviata con successo")
        else:
            _LOGGER.warning(f"Socket {self._row_id} in fase di connessione (retry automatici attivi)")
        
        # Lo switch rimane ON per indicare che VOGLIAMO la socket attiva
        # anche se temporaneamente non connessa
        self._is_attempting = False
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Ferma definitivamente la socket e tutti i tentativi di riconnessione."""
        _LOGGER.info(f"Richiesta STOP definitivo socket per centrale {self._row_id}")
        
        # IMPORTANTE: Ferma prima la socket (che fermerà anche i retry)
        await self._api.stop_socket_connection(self._row_id)
        
        # Solo dopo imposta lo switch come OFF
        self._attr_is_on = False
        self._is_attempting = False
        self.async_write_ha_state()
        
        _LOGGER.info(f"Socket {self._row_id} fermata definitivamente")


class CommonNotificationsSwitch(SwitchEntity, RestoreEntity):
    """Switch per abilitare/disabilitare le notifiche di sistema - comune a tutti i brand."""
    
    def __init__(self, hass, row_id, centrale_name):
        self.hass = hass
        self._row_id = row_id
        self._centrale_name = centrale_name
        self._attr_name = "Notifiche"
        self._attr_unique_id = f"lince_{self._row_id}_notifications"
        self._attr_is_on = True  # Default: notifiche abilitate
        self._attr_icon = "mdi:bell"
    
    @property
    def icon(self):
        return "mdi:bell" if self.is_on else "mdi:bell-off"
    
    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self._row_id)}
        )
    
    @property
    def available(self):
        """Lo switch è sempre disponibile."""
        return True
    
    async def async_added_to_hass(self):
        """Ripristina lo stato precedente quando l'entità viene aggiunta."""
        last_state = await self.async_get_last_state()
        if last_state:
            self._attr_is_on = last_state.state == "on"
            _LOGGER.info(f"Notifiche per {self._centrale_name} ripristinate a: {'ON' if self._attr_is_on else 'OFF'}")
        else:
            # Prima volta: default ON
            self._attr_is_on = True
            _LOGGER.info(f"Notifiche per {self._centrale_name} impostate a ON (default)")
        
        # Assicurati che notifications_enabled sia sempre un dict
        if "notifications_enabled" not in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN]["notifications_enabled"] = {}
        
        # Salva lo stato per questa centrale
        self.hass.data[DOMAIN]["notifications_enabled"][self._row_id] = self._attr_is_on
    
    async def async_turn_on(self, **kwargs):
        """Abilita le notifiche per questa centrale."""
        self._attr_is_on = True
        
        # Assicurati che sia un dict
        if "notifications_enabled" not in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN]["notifications_enabled"] = {}
        
        self.hass.data[DOMAIN]["notifications_enabled"][self._row_id] = True
        self.async_write_ha_state()
        _LOGGER.info(f"Notifiche ABILITATE per {self._centrale_name}")
    
    async def async_turn_off(self, **kwargs):
        """Disabilita le notifiche per questa centrale."""
        self._attr_is_on = False
        
        # Assicurati che sia un dict
        if "notifications_enabled" not in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN]["notifications_enabled"] = {}
        elif not isinstance(self.hass.data[DOMAIN]["notifications_enabled"], dict):
            self.hass.data[DOMAIN]["notifications_enabled"] = {}
        
        self.hass.data[DOMAIN]["notifications_enabled"][self._row_id] = False
        self.async_write_ha_state()
        _LOGGER.info(f"Notifiche DISABILITATE per {self._centrale_name}")
        
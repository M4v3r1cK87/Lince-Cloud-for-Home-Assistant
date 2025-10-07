from .api import GoldCloudAPI
from .coordinator import GoldCloudCoordinator
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
import logging
import asyncio
import voluptuous as vol
_LOGGER = logging.getLogger(__name__)

platforms = ["sensor", "switch", "binary_sensor", "alarm_control_panel"]

async def async_setup_entry(hass, config_entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    # Inizializza il flag delle notifiche a True (verrà sovrascritto dallo switch quando carica)
    hass.data[DOMAIN]["notifications_enabled"] = {}
    
    email = config_entry.data["email"]
    password = config_entry.data["password"]

    api = GoldCloudAPI(hass, email, password)
    
    # Tenta il login iniziale senza bloccare il setup
    try:
        await api.login(email, password)
        _LOGGER.info("Login iniziale completata con successo")
    except Exception as e:
        _LOGGER.warning("Login iniziale fallita: %s. L'integrazione riproverà automaticamente", e)
        # Non bloccare il setup - il coordinator gestirà i retry

    coordinator = GoldCloudCoordinator(hass, api, config_entry)
    
    # Non bloccare se il primo refresh fallisce
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.warning("Primo refresh fallito: %s. Continuo con setup, retry automatico attivo", e)

    hass.data[DOMAIN]["api"] = api
    hass.data[DOMAIN]["coordinator"] = coordinator
    _LOGGER.info("LinceCloud config entry setup completed")

     # Registra i servizi se non sono già registrati
    if not hass.services.has_service(DOMAIN, "reload"):
        await _async_setup_services(hass)
    
    # Registra il servizio di reload una sola volta
    async def handle_reload_service(call):
        _LOGGER.info("Manual reload of GoldCloud systems triggered")
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN, "reload_system", handle_reload_service
    )
    
    # Nuovo servizio per fermare tutte le socket
    async def handle_stop_all_sockets(call):
        """Ferma TUTTE le socket attive."""
        _LOGGER.info("Richiesta STOP di TUTTE le socket LinceCloud")
        api = hass.data[DOMAIN].get("api")
        if api:
            for row_id in list(api.socket_clients.keys()):
                _LOGGER.info(f"Fermando socket {row_id}")
                await api.stop_socket_connection(row_id)
        _LOGGER.info("Tutte le socket LinceCloud sono state fermate")
    
    hass.services.async_register(
        DOMAIN, "stop_all_sockets", handle_stop_all_sockets
    )

    # Registra handler per chiusura pulita al shutdown
    async def handle_homeassistant_stop(event):
        """Chiudi tutte le socket quando HA si ferma."""
        _LOGGER.info("Home Assistant in chiusura, chiudo tutte le socket...")
        if "api" in hass.data[DOMAIN]:
            try:
                await hass.data[DOMAIN]["api"].close_all_sockets()
                _LOGGER.info("Tutte le socket chiuse correttamente")
            except Exception as e:
                _LOGGER.error(f"Errore durante la chiusura delle socket: {e}")
    
    # Registra l'handler per gli eventi di stop
    hass.bus.async_listen_once("homeassistant_stop", handle_homeassistant_stop)

    await hass.config_entries.async_forward_entry_setups(config_entry, platforms)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Scarica l'integrazione e chiudi tutte le socket."""
    _LOGGER.info("Scaricamento integrazione LinceCloud...")
    
    # Chiudi tutte le socket prima di scaricare
    if "api" in hass.data[DOMAIN]:
        try:
            await hass.data[DOMAIN]["api"].close_all_sockets()
            _LOGGER.info("Socket chiuse durante unload")
        except Exception as e:
            _LOGGER.error(f"Errore chiusura socket durante unload: {e}")
    
    # Cancella il task di retry del coordinator se esiste
    coordinator = hass.data[DOMAIN].get("coordinator")
    if coordinator and hasattr(coordinator, "_retry_task") and coordinator._retry_task:
        coordinator._retry_task.cancel()
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)

    if unload_ok:
        hass.data[DOMAIN] = {}

    return unload_ok

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    """Options changed: aggiorna il coordinator senza ricaricare l'entry."""
    _LOGGER.info("Options changed for %s: refreshing only", entry.entry_id)
    coord = hass.data[DOMAIN].get("coordinator")
    if coord:
        # Riporta dentro al coordinator le nuove opzioni per-centrale
        coord.systems_config = entry.options.get("systems_config", {})
        await coord.async_request_refresh()

async def _async_setup_services(hass: HomeAssistant) -> None:
    """Registra i servizi dell'integrazione."""
    
    async def handle_reload(call):
        """Gestisce il servizio di reload."""
        _LOGGER.info("Ricaricamento integrazione LinceCloud richiesto")
        # Ricarica tutte le entry
        for entry in hass.config_entries.async_entries(DOMAIN):
            await hass.config_entries.async_reload(entry.entry_id)
    
    async def handle_sync_zones(call):
        """Gestisce la sincronizzazione delle zone."""
        centrale_id = call.data.get("centrale_id")
        _LOGGER.info(f"Sincronizzazione zone richiesta per centrale: {centrale_id or 'tutte'}")
        
        coordinator = hass.data[DOMAIN]["coordinator"]
        if coordinator:
            await coordinator.async_request_refresh()
    
    async def handle_reset_alarm_memory(call):
        """Resetta la memoria allarmi."""
        centrale_id = call.data.get("centrale_id")
        _LOGGER.info(f"Reset memoria allarmi per centrale: {centrale_id}")
        
        # Implementa la logica per resettare la memoria
        api = hass.data[DOMAIN]["api"]
        if api and hasattr(api, 'zone_sensors'):
            if centrale_id in api.zone_sensors:
                # Reset degli attributi delle zone
                for zone_type in ['filare', 'radio']:
                    for zone_num, zone_entity in api.zone_sensors[centrale_id].get(zone_type, {}).items():
                        if zone_entity:
                            # Resetta gli attributi di memoria
                            if hasattr(zone_entity, '_attr_extra_state_attributes'):
                                zone_entity._attr_extra_state_attributes['Memoria Allarme'] = False
                                zone_entity._attr_extra_state_attributes['Memoria 24h'] = False
                                zone_entity.safe_update()
    
    async def handle_force_websocket_restart(call):
        """Riavvia forzatamente il WebSocket."""
        centrale_id = call.data.get("centrale_id")
        _LOGGER.info(f"Riavvio WebSocket per centrale: {centrale_id}")
        
        api = hass.data[DOMAIN]["api"]
        if api:
            try:
                await api.stop_socket_connection(int(centrale_id))
                await asyncio.sleep(2)
                await api.start_socket_connection(int(centrale_id))
            except Exception as e:
                _LOGGER.error(f"Errore riavvio WebSocket: {e}")
    
    # Registra i servizi
    hass.services.async_register(DOMAIN, "reload", handle_reload)
    hass.services.async_register(DOMAIN, "sync_zones", handle_sync_zones)
    hass.services.async_register(DOMAIN, "reset_alarm_memory", handle_reset_alarm_memory)
    hass.services.async_register(DOMAIN, "force_websocket_restart", handle_force_websocket_restart)

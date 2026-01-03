"""Integrazione Lince Alarm per Home Assistant."""
from __future__ import annotations
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from .const import DOMAIN
from .euronet.const import (
    CONF_LOCAL_MODE, 
    CONF_HOST,
    CONF_PORT,
    CONF_PASSWORD,
    CONF_INSTALLER_CODE,
    DEFAULT_LOCAL_USERNAME,
    DEFAULT_LOCAL_PORT,
)
from .factory import ComponentFactory
import logging
import asyncio
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

platforms = ["sensor", "switch", "binary_sensor", "alarm_control_panel", "button"]


async def _async_remove_entities_from_registry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rimuove tutte le entità dell'integrazione dal registry.
    
    Questo forza la ricreazione completa delle entità al prossimo setup,
    assicurando che nomi, attributi e sw_version vengano aggiornati.
    """
    try:
        entity_registry = er.async_get(hass)
        device_registry = dr.async_get(hass)
        
        # Trova tutte le entità associate a questa config entry
        entities_to_remove = [
            entity.entity_id
            for entity in entity_registry.entities.values()
            if entity.config_entry_id == entry.entry_id
        ]
        
        # Rimuovi le entità
        for entity_id in entities_to_remove:
            entity_registry.async_remove(entity_id)
        
        # Trova e rimuovi i device associati a questa config entry
        devices_to_remove = [
            device.id
            for device in device_registry.devices.values()
            if entry.entry_id in device.config_entries
        ]
        
        for device_id in devices_to_remove:
            device_registry.async_remove_device(device_id)
        
        _LOGGER.debug(
            "Rimossi %d entità e %d device dal registry per ricreazione",
            len(entities_to_remove), len(devices_to_remove)
        )
    except Exception as e:
        _LOGGER.warning("Errore rimozione entità dal registry: %s", e)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry to new version."""
    _LOGGER.debug(f"Migrating from version {config_entry.version}")
    
    if config_entry.version == 1:
        # Versione 1 -> 2: aggiungiamo CONF_LOCAL_MODE = False per entry cloud esistenti
        new_data = {**config_entry.data}
        new_data[CONF_LOCAL_MODE] = False
        
        hass.config_entries.async_update_entry(
            config_entry, 
            data=new_data,
            version=2
        )
        _LOGGER.debug("Migration to version 2 successful")
    
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Lince Alarm from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["notifications_enabled"] = {}
    
    # Controlla se è modalità locale o cloud
    local_mode = config_entry.data.get(CONF_LOCAL_MODE, False)
    
    if local_mode:
        return await _async_setup_local_entry(hass, config_entry)
    else:
        return await _async_setup_cloud_entry(hass, config_entry)


async def _async_setup_local_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Setup per connessione locale diretta alla centrale."""
    _LOGGER.debug("Configurazione modalità LOCALE")
    
    host = config_entry.data[CONF_HOST]
    port = config_entry.data.get(CONF_PORT, DEFAULT_LOCAL_PORT)
    password = config_entry.data[CONF_PASSWORD]
    installer_code = config_entry.data.get(CONF_INSTALLER_CODE, "")
    
    # Importa client locale
    from .euronet import EuroNetClient
    from .euronet.coordinator import EuroNetCoordinator
    
    # Crea client locale (username è sempre "admin")
    client = EuroNetClient(
        host=host,
        port=port,
        username=DEFAULT_LOCAL_USERNAME,
        password=password,
    )
    
    # Codice installatore: per leggere configurazioni zone/tempi
    # Il codice utente per arm/disarm viene inserito real-time nel pannello allarme
    client.installer_code = installer_code
    
    # Crea coordinator locale
    coordinator = EuroNetCoordinator(hass, client, config_entry)
    
    # =========================================================================
    # FASE 1: Login e caricamento configurazioni PRIMA di creare le entità
    # =========================================================================
    
    # Effettua login con codice installatore (se configurato)
    # per caricare le configurazioni zone (nomi, tempi, programmi)
    # Retry fino a 3 volte con delay crescente per dare tempo alla centrale
    if installer_code:
        login_success = False
        for attempt in range(3):
            try:
                if attempt > 0:
                    delay = attempt * 2  # 2s, 4s
                    await asyncio.sleep(delay)
                
                login_success = await hass.async_add_executor_job(
                    client.login, installer_code
                )
                if login_success:
                    break
            except Exception as e:
                _LOGGER.debug("Tentativo login %d fallito: %s", attempt + 1, e)
        
        if not login_success:
            _LOGGER.warning("Login con codice installatore fallito dopo 3 tentativi")
    
    # Carica configurazioni zone (nomi, tipologie, tempi, ecc.)
    # Questo deve avvenire PRIMA della creazione delle entità
    try:
        await coordinator._async_load_zone_configs()
        if coordinator.zone_configs:
            _LOGGER.info(
                "Configurazioni zone caricate: %d filari, %d radio",
                len(coordinator.zone_configs.zone_filari),
                len(coordinator.zone_configs.zone_radio)
            )
    except Exception as e:
        _LOGGER.warning("Errore caricamento configurazioni zone: %s", e)
    
    # =========================================================================
    # FASE 2: Primo refresh per ottenere stato corrente
    # =========================================================================
    
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.warning("Primo refresh locale fallito: %s - Retry automatico attivo", e)
    
    # =========================================================================
    # FASE 3: Salva in hass.data e crea piattaforme
    # =========================================================================
    hass.data[DOMAIN]["local_mode"] = True
    hass.data[DOMAIN]["local_client"] = client
    hass.data[DOMAIN]["coordinator"] = coordinator
    hass.data[DOMAIN]["api"] = None  # Non usato in modalità locale
    hass.data[DOMAIN]["primary_brand"] = "lince-europlus"
    
    _LOGGER.info("Lince Alarm LOCAL setup completato: %s:%d", host, port)
    
    # Setup delle piattaforme
    await hass.config_entries.async_forward_entry_setups(config_entry, platforms)
    
    return True


async def _async_setup_cloud_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Setup per connessione cloud (comportamento originale)."""
    _LOGGER.debug("Configurazione modalità CLOUD")
    
    email = config_entry.data.get("email")
    password = config_entry.data.get("password")
    
    if not email or not password:
        _LOGGER.error("Credenziali cloud mancanti")
        return False

    # API comune per login iniziale e fetch systems
    from .common.api import CommonAPI
    common_api = CommonAPI(hass, email, password)
    
    # Variabili per gestire brand e sistemi
    brands_count = {}
    systems = []
    primary_brand = "lince-europlus"  # Default
    
    try:
        # Login iniziale
        await common_api.login(email, password)
        _LOGGER.debug("Login iniziale completata con successo")
        
        # Fetch systems per determinare i brand
        systems = await common_api.fetch_systems() or []
        
        # Conta i brand presenti
        for system in systems:
            brand = ComponentFactory.get_brand_from_system(system)
            brands_count[brand] = brands_count.get(brand, 0) + 1
            # Aggiungi il brand al sistema per uso futuro
            system["_detected_brand"] = brand
        
        # Determina il brand primario (quello con più sistemi)
        if brands_count:
            primary_brand = max(brands_count, key=brands_count.get)
            _LOGGER.debug(f"Brand rilevati: {brands_count}. Primario: {primary_brand}")
        
    except Exception as e:
        _LOGGER.warning("Login iniziale fallita o impossibile recuperare sistemi: %s", e)
        # Continua con default brand
    
    # Crea API e Coordinator specifici per il brand primario
    api = ComponentFactory.get_api(primary_brand, hass, email, password)
    
    # Trasferisci token se disponibile
    if hasattr(common_api, 'token') and common_api.token:
        api.token = common_api.token
        api.token_expiry = common_api.token_expiry
    
    # Crea coordinator per il brand primario
    coordinator = ComponentFactory.get_coordinator(primary_brand, hass, api, config_entry)
    
    # Salva informazioni sui brand per uso futuro
    hass.data[DOMAIN]["local_mode"] = False
    hass.data[DOMAIN]["brands_count"] = brands_count
    hass.data[DOMAIN]["primary_brand"] = primary_brand
    hass.data[DOMAIN]["systems"] = systems
    
    # Non bloccare se il primo refresh fallisce
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.warning("Primo refresh fallito: %s. Continuo con setup, retry automatico attivo", e)

    hass.data[DOMAIN]["api"] = api
    hass.data[DOMAIN]["coordinator"] = coordinator
    
    _LOGGER.debug(f"Lince Alarm CLOUD setup completato. Brand primario: {primary_brand}")

    # Registra i servizi se non sono già registrati
    if not hass.services.has_service(DOMAIN, "reload"):
        await _async_setup_services(hass)
    
    # Servizio reload systems
    async def handle_reload_service(call):
        _LOGGER.debug("Manual reload of Lince Alarm systems triggered")
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN, "reload_system", handle_reload_service
    )
    
    # Servizio stop tutte le socket
    async def handle_stop_all_sockets(call):
        """Ferma TUTTE le socket attive."""
        _LOGGER.debug("Richiesta STOP di TUTTE le socket Lince Alarm")
        api = hass.data[DOMAIN].get("api")
        if api and hasattr(api, '_socket_clients'):
            for row_id in list(api._socket_clients.keys()):
                _LOGGER.debug(f"Fermando socket {row_id}")
                await api.stop_socket_connection(row_id)
        _LOGGER.debug("Tutte le socket Lince Alarm sono state fermate")
    
    hass.services.async_register(
        DOMAIN, "stop_all_sockets", handle_stop_all_sockets
    )

    # Handler per chiusura pulita al shutdown
    async def handle_homeassistant_stop(event):
        """Chiudi tutte le connessioni quando HA si ferma."""
        _LOGGER.debug("Home Assistant in chiusura, chiudo tutte le connessioni...")
        
        # Shutdown del coordinator (cancella task in background)
        coordinator = hass.data[DOMAIN].get("coordinator")
        if coordinator and hasattr(coordinator, "async_shutdown"):
            try:
                await coordinator.async_shutdown()
                _LOGGER.debug("Shutdown coordinator completato")
            except Exception as e:
                _LOGGER.error(f"Errore shutdown coordinator: {e}")
        
        # Logout da EuroNET locale se in modalità locale
        local_client = hass.data[DOMAIN].get("local_client")
        if local_client:
            try:
                await hass.async_add_executor_job(local_client.logout, True)
                _LOGGER.debug("Logout EuroNET effettuato durante shutdown")
            except Exception as e:
                _LOGGER.error(f"Errore logout EuroNET durante shutdown: {e}")
        
        # Chiudi socket cloud
        api = hass.data[DOMAIN].get("api")
        if api and hasattr(api, 'close_all_sockets'):
            try:
                await api.close_all_sockets()
                _LOGGER.debug("Tutte le socket chiuse correttamente")
            except Exception as e:
                _LOGGER.error(f"Errore durante la chiusura delle socket: {e}")
    
    hass.bus.async_listen_once("homeassistant_stop", handle_homeassistant_stop)

    # Setup delle piattaforme
    await hass.config_entries.async_forward_entry_setups(config_entry, platforms)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Scarica l'integrazione e chiudi tutte le socket."""
    
    # Cancella i task in background del coordinator e fai cleanup
    coordinator = hass.data[DOMAIN].get("coordinator")
    if coordinator:
        # Per modalità locale, usa async_shutdown (include logout)
        if hasattr(coordinator, "async_shutdown"):
            try:
                await coordinator.async_shutdown()
            except Exception as e:
                _LOGGER.error(f"Errore shutdown coordinator: {e}")
        # Per modalità cloud, cancella _retry_task se esiste
        elif hasattr(coordinator, "_retry_task") and coordinator._retry_task:
            coordinator._retry_task.cancel()
    
    # Chiudi tutte le socket prima di scaricare (modalità cloud)
    api = hass.data[DOMAIN].get("api")
    if api and hasattr(api, 'close_all_sockets'):
        try:
            await api.close_all_sockets()
        except Exception as e:
            _LOGGER.error(f"Errore chiusura socket durante unload: {e}")
    
    # Rimuovi le entità dal registry per forzare ricreazione completa al reload
    # Questo assicura che nomi, attributi e sw_version vengano aggiornati
    await _async_remove_entities_from_registry(hass, entry)
    
    # Attendi che la centrale elabori il logout prima di procedere
    # Questo evita problemi di "Chiavi XOR insufficienti" al prossimo login
    local_mode = entry.data.get(CONF_LOCAL_MODE, False)
    if local_mode:
        await asyncio.sleep(2)
    
    # Scarica le piattaforme
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)

    if unload_ok:
        hass.data[DOMAIN] = {}

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    """Options changed: aggiorna il coordinator senza ricaricare l'entry."""
    _LOGGER.debug("Options changed for %s: refreshing only", entry.entry_id)
    
    # Controlla se siamo in modalità locale
    local_mode = entry.data.get(CONF_LOCAL_MODE, False)
    
    coord = hass.data[DOMAIN].get("coordinator")
    if coord:
        if local_mode:
            # Modalità locale: aggiorna polling interval se cambiato
            from .euronet.const import CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL_MS
            new_polling = entry.options.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL_MS)
            if hasattr(coord, 'update_polling_interval'):
                coord.update_polling_interval(new_polling)
            
            # Verifica se il codice installatore è stato aggiunto/modificato
            # In questo caso forziamo il reload delle configurazioni zone
            installer_code = entry.data.get(CONF_INSTALLER_CODE, "")
            if installer_code and hasattr(coord, 'reset_zone_configs_cache'):
                # Il codice installatore è presente, resetta la cache per ricaricare le zone
                coord.reset_zone_configs_cache()
                _LOGGER.debug("Installer code presente - zone configs verranno ricaricate")
        else:
            # Modalità cloud: aggiorna le opzioni nel coordinator
            coord.systems_config = entry.options.get("systems_config", {})
            coord.arm_profiles = entry.options.get("arm_profiles", {})
        
        await coord.async_request_refresh()


async def _async_setup_services(hass: HomeAssistant) -> None:
    """Registra i servizi dell'integrazione."""
    
    async def handle_reload(call):
        """Gestisce il servizio di reload."""
        _LOGGER.info("Ricaricamento integrazione Lince Alarm richiesto")
        for entry in hass.config_entries.async_entries(DOMAIN):
            await hass.config_entries.async_reload(entry.entry_id)
    
    async def handle_sync_zones(call):
        """Gestisce la sincronizzazione delle zone."""
        centrale_id = call.data.get("centrale_id")
        _LOGGER.info(f"Sincronizzazione zone richiesta per centrale: {centrale_id or 'tutte'}")
        
        coordinator = hass.data[DOMAIN].get("coordinator")
        if coordinator:
            await coordinator.async_request_refresh()
    
    async def handle_reset_alarm_memory(call):
        """Resetta la memoria allarmi."""
        centrale_id = call.data.get("centrale_id")
        _LOGGER.info(f"Reset memoria allarmi per centrale: {centrale_id}")
        
        api = hass.data[DOMAIN].get("api")
        if api and hasattr(api, 'zone_sensors'):
            try:
                centrale_int = int(centrale_id) if centrale_id else None
                if centrale_int and centrale_int in api.zone_sensors:
                    for zone_type in ['filare', 'radio']:
                        zones = api.zone_sensors[centrale_int].get(zone_type, {})
                        for zone_num, zone_entity in zones.items():
                            if zone_entity and hasattr(zone_entity, '_attr_extra_state_attributes'):
                                zone_entity._attr_extra_state_attributes['Memoria Allarme'] = False
                                zone_entity._attr_extra_state_attributes['Memoria 24h'] = False
                                if hasattr(zone_entity, 'safe_update'):
                                    zone_entity.safe_update()
            except Exception as e:
                _LOGGER.error(f"Errore reset memoria allarmi: {e}")
    
    async def handle_force_websocket_restart(call):
        """Riavvia forzatamente il WebSocket."""
        centrale_id = call.data.get("centrale_id")
        _LOGGER.info(f"Riavvio WebSocket per centrale: {centrale_id}")
        
        api = hass.data[DOMAIN].get("api")
        if api and hasattr(api, 'stop_socket_connection'):
            try:
                centrale_int = int(centrale_id) if centrale_id else None
                if centrale_int:
                    await api.stop_socket_connection(centrale_int)
                    await asyncio.sleep(2)
                    if hasattr(api, 'start_socket_connection'):
                        await api.start_socket_connection(centrale_int)
            except Exception as e:
                _LOGGER.error(f"Errore riavvio WebSocket: {e}")
    
    # Registra i servizi
    hass.services.async_register(DOMAIN, "reload", handle_reload)
    hass.services.async_register(DOMAIN, "sync_zones", handle_sync_zones)
    hass.services.async_register(DOMAIN, "reset_alarm_memory", handle_reset_alarm_memory)
    hass.services.async_register(DOMAIN, "force_websocket_restart", handle_force_websocket_restart)
    
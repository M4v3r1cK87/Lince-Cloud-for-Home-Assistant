"""Coordinator implementation for Lince Europlus."""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant

from .parser import europlusParser
from ..utils import send_persistent_notification, dismiss_persistent_notification, send_notification
from ..const import DOMAIN, RETRY_INTERVAL, MAX_RETRY_INTERVAL, INITIAL_RETRY_INTERVAL
from ..common.base_coordinator import BaseCoordinator
from .const import DEFAULT_FILARI, DEFAULT_RADIO

_LOGGER = logging.getLogger(__name__)


class EuroplusCoordinator(BaseCoordinator):
    """Coordinator specific to Lince Europlus."""
    
    def __init__(self, hass: HomeAssistant, api, config_entry):
        """Initialize Europlus coordinator."""
        # Inizializza la classe base
        super().__init__(
            hass, 
            api, 
            config_entry,
            update_interval=timedelta(seconds=10)
        )
        
        self.socket_messages = {}
        
        # Converti le chiavi stringa in interi per systems_config
        raw_systems_config = config_entry.options.get("systems_config", {})
        self.systems_config = {}
        
        for key, value in raw_systems_config.items():
            try:
                int_key = int(key)
                self.systems_config[int_key] = value
                _LOGGER.debug(f"Convertita chiave '{key}' (str) -> {int_key} (int): {value}")
            except (ValueError, TypeError):
                _LOGGER.warning(f"Impossibile convertire chiave '{key}' in intero")
                self.systems_config[key] = value
        
        self.Email = config_entry.data["email"]
        self.Password = config_entry.data["password"]
        
        # Retry mechanism
        self._retry_task = None
        self._retry_count = 0
        self._last_successful_update = None
        self._connection_failed = False
        self._retry_interval = INITIAL_RETRY_INTERVAL
        self._notification_id = "lincecloud_connection_error"
        self._was_offline = False
        self._pause_auto_update = False
        self._notification_cleanup_task = None
        self._row_id = None

    def _get_counts_for_system(self, system_id: int) -> tuple:
        """Get zone counts for a specific Europlus system."""
        try:
            sid_int = int(system_id)
        except (ValueError, TypeError):
            _LOGGER.error(f"system_id non valido: {system_id}")
            return DEFAULT_FILARI, DEFAULT_RADIO
        
        cfg = self.systems_config.get(sid_int)
        
        if cfg is None:
            _LOGGER.warning(
                f"Nessuna configurazione trovata per centrale {sid_int}. "
                f"Chiavi disponibili: {list(self.systems_config.keys())}"
            )
            return DEFAULT_FILARI, DEFAULT_RADIO
        
        nf = int(cfg.get("num_filari", DEFAULT_FILARI))
        nr = int(cfg.get("num_radio", DEFAULT_RADIO))
        
        _LOGGER.debug(f"Config Europlus per centrale {sid_int}: filari={nf}, radio={nr}")
        return nf, nr

    async def _async_update_data(self) -> list[dict]:
        """Fetch data from Europlus API."""
        if self._pause_auto_update:
            _LOGGER.debug("Update automatico in pausa, salto questo ciclo")
            return self.data or []

        try:
            if not self.api.token:
                _LOGGER.info("Token mancante, eseguo login...")
                await self.api.login(self.Email, self.Password)
                
                # Login riuscita, cancella notifica errore se presente
                if self._connection_failed:
                    await self._clear_error_notification()

            # Fetch systems
            systems = await self.api.fetch_systems()
            
            # Per ogni sistema, fetch access data e parsa zone/chiavi
            for system in systems:
                try:
                    self._row_id = system["id"]
                    row_id = self._row_id
                    
                    # Fetch access data
                    system["access_data"] = await self.api.fetch_system_access(row_id)
                    
                    # Parse zone names usando Europlus parser
                    if system.get("access_data") and "store" in system.get("access_data", {}):
                        num_filari, num_radio = self._get_counts_for_system(row_id)
                        
                        parser = europlusParser(None)
                        zonesName = parser.parseZones(
                            system["access_data"]["store"], 
                            num_filari, 
                            num_radio
                        )
                        system["zonesName"] = zonesName
                        
                        # Parse keys names
                        keysName = parser.parse_keysName(system["access_data"]["store"])
                        system["keysName"] = keysName
                    else:
                        system["zonesName"] = {"filare": [], "radio": []}
                        system["keysName"] = []
                        
                except Exception as e:
                    _LOGGER.error(f"Errore parsing dati per sistema {system.get('id')}: {e}")
                    system["zonesName"] = {"filare": [], "radio": []}
                    system["keysName"] = []
            
            # Update riuscito
            self._last_successful_update = datetime.now()
            self._retry_count = 0
            self._retry_interval = INITIAL_RETRY_INTERVAL
            
            if self._connection_failed:
                await self._clear_error_notification()
                self._connection_failed = False
                self._was_offline = False
            
            return systems
            
        except Exception as e:
            _LOGGER.error(f"Errore durante update Europlus: {e}")
            
            # Gestione retry con backoff
            if not self._connection_failed:
                self._connection_failed = True
                await self._show_error_notification(str(e))
            
            # Schedule retry
            if self._retry_task is None or self._retry_task.done():
                self._retry_task = asyncio.create_task(self._schedule_retry())
            
            # Ritorna dati cached se disponibili
            if self.data:
                return self.data
            
            raise UpdateFailed(f"Impossibile aggiornare dati Europlus: {e}")

    async def _schedule_retry(self):
        """Schedule retry con exponential backoff."""
        try:
            await asyncio.sleep(self._retry_interval)
            
            # Aumenta intervallo per prossimo retry (max 30 min)
            self._retry_interval = min(self._retry_interval * 2, MAX_RETRY_INTERVAL)
            self._retry_count += 1
            
            _LOGGER.info(f"Tentativo retry #{self._retry_count} dopo {self._retry_interval}s")
            await self.async_request_refresh()
            
        except Exception as e:
            _LOGGER.error(f"Errore durante retry: {e}")

    async def _show_error_notification(self, error: str):
        """Mostra notifica errore connessione."""
        await send_persistent_notification(
            self.hass,
            f"Impossibile connettersi al cloud Lince Europlus: {error}. "
            "L'integrazione riproverà automaticamente.",
            "Errore connessione LinceCloud Europlus",
            self._notification_id
        )

    async def _clear_error_notification(self):
        """Rimuovi notifica errore."""
        await dismiss_persistent_notification(self.hass, self._notification_id)
        
        if self._was_offline:
            # Notifica ripristino connessione
            await send_notification(
                self.hass,
                "Connessione al cloud Lince Europlus ripristinata",
                "LinceCloud Europlus Online"
            )

    def pause_auto_update(self):
        """Metti in pausa gli update automatici."""
        self._pause_auto_update = True
        _LOGGER.debug("Update automatici Europlus in pausa")

    def resume_auto_update(self):
        """Riprendi gli update automatici."""
        self._pause_auto_update = False
        _LOGGER.debug("Update automatici Europlus ripresi")
        
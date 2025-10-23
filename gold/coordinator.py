"""Coordinator implementation for Lince Gold."""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant

from ..utils import send_persistent_notification, dismiss_persistent_notification, send_notification
from ..const import DOMAIN, RETRY_INTERVAL, MAX_RETRY_INTERVAL, INITIAL_RETRY_INTERVAL
from ..common.base_coordinator import BaseCoordinator
from .api import GoldAPI
from .const import DEFAULT_FILARI, DEFAULT_RADIO

_LOGGER = logging.getLogger(__name__)


class GoldCoordinator(BaseCoordinator):
    """Coordinator specific to Lince Gold."""
    
    def __init__(self, hass: HomeAssistant, api: GoldAPI, config_entry):
        """Initialize Gold coordinator."""
        # Inizializza la classe base - STESSO INTERVAL DI EUROPLUS
        super().__init__(
            hass, 
            api, 
            config_entry,
            update_interval=timedelta(seconds=10)  # STESSO DI EUROPLUS
        )
        
        self.socket_messages = {}
        self._socket_tasks = {}
        
        # STESSA LOGICA EUROPLUS - Legge configurazione zone da config_entry
        self.systems_config = {}
        if "systems_config" in config_entry.data:
            self.systems_config = config_entry.data["systems_config"]
            _LOGGER.debug(f"GoldCoordinator: Loaded systems config: {self.systems_config}")
        elif "systems_config" in config_entry.options:
            self.systems_config = config_entry.options["systems_config"]
            _LOGGER.debug(f"GoldCoordinator: Loaded systems config from options: {self.systems_config}")
        
        self.Email = config_entry.data["email"]
        self.Password = config_entry.data["password"]
        
        # Retry mechanism - IDENTICO A EUROPLUS
        self._retry_task = None
        self._retry_count = 0
        self._last_successful_update = None
        self._connection_failed = False
        self._retry_interval = INITIAL_RETRY_INTERVAL
        self._notification_id = "lincecloud_gold_connection_error"
        self._was_offline = False
        self._pause_auto_update = False
        self._notification_cleanup_task = None
        
        _LOGGER.info("GoldCoordinator initialized")

    def _get_counts_for_system(self, system: dict) -> Tuple[int, int]:
        """
        Ritorna il numero di zone filari e radio per un sistema.
        """
        row_id = system.get("id")
        if not row_id:
            return DEFAULT_FILARI, DEFAULT_RADIO
        
        # Cerca prima in options (priorità), poi in data
        config = self.config_entry.options.get("systems_config", {}).get(str(row_id), {})
        if not config:
            config = self.config_entry.data.get("systems_config", {}).get(str(row_id), {})
        
        # Se non c'è config salvata, usa defaults Gold
        num_filari = int(config.get("num_filari", DEFAULT_FILARI))  # Default Gold: 0
        num_radio = int(config.get("num_radio", DEFAULT_RADIO))   # Default Gold: 0
        
        _LOGGER.debug(f"GoldCoordinator: System {row_id} zone counts: filari={num_filari}, radio={num_radio}")
        return (num_filari, num_radio)

    async def _async_update_data(self) -> list[dict]:
        """Fetch data from Gold API."""
        if self._pause_auto_update:
            _LOGGER.debug("Update automatico Gold in pausa, salto questo ciclo")
            return self.data or []

        try:
            _LOGGER.debug("GoldCoordinator: Starting update cycle")
            
            # 1. Login se necessario - IDENTICO A EUROPLUS
            if not self.api.is_authenticated():
                _LOGGER.info("Token mancante o scaduto, eseguo login Gold...")
                success = await self.api.login()
                
                if not success:
                    raise UpdateFailed("Login Gold fallito")
                
                _LOGGER.info("Login Gold completato con successo")
                
                if self._connection_failed:
                    await self._clear_error_notification()

            # 2. Fetch systems - IDENTICO A EUROPLUS
            systems = await self.api.get_systems()
            
            _LOGGER.debug(f"GoldCoordinator: Found {len(systems)} Gold systems")
            
            # 3. Per ogni sistema - STESSA LOGICA EUROPLUS
            for system in systems:
                try:
                    system_id = system.get("id")
                    centrale_id = system.get("IdCentrale")
                    
                    if not centrale_id:
                        _LOGGER.warning(f"Sistema senza IdCentrale: {system}")
                        continue
                    
                    # IDENTICO A EUROPLUS - Recupera access_data via REST
                    if system_id:
                        _LOGGER.debug(f"Fetching system_access for system {system_id}")
                        access_data = await self.api.fetch_system_access(system_id)
                        system["access_data"] = access_data
                        _LOGGER.debug(f"Access data for centrale {centrale_id}: {access_data}")

                    # Se c'è uno store nella access_data, parsalo
                        if system.get("access_data") and "store" in system.get("access_data", {}):
                            _LOGGER.debug(f"Gold system {system_id} has store data: {system['access_data']['store']}")
                            num_filari, num_radio = self._get_counts_for_system(system_id)                        
                    
                    # Avvia socket per centrale Gold (questa è la differenza con Europlus)
                    if centrale_id not in self._socket_tasks:
                        _LOGGER.info(f"GoldCoordinator: Starting socket for centrale {centrale_id}")
                        task = asyncio.create_task(
                            self._manage_socket_connection(centrale_id)
                        )
                        self._socket_tasks[centrale_id] = task
                    
                except Exception as e:
                    _LOGGER.error(f"Errore gestione sistema {system.get('id')}: {e}")
            
            # Update riuscito - IDENTICO A EUROPLUS
            self._last_successful_update = datetime.now()
            self._retry_count = 0
            self._retry_interval = INITIAL_RETRY_INTERVAL
            
            if self._connection_failed:
                await self._clear_error_notification()
                self._connection_failed = False
                self._was_offline = False
            
            _LOGGER.debug(f"GoldCoordinator: Update completed - {len(systems)} systems - Systems: {systems}")
            return systems
            
        except Exception as e:
            _LOGGER.error(f"Errore durante update Gold: {e}", exc_info=True)
            
            # Gestione retry - IDENTICA A EUROPLUS
            if not self._connection_failed:
                self._connection_failed = True
                await self._show_error_notification(str(e))
            
            if self._retry_task is None or self._retry_task.done():
                self._retry_task = asyncio.create_task(self._schedule_retry())
            
            if self.data:
                return self.data
            
            raise UpdateFailed(f"Impossibile aggiornare dati Gold: {e}")

    async def _manage_socket_connection(self, centrale_id: int):
        """Manage socket connection for a centrale - SPECIFICO PER GOLD."""
        try:
            _LOGGER.info(f"Socket manager started for Gold centrale {centrale_id}")
            
            while True:
                try:
                    # Connetti socket attraverso l'API
                    success = await self.api.connect_socket(centrale_id)
                    
                    if not success:
                        _LOGGER.error(f"Failed to connect socket for centrale {centrale_id}")
                        await asyncio.sleep(30)
                        continue
                    
                    _LOGGER.info(f"Socket connected for Gold centrale {centrale_id}")
                    
                    # Aspetta che la connessione si chiuda
                    while self.api.is_socket_connected(centrale_id):
                        await asyncio.sleep(5)
                    
                    _LOGGER.warning(f"Socket disconnected for centrale {centrale_id}, will reconnect...")
                    
                except Exception as e:
                    _LOGGER.error(f"Error in socket connection for centrale {centrale_id}: {e}")
                
                await asyncio.sleep(10)
                
        except asyncio.CancelledError:
            _LOGGER.info(f"Socket manager cancelled for centrale {centrale_id}")
            await self.api.disconnect_socket(centrale_id)
            raise
        except Exception as e:
            _LOGGER.error(f"Fatal error in socket manager for centrale {centrale_id}: {e}")

    async def _schedule_retry(self):
        """Schedule retry - IDENTICO A EUROPLUS."""
        try:
            await asyncio.sleep(self._retry_interval)
            
            self._retry_interval = min(self._retry_interval * 2, MAX_RETRY_INTERVAL)
            self._retry_count += 1
            
            _LOGGER.info(f"Gold: Tentativo retry #{self._retry_count} dopo {self._retry_interval}s")
            await self.async_request_refresh()
            
        except Exception as e:
            _LOGGER.error(f"Errore durante retry Gold: {e}")

    async def _show_error_notification(self, error: str):
        """Mostra notifica errore - IDENTICO A EUROPLUS."""
        await send_persistent_notification(
            self.hass,
            f"Impossibile connettersi al cloud Lince Gold: {error}. "
            "L'integrazione riproverà automaticamente.",
            "Errore connessione LinceCloud Gold",
            self._notification_id
        )

    async def _clear_error_notification(self):
        """Rimuovi notifica errore - IDENTICO A EUROPLUS."""
        await dismiss_persistent_notification(self.hass, self._notification_id)
        
        if self._was_offline:
            await send_notification(
                self.hass,
                "Connessione al cloud Lince Gold ripristinata",
                "LinceCloud Gold Online"
            )

    async def async_shutdown(self):
        """Shutdown coordinator."""
        _LOGGER.info("Shutting down Gold coordinator...")
        
        # Cancella task socket
        for centrale_id, task in self._socket_tasks.items():
            _LOGGER.debug(f"Cancelling socket task for centrale {centrale_id}")
            task.cancel()
        
        if self._socket_tasks:
            await asyncio.gather(*self._socket_tasks.values(), return_exceptions=True)
        
        # Disconnetti socket
        await self.api.disconnect_all()
        
        _LOGGER.info("Gold coordinator shutdown complete")

    def pause_auto_update(self):
        """Metti in pausa - IDENTICO A EUROPLUS."""
        self._pause_auto_update = True
        _LOGGER.debug("Update automatici Gold in pausa")

    def resume_auto_update(self):
        """Riprendi - IDENTICO A EUROPLUS."""
        self._pause_auto_update = False
        _LOGGER.debug("Update automatici Gold ripresi")
    
    def get_systems(self) -> List[Dict]:
        """Get systems - IDENTICO A EUROPLUS."""
        if self.data:
            return self.data.get("systems", [])
        return []
    
    def get_centrale_state(self, centrale_id: int) -> Optional[Dict]:
        """Get state - IDENTICO A EUROPLUS."""
        if self.data:
            return self.data.get("states", {}).get(centrale_id)
        return None
    
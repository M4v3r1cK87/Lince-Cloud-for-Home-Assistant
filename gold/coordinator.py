"""Coordinator implementation for Lince Gold."""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant

from ..utils import send_persistent_notification, dismiss_persistent_notification, send_notification
from ..const import DOMAIN, RETRY_INTERVAL, MAX_RETRY_INTERVAL, INITIAL_RETRY_INTERVAL
from ..common.base_coordinator import BaseCoordinator
from .const import DEFAULT_FILARI, DEFAULT_RADIO

_LOGGER = logging.getLogger(__name__)


class GoldCoordinator(BaseCoordinator):
    """Coordinator specific to Lince Gold."""
    
    def __init__(self, hass: HomeAssistant, api, config_entry):
        """Initialize Gold coordinator."""
        # Inizializza la classe base - IDENTICO A EUROPLUS
        super().__init__(
            hass, 
            api, 
            config_entry,
            update_interval=timedelta(seconds=10)
        )
        
        # IDENTICO A EUROPLUS - NO SOCKET MANAGEMENT QUI
        self.socket_messages = {}
        
        # IDENTICO A EUROPLUS - Converti le chiavi stringa in interi per systems_config
        raw_systems_config = config_entry.options.get("systems_config", {})
        self.systems_config = {}
        
        for key, value in raw_systems_config.items():
            try:
                int_key = int(key)
                self.systems_config[int_key] = value
                _LOGGER.debug(f"Gold: Convertita chiave '{key}' (str) -> {int_key} (int): {value}")
            except (ValueError, TypeError):
                _LOGGER.warning(f"Gold: Impossibile convertire chiave '{key}' in intero")
                self.systems_config[key] = value
        
        self.Email = config_entry.data["email"]
        self.Password = config_entry.data["password"]
        
        # IDENTICO A EUROPLUS - Retry mechanism
        self._retry_task = None
        self._retry_count = 0
        self._last_successful_update = None
        self._connection_failed = False
        self._retry_interval = INITIAL_RETRY_INTERVAL
        self._notification_id = "lincecloud_gold_connection_error"  # Solo ID diverso
        self._was_offline = False
        self._pause_auto_update = False
        self._notification_cleanup_task = None
        self._row_id = None

    def _get_counts_for_system(self, system_id: int) -> tuple:
        """Get zone counts for a specific Gold system - IDENTICO A EUROPLUS."""
        try:
            sid_int = int(system_id)
        except (ValueError, TypeError):
            _LOGGER.error(f"Gold: system_id non valido: {system_id}")
            return DEFAULT_FILARI, DEFAULT_RADIO
        
        cfg = self.systems_config.get(sid_int)
        
        if cfg is None:
            _LOGGER.warning(
                f"Gold: Nessuna configurazione trovata per centrale {sid_int}. "
                f"Chiavi disponibili: {list(self.systems_config.keys())}"
            )
            return DEFAULT_FILARI, DEFAULT_RADIO
        
        nf = int(cfg.get("num_filari", DEFAULT_FILARI))
        nr = int(cfg.get("num_radio", DEFAULT_RADIO))
        
        _LOGGER.debug(f"Config Gold per centrale {sid_int}: filari={nf}, radio={nr}")
        return nf, nr

    async def _async_update_data(self) -> list[dict]:
        """Fetch data from Gold API - IDENTICO A EUROPLUS (SENZA SOCKET)."""
        if self._pause_auto_update:
            _LOGGER.debug("Gold: Update automatico in pausa, salto questo ciclo")
            return self.data or []

        try:
            # IDENTICO A EUROPLUS - Check token e login
            if not self.api.token:
                _LOGGER.info("Gold: Token mancante, eseguo login...")
                await self.api.login(self.Email, self.Password)
                
                # Login riuscita, cancella notifica errore se presente
                if self._connection_failed:
                    await self._clear_error_notification()

            # IDENTICO A EUROPLUS - Fetch systems
            systems = await self.api.fetch_systems()
            
            # IDENTICO A EUROPLUS - Per ogni sistema, fetch access data
            for system in systems:
                try:
                    self._row_id = system["id"]
                    row_id = self._row_id
                    
                    # IDENTICO A EUROPLUS - Fetch access data
                    system["access_data"] = await self.api.fetch_system_access(row_id)                                            
                except Exception as e:
                    _LOGGER.error(f"Gold: Errore processing sistema {system.get('id')}: {e}")
            
            # IDENTICO A EUROPLUS - Update riuscito
            self._last_successful_update = datetime.now()
            self._retry_count = 0
            self._retry_interval = INITIAL_RETRY_INTERVAL
            
            if self._connection_failed:
                await self._clear_error_notification()
                self._connection_failed = False
                self._was_offline = False

            _LOGGER.debug(f"Sistemi GOLD: {systems}")
            return systems
            
        except Exception as e:
            _LOGGER.error(f"Gold: Errore durante update: {e}")
            
            # IDENTICO A EUROPLUS - Gestione retry con backoff
            if not self._connection_failed:
                self._connection_failed = True
                await self._show_error_notification(str(e))
            
            # Schedule retry
            if self._retry_task is None or self._retry_task.done():
                self._retry_task = asyncio.create_task(self._schedule_retry())
            
            # Ritorna dati cached se disponibili
            if self.data:
                return self.data
            
            raise UpdateFailed(f"Gold: Impossibile aggiornare dati: {e}")

    async def _schedule_retry(self):
        """IDENTICO A EUROPLUS - Schedule retry con exponential backoff."""
        try:
            await asyncio.sleep(self._retry_interval)
            
            # Aumenta intervallo per prossimo retry (max 30 min)
            self._retry_interval = min(self._retry_interval * 2, MAX_RETRY_INTERVAL)
            self._retry_count += 1
            
            _LOGGER.info(f"Gold: Tentativo retry #{self._retry_count} dopo {self._retry_interval}s")
            await self.async_request_refresh()
            
        except Exception as e:
            _LOGGER.error(f"Gold: Errore durante retry: {e}")

    async def _show_error_notification(self, error: str):
        """IDENTICO A EUROPLUS - Mostra notifica errore connessione."""
        await send_persistent_notification(
            self.hass,
            f"Impossibile connettersi al cloud Lince Gold: {error}. "
            "L'integrazione riproverà automaticamente.",
            "Errore connessione LinceCloud Gold",
            self._notification_id
        )

    async def _clear_error_notification(self):
        """IDENTICO A EUROPLUS - Rimuovi notifica errore."""
        await dismiss_persistent_notification(self.hass, self._notification_id)
        
        if self._was_offline:
            # Notifica ripristino connessione
            await send_notification(
                self.hass,
                "Connessione al cloud Lince Gold ripristinata",
                "LinceCloud Gold Online"
            )

    def pause_auto_update(self):
        """IDENTICO A EUROPLUS - Metti in pausa gli update automatici."""
        self._pause_auto_update = True
        _LOGGER.debug("Gold: Update automatici in pausa")

    def resume_auto_update(self):
        """IDENTICO A EUROPLUS - Riprendi gli update automatici."""
        self._pause_auto_update = False
        _LOGGER.debug("Gold: Update automatici ripresi")

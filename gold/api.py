"""API client for Gold centrals."""
import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from ..common.api import CommonAPI
from .socket_client import GoldSocketClient
from .parser import GoldStateParser, GoldPhysicalMapParser
from .binary_sensor import update_gold_buscomm_binarysensors
from .sensor import update_gold_buscomm_sensors

_LOGGER = logging.getLogger(__name__)


class GoldAPI(CommonAPI):
    """API client specifically for Gold centrals."""
    
    def __init__(self, hass, email: str, password: str):
        """Initialize Gold API."""
        super().__init__(hass, email, password)
        self.brand = "lince-gold"
        
        # Gold specific parsers
        self._state_parser = GoldStateParser()
        self._physical_map_parser = GoldPhysicalMapParser()
        
        # Socket clients per centrale - IDENTICO A EUROPLUS
        self._socket_clients: Dict[int, GoldSocketClient] = {}
        
        # Cache stati
        self._states_cache: Dict[int, Dict] = {}
        self._physical_maps_cache: Dict[int, Dict] = {}
        
        _LOGGER.info("GoldAPI initialized")
    
    def is_socket_connected(self, row_id: int) -> bool:
        """Verifica se la socket è connessa per un sistema - IDENTICO A EUROPLUS."""
        # Per Gold, row_id corrisponde all'IdCentrale
        client = self._socket_clients.get(row_id)
        return client.is_connected() if client else False

    def get_socket_client(self, row_id: int) -> GoldSocketClient | None:
        """Restituisce il client socket - IDENTICO A EUROPLUS."""
        return self._socket_clients.get(row_id)

    async def start_socket_connection(self, row_id: int):
        """Avvia la connessione socket per un sistema - ADATTATO PER GOLD."""
        _LOGGER.debug(f"Avvio connessione socket Gold per centrale {row_id}")
        
        try:
            # Callback per connessione - IDENTICO A EUROPLUS
            async def connect_callback(cb_row_id: int):
                _LOGGER.info(f"[{cb_row_id}] Riconnesso alla socket Gold")

            # Callback per disconnessione - IDENTICO A EUROPLUS
            async def disconnect_callback(cb_row_id: int):
                _LOGGER.warning(f"[{cb_row_id}] Disconnessione dalla socket Gold rilevata")

            # Callback per messaggi - SPECIFICO PER GOLD
            async def message_callback(cb_row_id: int, message):
                _LOGGER.debug(f"[{cb_row_id}] Messaggio socket Gold ricevuto")
                
                # Usa i parser Gold per processare il messaggio
                await self._on_gold_message(cb_row_id, message)

            # Se il token è scaduto, login - IDENTICO A EUROPLUS
            if self.is_token_expired():
                _LOGGER.info("Token scaduto, provo login Gold")
                try:
                    await self.login(self._email, self._password)
                except Exception as e:
                    _LOGGER.warning("[socket %s] Login Gold fallita: %s", row_id, e)
                    return False

            # Se esiste già un client per questa centrale - IDENTICO A EUROPLUS
            if row_id in self._socket_clients:
                client = self._socket_clients[row_id]
                if client.is_connected():
                    _LOGGER.debug(f"Connessione socket Gold già avviata per {row_id}")
                    return True
                else:
                    _LOGGER.info(f"Rimuovo client socket Gold non connesso per {row_id}")
                    await client.stop()
                    self._socket_clients.pop(row_id, None)

            # Crea e avvia il nuovo client socket GOLD
            client = GoldSocketClient(
                token=self.token,
                centrale_id=row_id,
                message_callback=message_callback,
                disconnect_callback=disconnect_callback,
                connect_callback=connect_callback,
                hass=self.hass,
                api=self,
                email=self._email,
                password=self._password
            )

            connected = await client.start()
            if not connected:
                _LOGGER.info(f"[{row_id}] Connessione Gold in corso...")
                await asyncio.sleep(3)
                if not client.is_connected():
                    await client.stop()
                    return False

            self._socket_clients[row_id] = client
            _LOGGER.info(f"Socket Gold {row_id} avviata con successo")
            return True
            
        except Exception as e:
            _LOGGER.error(f"Errore avvio socket Gold {row_id}: {e}", exc_info=True)
            return False

    async def stop_socket_connection(self, row_id: int):
        """Ferma la connessione socket per un sistema - IDENTICO A EUROPLUS."""
        client = self._socket_clients.get(row_id)
        if client:
            try:
                await client.stop()
                _LOGGER.info(f"Socket Gold {row_id} fermata")
            except Exception as e:
                _LOGGER.error(f"Errore durante stop socket Gold {row_id}: {e}")
            finally:
                if row_id in self._socket_clients:
                    del self._socket_clients[row_id]
        
        # Pulisci cache stati
        self._states_cache.pop(row_id, None)
        _LOGGER.info(f"Socket Gold {row_id} completamente fermata")

    async def initialize_socket(self, centrale_id: int) -> bool:
        """Initialize Gold socket for a specific central - WRAPPER per compatibilità."""
        return await self.start_socket_connection(centrale_id)
    
    async def _on_gold_message(self, centrale_id: int, message: Any):
        """Handle Gold socket messages."""
        try:
            _LOGGER.debug(f"Gold message from {centrale_id}: {message}")
            
            # Parse based on message type
            if isinstance(message, dict):
                if message.get("type") == "gold_state":
                    # Already parsed by socket client
                    parsed_state = message.get("data", {})
                    self._states_cache[centrale_id] = parsed_state
                    
                    # IMPORTANTE: Aggiorna i sensori con i dati parsati
                    # I dati sono già nella struttura corretta (stato, alim, prog, ecc.)
                    _LOGGER.debug(f"[{centrale_id}] Aggiornamento sensori Gold con dati parsati")
                    
                    # Aggiorna binary sensors
                    update_gold_buscomm_binarysensors(self, centrale_id, parsed_state)
                    
                    # Aggiorna sensors (voltage, current, firmware, etc.)
                    update_gold_buscomm_sensors(self, centrale_id, parsed_state)
                    
                    # Notify HA of state change
                    if self.hass:
                        self.hass.bus.async_fire(
                            "lince_gold_state_update",
                            {"centrale_id": centrale_id, "state": self._states_cache[centrale_id]}
                        )
                        
        except Exception as e:
            _LOGGER.error(f"Error handling Gold message: {e}", exc_info=True)
    
    async def _on_gold_connect(self, centrale_id: int):
        """Handle Gold socket connection."""
        _LOGGER.info(f"Gold socket connected for central {centrale_id}")
        
        # Request initial state
        # TODO: Discover how to request state
    
    async def _on_gold_disconnect(self, centrale_id: int):
        """Handle Gold socket disconnection."""
        _LOGGER.warning(f"Gold socket disconnected for central {centrale_id}")
    
    async def get_state(self, centrale_id: int) -> Optional[Dict]:
        """Get current state for a Gold central."""
        # Return from cache if available and recent
        if centrale_id in self._states_cache:
            return self._states_cache[centrale_id]
        
        # TODO: Implement HTTP fallback if socket not available
        return None
    
    def get_debug_info(self, centrale_id: int) -> Dict:
        """Get debug info for Gold central."""
        socket = self._socket_clients.get(centrale_id)
        if not socket:
            return {"error": "No socket client"}
        
        return {
            "connected": socket.is_connected(),
            "last_messages": socket.get_last_messages(20),
            "discovered_events": socket.get_discovered_events(),
            "cached_state": self._states_cache.get(centrale_id, {}),
            "parser_state": {
                "armed": self._state_parser.is_armed(),
                "problems": self._state_parser.get_system_problems(),
                "open_zones": self._state_parser.get_open_zones()
            }
        }
    
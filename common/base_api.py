"""Base API class for brand-specific implementations."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import logging

_LOGGER = logging.getLogger(__name__)


class BaseAPI(ABC):
    """Classe base astratta per le API brand-specific."""
    
    def __init__(self, hass, email: Optional[str] = None, password: Optional[str] = None):
        self.hass = hass
        self._email = email
        self._password = password
        self.token: Optional[str] = None
        self.token_expiry = None
        
    @abstractmethod
    async def login(self, email: Optional[str] = None, password: Optional[str] = None):
        """Login al servizio."""
        pass
    
    @abstractmethod
    async def fetch_systems(self):
        """Recupera lista sistemi."""
        pass
    
    @abstractmethod
    async def fetch_system_access(self, row_id: int):
        """Recupera access data di un sistema."""
        pass
        
    @abstractmethod
    async def start_socket_connection(self, row_id: int):
        """Avvia connessione socket per un sistema."""
        pass
    
    @abstractmethod
    async def stop_socket_connection(self, row_id: int):
        """Ferma connessione socket per un sistema."""
        pass
    
    @abstractmethod
    async def send_arm_disarm_command(self, row_id: int, program_mask: int, pin: str):
        """Invia comando arm/disarm."""
        pass
    
    @abstractmethod
    async def close_all_sockets(self):
        """Chiudi tutte le socket aperte."""
        pass
    
    @abstractmethod
    def is_socket_connected(self, row_id: int) -> bool:
        """Verifica se la socket è connessa."""
        pass
    
    def get_last_socket_message(self, row_id: int) -> Optional[str]:
        """Ritorna l'ultimo messaggio ricevuto dalla socket."""
        return None
    
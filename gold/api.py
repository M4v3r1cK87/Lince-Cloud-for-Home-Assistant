"""API client for Gold centrals."""
import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from ..common.api import BaseLinceAPI
from .socket_client import GoldSocketClient
from .parser import GoldStateParser, GoldPhysicalMapParser

_LOGGER = logging.getLogger(__name__)


class GoldAPI(BaseLinceAPI):
    """API client specifically for Gold centrals."""
    
    def __init__(self, hass, email: str, password: str):
        """Initialize Gold API."""
        super().__init__(hass, email, password)
        self.brand = "lince-gold"
        
        # Gold specific parsers
        self._state_parser = GoldStateParser()
        self._physical_map_parser = GoldPhysicalMapParser()
        
        # Socket clients per centrale
        self._socket_clients: Dict[int, GoldSocketClient] = {}
        
        # Cache stati
        self._states_cache: Dict[int, Dict] = {}
        self._physical_maps_cache: Dict[int, Dict] = {}
        
        _LOGGER.info("GoldAPI initialized")
    
    async def initialize_socket(self, centrale_id: int) -> bool:
        """Initialize Gold socket for a specific central."""
        try:
            if centrale_id in self._socket_clients:
                _LOGGER.debug(f"Socket already exists for Gold central {centrale_id}")
                return True
            
            # Create Gold socket client
            socket_client = GoldSocketClient(
                token=self.token,
                centrale_id=centrale_id,
                message_callback=self._on_gold_message,
                disconnect_callback=self._on_gold_disconnect,
                connect_callback=self._on_gold_connect,
                hass=self.hass,
                api=self,
                email=self._email,
                password=self._password
            )
            
            # Start connection
            success = await socket_client.start()
            if success:
                self._socket_clients[centrale_id] = socket_client
                _LOGGER.info(f"Gold socket initialized for central {centrale_id}")
                return True
            else:
                _LOGGER.error(f"Failed to initialize Gold socket for central {centrale_id}")
                return False
                
        except Exception as e:
            _LOGGER.error(f"Error initializing Gold socket: {e}", exc_info=True)
            return False
    
    async def _on_gold_message(self, centrale_id: int, message: Any):
        """Handle Gold socket messages."""
        try:
            _LOGGER.debug(f"Gold message from {centrale_id}: {message}")
            
            # Parse based on message type
            if isinstance(message, dict):
                if message.get("type") == "gold_state":
                    # Already parsed by socket client
                    self._states_cache[centrale_id] = message.get("data", {})
                    
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
    
    async def arm_gold(self, centrale_id: int, pin: str, g1: bool, g2: bool, g3: bool) -> bool:
        """Arm Gold central."""
        try:
            socket = self._socket_clients.get(centrale_id)
            if not socket:
                _LOGGER.error(f"No socket for Gold central {centrale_id}")
                return False
            
            # Send PIN
            await socket.send_gold_pin(pin)
            
            # Wait a bit
            await asyncio.sleep(0.5)
            
            # Send arm command
            await socket.send_gold_arm(g1, g2, g3)
            
            return True
            
        except Exception as e:
            _LOGGER.error(f"Error arming Gold: {e}", exc_info=True)
            return False
    
    async def disarm_gold(self, centrale_id: int, pin: str) -> bool:
        """Disarm Gold central."""
        try:
            socket = self._socket_clients.get(centrale_id)
            if not socket:
                _LOGGER.error(f"No socket for Gold central {centrale_id}")
                return False
            
            # Send PIN
            await socket.send_gold_pin(pin)
            
            # Wait a bit
            await asyncio.sleep(0.5)
            
            # Send disarm (all false)
            await socket.send_gold_arm(False, False, False)
            
            return True
            
        except Exception as e:
            _LOGGER.error(f"Error disarming Gold: {e}", exc_info=True)
            return False
    
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
                "problems": self._state_parser.get_problemi_sistema(),
                "open_zones": self._state_parser.get_zone_aperte()
            }
        }
    
"""Socket.IO client specifico per Lince Gold con logging completo."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Optional, Dict
from datetime import datetime

from ..common.socket_client import BaseSocketClient
from .parser import GoldStateParser
from ..const import API_SOCKET_IO_URL, DOMAIN
from .const import SOCKET_NAMESPACE

_LOGGER = logging.getLogger(__name__)

class GoldSocketClient(BaseSocketClient):
    """Client Socket.IO specifico per centrali Gold con debug esteso."""
    
    def __init__(self, *args, **kwargs):
        """Initialize Gold socket client."""
        super().__init__(*args, **kwargs)
        
        # Parser Gold
        self._state_parser = GoldStateParser()
        
        # Storage per debug
        self._last_messages = []
        self._max_messages = 100
        
        # Eventi Gold specifici
        self._gold_events = {}
        
        _LOGGER.info(f"[{self.centrale_id}] GoldSocketClient initialized")
    
    def _build_connect_url(self) -> str:
        """URL specifico Gold."""
        # Assumo stesso pattern di Europlus per ora
        url = f"{API_SOCKET_IO_URL}/?token={self.token}&system_id={self.centrale_id}"
        _LOGGER.debug(f"[{self.centrale_id}] Gold connect URL: {url}")
        return url
    
    def _get_namespace(self) -> str:
        """Namespace specifico Gold."""
        _LOGGER.debug(f"[{self.centrale_id}] Gold namespace: {SOCKET_NAMESPACE}")
        return SOCKET_NAMESPACE
    
    def _register_handlers(self):
        """Registra TUTTI gli handler possibili per debug massivo."""
        namespace = SOCKET_NAMESPACE
        
        # Handler base
        self.sio.on("connect", self.on_connect, namespace=namespace)
        self.sio.on("disconnect", self.on_disconnect, namespace=namespace)
        self.sio.on("connect_error", self.on_connect_error, namespace=namespace)
        
        # Handler specifici Gold già visti
        self.sio.on("onGoldState", self.on_gold_state, namespace=namespace)
        
        # Handler generici per catturare tutto
        self.sio.on("message", self.on_message, namespace=namespace)
        self.sio.on("*", self.on_any_event, namespace=namespace)
        
        # Possibili altri eventi Gold (da scoprire)
        possible_events = [
            "onStatus", "status", "state", "goldStatus",
            "alarm", "onAlarm", "goldAlarm",
            "event", "onEvent", "goldEvent",
            "update", "onUpdate", "goldUpdate",
            "command", "onCommand", "goldCommand",
            "response", "onResponse", "goldResponse",
            "notification", "onNotification",
            "error", "onError", "goldError",
            "ping", "pong", "heartbeat"
        ]
        
        for event in possible_events:
            self.sio.on(event, lambda data, e=event: self.on_discovered_event(e, data), namespace=namespace)
        
        _LOGGER.info(f"[{self.centrale_id}] Registered {len(possible_events) + 6} event handlers for discovery")
    
    # ------------------------------ Event handlers GOLD ------------------------------
    
    async def on_connect(self):
        """Handler connessione Gold."""
        self._connected = True
        self._connected_event.set()
        self._reconnect_backoff = 2.0
        
        _LOGGER.info(f"[{self.centrale_id}] Gold Socket.IO connected")
        _LOGGER.debug(f"[{self.centrale_id}] Connection details: namespace={SOCKET_NAMESPACE}")
        
        # Log session info
        if self.sio:
            _LOGGER.debug(f"[{self.centrale_id}] Session ID: {self.sio.sid}")
        
        if self.connect_callback:
            await self.connect_callback(self.centrale_id)
    
    async def on_disconnect(self):
        """Handler disconnessione Gold."""
        self._connected = False
        self._connected_event.clear()
        
        _LOGGER.warning(f"[{self.centrale_id}] Gold Socket.IO disconnected")
        
        if self.disconnect_callback:
            await self.disconnect_callback(self.centrale_id)
    
    async def on_connect_error(self, data: Any = None):
        """Handler errore connessione Gold."""
        _LOGGER.error(f"[{self.centrale_id}] Gold connection error: {data}")
        
        # Log dettagliato dell'errore
        if isinstance(data, dict):
            for key, value in data.items():
                _LOGGER.debug(f"[{self.centrale_id}] Error detail - {key}: {value}")
        
        # Check autenticazione
        from ..common.socket_client import _UNAUTH_STRINGS
        msg = str(data or "").lower()
        
        if any(s in msg for s in _UNAUTH_STRINGS):
            _LOGGER.warning(f"[{self.centrale_id}] Authentication error detected")
            await self._handle_unauthorized()
        else:
            await self._schedule_reconnect_backoff("gold_connect_error")
    
    async def on_message(self, data):
        """Handler messaggio generico Gold."""
        timestamp = datetime.now().isoformat()
        _LOGGER.debug(f"[{self.centrale_id}] Gold message received at {timestamp}")
        _LOGGER.debug(f"[{self.centrale_id}] Message type: {type(data)}")
        _LOGGER.debug(f"[{self.centrale_id}] Message content: {data}")
        
        self._store_message("message", data, timestamp)
        
        if self.message_callback:
            await self.message_callback(self.centrale_id, data)
    
    async def on_any_event(self, event, data):
        """Handler catch-all per TUTTI gli eventi."""
        timestamp = datetime.now().isoformat()
        
        # Log massivo
        _LOGGER.debug(f"[{self.centrale_id}] ===== GOLD EVENT CAPTURED =====")
        _LOGGER.debug(f"[{self.centrale_id}] Timestamp: {timestamp}")
        _LOGGER.debug(f"[{self.centrale_id}] Event name: '{event}'")
        _LOGGER.debug(f"[{self.centrale_id}] Data type: {type(data)}")
        
        # Log dettagliato del contenuto
        if isinstance(data, dict):
            _LOGGER.debug(f"[{self.centrale_id}] Data keys: {list(data.keys())}")
            for key, value in data.items():
                if isinstance(value, (list, dict)):
                    _LOGGER.debug(f"[{self.centrale_id}]   {key}: {type(value)} with {len(value)} items")
                else:
                    _LOGGER.debug(f"[{self.centrale_id}]   {key}: {value}")
        else:
            _LOGGER.debug(f"[{self.centrale_id}] Data: {data}")
        
        _LOGGER.debug(f"[{self.centrale_id}] ==============================")
        
        self._store_message(event, data, timestamp)
        
        # Se è un evento non gestito, memorizza
        if event not in ["connect", "disconnect", "connect_error", "message", "onGoldState"]:
            self._gold_events[event] = self._gold_events.get(event, 0) + 1
            if self._gold_events[event] == 1:  # Prima volta che vediamo questo evento
                _LOGGER.debug(f"[{self.centrale_id}] DISCOVERED NEW EVENT: '{event}'")
    
    async def on_discovered_event(self, event: str, data: Any):
        """Handler per eventi scoperti dinamicamente."""
        timestamp = datetime.now().isoformat()
        _LOGGER.debug(f"[{self.centrale_id}] Discovered event '{event}' triggered at {timestamp}")
        _LOGGER.debug(f"[{self.centrale_id}] Event '{event}' data: {data}")
        
        self._store_message(f"discovered_{event}", data, timestamp)
    
    async def on_gold_state(self, data):
        """Handler specifico per stato Gold."""
        timestamp = datetime.now().isoformat()
        _LOGGER.debug(f"[{self.centrale_id}] ===== GOLD STATE RECEIVED =====")
        _LOGGER.debug(f"[{self.centrale_id}] Timestamp: {timestamp}")
        
        # Log raw data
        _LOGGER.debug(f"[{self.centrale_id}] Raw state data: {data}")

        # Inizializza parsed a None
        parsed = None
        
        # Parse con il parser
        try:
            parsed = self._state_parser.parse(data)
            
            _LOGGER.debug(f"[{self.centrale_id}] Parsed state:")
            _LOGGER.debug(f"[{self.centrale_id}]   Armed: {self._state_parser.is_armed()}")
            _LOGGER.debug(f"[{self.centrale_id}]   Programs: {self._state_parser.get_armed_programs()}")
            _LOGGER.debug(f"[{self.centrale_id}]   Battery: {self._state_parser.get_battery_voltage()}V")
            _LOGGER.debug(f"[{self.centrale_id}]   Current: {self._state_parser.get_current_consumption()}A")
            _LOGGER.debug(f"[{self.centrale_id}]   WiFi: {self._state_parser.get_wifi_status()}")
            _LOGGER.debug(f"[{self.centrale_id}]   Firmware: {self._state_parser.get_firmware_version()}")
            
            # Check problemi
            problemi = self._state_parser.get_system_problems()
            if problemi:
                _LOGGER.debug(f"[{self.centrale_id}] System problems: {', '.join(problemi)}")
            
            # Check zone aperte
            zone = self._state_parser.get_open_zones()
            zone_aperte = [k for k, v in zone.items() if v]
            if zone_aperte:
                _LOGGER.debug(f"[{self.centrale_id}] Open zones: {', '.join(zone_aperte)}")
            
            # Check allarmi
            allarmi = self._state_parser.get_active_alarms()
            if allarmi:
                _LOGGER.debug(f"[{self.centrale_id}] Active alarms: {', '.join(allarmi)}")
            
        except Exception as e:
            _LOGGER.error(f"[{self.centrale_id}] Error parsing Gold state: {e}", exc_info=True)
        
        _LOGGER.debug(f"[{self.centrale_id}] ==============================")
        
        self._store_message("onGoldState", data, timestamp)
        
        if self.message_callback:
            await self.message_callback(
                self.centrale_id, 
                {"type": "gold_state", "data": parsed if parsed is not None else data}
            )
    
    # ------------------------------ Utility methods ------------------------------
    
    def _store_message(self, event: str, data: Any, timestamp: str):
        """Store message for debugging."""
        message = {
            "timestamp": timestamp,
            "event": event,
            "data": data
        }
        
        self._last_messages.append(message)
        if len(self._last_messages) > self._max_messages:
            self._last_messages.pop(0)
    
    def get_last_messages(self, count: int = 10) -> list:
        """Get last N messages for debugging."""
        return self._last_messages[-count:]
    
    def get_discovered_events(self) -> dict:
        """Get all discovered events with counts."""
        return dict(self._gold_events)

"""Socket.IO client specifico per Lince Europlus."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Optional

from ..common.socket_client import BaseSocketClient
from ..utils import send_multiple_notifications
from ..const import API_SOCKET_IO_URL, DOMAIN
from .const import SOCKET_NAMESPACE

_LOGGER = logging.getLogger(__name__)

SEND_EVENT = "sendCommand"

BIT_G1 = 1  # 0b0001
BIT_G2 = 2  # 0b0010
BIT_G3 = 4  # 0b0100
BIT_GEXT = 8  # 0b1000


class EuroplusSocketClient(BaseSocketClient):
    """
    Client Socket.IO specifico per Europlus.
    Eredita la gestione connessione/disconnessione/errori dalla classe base.
    """

    def __init__(self, *args, **kwargs):
        """Initialize Europlus socket client."""
        super().__init__(*args, **kwargs)
        
        # Eventi per autorizzazione (PIN/teknox) - SPECIFICO EUROPLUS
        self._auth_events: dict[int, asyncio.Event] = {}

    def _build_connect_url(self) -> str:
        """URL specifico Europlus con querystring."""
        return f"{API_SOCKET_IO_URL}/?token={self.token}&system_id={self.centrale_id}"

    def _get_namespace(self) -> str:
        """Namespace specifico Europlus."""
        return SOCKET_NAMESPACE

    def _register_handlers(self):
        """Registra handler eventi specifici Europlus."""
        namespace = SOCKET_NAMESPACE
        
        # Event binding specifici Europlus
        self.sio.on("connect", self.on_connect, namespace=namespace)
        self.sio.on("disconnect", self.on_disconnect, namespace=namespace)
        self.sio.on("connect_error", self.on_connect_error, namespace=namespace)
        self.sio.on("message", self.on_message, namespace=namespace)
        self.sio.on("onStatus", self.on_status, namespace=namespace)

    # ------------------------------ Event handlers EUROPLUS ------------------------------

    async def on_connect(self):
        """Handler connessione Europlus."""
        self._connected = True
        self._connected_event.set()
        self._reconnect_backoff = 2.0
        centrale_name = "Sconosciuta"
        _LOGGER.debug("[%s] Socket.IO connesso", self.centrale_id)

        if self.hass:
            try:
                coordinator = self.hass.data[DOMAIN]["coordinator"]
                for system in coordinator.data:
                    if system["id"] == self.centrale_id:
                        centrale_name = f'{system.get("name", "Sconosciuta")}'
                        break
            except Exception:
                pass
        
        #await send_multiple_notifications(
        #    self.hass,
        #    message=f"🔗 WebSocket connessa per {centrale_name}",
        #    title=f"Lince Alarm - WebSocket",
        #    persistent=True,
        #    persistent_id=f"socket_connected_{self.centrale_id}",
        #    mobile=True,
        #    centrale_id=self.centrale_id
        #)

        if self.connect_callback:
            await self.connect_callback(self.centrale_id)

    async def on_disconnect(self):
        """Handler disconnessione Europlus."""
        self._connected = False
        self._connected_event.clear()
        centrale_name = "Sconosciuta"
        _LOGGER.warning("[%s] Socket.IO disconnesso", self.centrale_id)

        if self.hass:
            try:
                coordinator = self.hass.data[DOMAIN]["coordinator"]
                for system in coordinator.data:
                    if system["id"] == self.centrale_id:
                        centrale_name = f'{system.get("name", "Sconosciuta")}'
                        break
            except Exception:
                pass
        
        #await send_multiple_notifications(
        #    self.hass,
        #    message=f"🔗 WebSocket disconnessa per {centrale_name}",
        #    title=f"Lince Alarm - WebSocket",
        #    persistent=True,
        #    persistent_id=f"socket_connected_{self.centrale_id}",
        #    mobile=True,
        #    centrale_id=self.centrale_id
        #)

        if self.disconnect_callback:
            await self.disconnect_callback(self.centrale_id)

    async def on_connect_error(self, data: Any = None):
        """
        Handler errore connessione Europlus.
        Intercetta errori DOPO aver raggiunto il server (namespace):
        - se 'unauthorized/expired/invalid', re-login + reconnect con nuovo token
        - altrimenti, lascia lavorare l'auto-reconnect e pianifica retry con backoff
        """
        msg = ""
        if isinstance(data, dict):
            msg = str(data.get("message") or data.get("error") or "")
        else:
            msg = str(data or "")

        _LOGGER.warning(
            "[%s] Errore di connessione namespace: %s", self.centrale_id, data
        )

        # Check per errori di autenticazione (dalla classe base)
        from ..common.socket_client import _UNAUTH_STRINGS
        
        if any(s in msg.lower() for s in _UNAUTH_STRINGS):
            if self.hass:
                try:
                    centrale_name = f"Centrale {self.centrale_id}"
                    coordinator = self.hass.data[DOMAIN]["coordinator"]
                    for system in coordinator.data:
                        if system["id"] == self.centrale_id:
                            centrale_name = f'{system.get("name", "Sconosciuta")}'
                            break
                    
                    #await send_multiple_notifications(
                    #    self.hass,
                    #    message=f"🔐 Errore autenticazione WebSocket per {centrale_name}. Tentativo re-login...",
                    #    title=f"Lince Alarm - Errore Autenticazione",
                    #    persistent=True,
                    #    persistent_id=f"socket_auth_error_{self.centrale_id}",
                    #    mobile=False,
                    #    centrale_id=self.centrale_id
                    #)
                except Exception as e:
                    _LOGGER.debug("[%s] Errore invio notifica auth error: %s", self.centrale_id, e)

            await self._handle_unauthorized()
        else:
            await self._schedule_reconnect_backoff("generic_connect_error")

    async def on_message(self, data):
        """Handler messaggio generico Europlus."""
        _LOGGER.debug("[%s] Messaggio ricevuto: %s", self.centrale_id, data)
        if self.message_callback:
            await self.message_callback(self.centrale_id, data)

    async def on_status(self, data):
        """Handler specifico Europlus per messaggi onStatus."""
        _LOGGER.debug("[%s] Messaggio onStatus ricevuto: %s", self.centrale_id, data)
        if self.message_callback:
            await self.message_callback(self.centrale_id, data)

    # ------------------------------ Utility PIN / CAP EUROPLUS ------------------------------

    def _ensure_event(self, row_id: int) -> asyncio.Event:
        """Gestione eventi autorizzazione specifici Europlus."""
        ev = self._auth_events.get(row_id)
        if ev is None:
            ev = asyncio.Event()
            self._auth_events[row_id] = ev
        return ev

    def reset_authorized(self, row_id: int) -> None:
        """Reset autorizzazione Europlus."""
        ev = self._ensure_event(row_id)
        ev.clear()

    async def wait_for_authorized(self, row_id: int, timeout: float = 0.5) -> bool:
        """Attendi autorizzazione Teknox - specifico Europlus."""
        ev = self._ensure_event(row_id)
        try:
            await asyncio.wait_for(ev.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    # ------------------------------ Comandi specifici EUROPLUS ------------------------------

    async def async_send_pin(self, pin: list[int]) -> None:
        """
        Invia il login (type=251) con payload di esattamente 6 cifre 0..9.
        SPECIFICO PROTOCOLLO EUROPLUS.
        """
        if (
            not isinstance(pin, list)
            or len(pin) != 6
            or any(not isinstance(d, int) or d < 0 or d > 9 for d in pin)
        ):
            raise ValueError("PIN non valido: servono esattamente 6 cifre (int 0..9)")
        msg = json.dumps({"type": 251, "payload": pin}, separators=(",", ":"))
        try:
            await self.sio.emit(SEND_EVENT, msg, namespace=SOCKET_NAMESPACE)
            _LOGGER.debug("[%s] PIN inviato.", self.centrale_id)
        except Exception as e:
            _LOGGER.error("[%s] Errore in invio PIN: %s", self.centrale_id, e)

    async def async_send_program_activation(
        self, g1: bool, g2: bool, g3: bool, gext: bool
    ):
        """
        Invia il cambio stato (type=240) con payload = [mask].
        SPECIFICO PROTOCOLLO EUROPLUS.
        - True/False per ciascun programma (G1, G2, G3, GEXT).
        - Se tutti False -> mask = 0 (disarmo).
        """
        mask = (
            (BIT_G1 if g1 else 0)
            | (BIT_G2 if g2 else 0)
            | (BIT_G3 if g3 else 0)
            | (BIT_GEXT if gext else 0)
        )
        msg = json.dumps({"type": 240, "payload": [mask]}, separators=(",", ":"))
        try:
            await self.sio.emit(SEND_EVENT, msg, namespace=SOCKET_NAMESPACE)
            _LOGGER.debug(
                "[%s] Stato centrale inviato. G1 %s, G2 %s, G3 %s, GEXT %s.",
                self.centrale_id,
                g1, g2, g3, gext,
            )
        except Exception as e:
            _LOGGER.error(
                "[%s] Errore invio attivazione programmi: %s", self.centrale_id, e
            )
            
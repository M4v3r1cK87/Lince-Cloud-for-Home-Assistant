from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any, Callable, Optional
from .utils import send_multiple_notifications

import socketio

from .const import API_SOCKET_IO_URL, SOCKET_NAMESPACE, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Backoff per riconnessioni durante la vita della sessione (usato dal nostro scheduler)
RETRY_INTERVAL = 300  # 5 minuti per errori generici non gestiti nel connect loop
SEND_EVENT = "sendCommand"

# Backoff per il PRIMO aggancio (prima dell'handshake SIO):
# su errori tipo "Network unreachable", DNS, ecc.
INITIAL_BACKOFF_START = 2.0   # secondi
INITIAL_BACKOFF_MAX = 60.0    # secondi

BIT_G1 = 1  # 0b0001
BIT_G2 = 2  # 0b0010
BIT_G3 = 4  # 0b0100
BIT_GEXT = 8  # 0b1000

# Frasi indicative di token non valido/scaduto/permessi mancanti
_UNAUTH_STRINGS = (
    "non autorizzata",
    "unauthorized",
    "not authorized",
    "forbidden",
    "jwt expired",
    "token expired",
    "invalid token",
)


class LinceSocketClient:
    """
    Client Socket.IO con:
    - auto-reconnect del client python-socketio
    - gestione 'connect_error' per token scaduto/non valido (re-login + reconnect)
    - backoff esponenziale e jitter per fallimenti iniziali (rete assente/DNS)
    - lock per evitare rientri
    """

    def __init__(
        self,
        token: str,
        centrale_id: int,
        message_callback: Optional[Callable[[int, Any], asyncio.Future]] = None,
        disconnect_callback: Optional[Callable[[int], asyncio.Future]] = None,
        connect_callback: Optional[Callable[[int], asyncio.Future]] = None,
        *,
        hass=None,
        config_entry=None,
        api=None,  # istanza di GoldCloudAPI (espone .token, .login(email,pwd), opz. get_credentials/_email/_password)
        auth_failed_callback: Optional[Callable[[int, str], asyncio.Future]] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.token = token
        self.centrale_id = centrale_id
        self.message_callback = message_callback
        self.disconnect_callback = disconnect_callback
        self.connect_callback = connect_callback

        self.hass = hass
        self._entry = config_entry
        self._api = api
        self._auth_failed_cb = auth_failed_callback
        self._email = email
        self._password = password

        self._connected = False
        self._task: Optional[asyncio.Task] = None
        self._connected_event = asyncio.Event()
        self._stop = False

        # Eventi per autorizzazione (PIN/teknox)
        self._auth_events: dict[int, asyncio.Event] = {}

        # Lock e backoff per re-login/reconnect forzati (dopo il primo aggancio)
        self._relogin_lock = asyncio.Lock()
        self._reconnect_lock = asyncio.Lock()
        self._reconnect_backoff = 2.0
        self._reconnect_backoff_max = 300.0
        self._login_failures = 0

        # Client Socket.IO
        self.sio = socketio.AsyncClient(
            logger=False,
            engineio_logger=False,
            reconnection=True,
            reconnection_attempts=0,  # 0 = infiniti
            reconnection_delay=1,
            reconnection_delay_max=30,
            randomization_factor=0.5,
        )

        # Event binding
        self.sio.on("connect", self.on_connect, namespace=SOCKET_NAMESPACE)
        self.sio.on("disconnect", self.on_disconnect, namespace=SOCKET_NAMESPACE)
        self.sio.on("connect_error", self.on_connect_error, namespace=SOCKET_NAMESPACE)
        self.sio.on("message", self.on_message, namespace=SOCKET_NAMESPACE)
        self.sio.on("*", self.on_any_event, namespace=SOCKET_NAMESPACE)
        self.sio.on("onStatus", self.on_status, namespace=SOCKET_NAMESPACE)

    # ------------------------------ Helpers connessione ------------------------------

    async def stop(self):
        """Ferma DEFINITIVAMENTE il client e TUTTI i task di connessione/retry."""
        _LOGGER.info("[%s] Richiesta STOP definitivo del socket client", self.centrale_id)
        
        # Flag di stop PRIMA di tutto
        self._stop = True
        
        # NON inviare notifica se siamo in fase di shutdown di HA
        # Controlla se HA è in fase di stop
        is_ha_stopping = False
        if self.hass:
            # Verifica se c'è un evento di stop in corso
            is_ha_stopping = self.hass.is_stopping if hasattr(self.hass, 'is_stopping') else False
        
        # Invia notifica solo se NON siamo in fase di shutdown
        if self.hass and self._connected and not is_ha_stopping:
            try:
                from .utils import send_multiple_notifications
                centrale_name = f"Centrale {self.centrale_id}"
                if self._api:
                    try:
                        systems = getattr(self._api, '_systems_cache', None) or []
                        for sys in systems:
                            if sys.get('id') == self.centrale_id:
                                centrale_name = sys.get('nome', centrale_name)
                                break
                    except:
                        pass
                
                await send_multiple_notifications(
                    self.hass,
                    message=f"🔌 WebSocket fermata manualmente per {centrale_name}. ⚠️ Lo stato della centrale NON è cambiato.",
                    title=f"LinceCloud - WebSocket",
                    persistent=True,
                    persistent_id=f"socket_stopped_{self.centrale_id}",
                    mobile=False,
                    centrale_id=self.centrale_id
                )
            except Exception as e:
                _LOGGER.debug("[%s] Errore invio notifica stop: %s", self.centrale_id, e)
        
        self._connected = False
        self._connected_event.clear()
        
        # Cancella TUTTI i task attivi
        tasks_to_cancel = []
        if self._connect_task and not self._connect_task.done():
            tasks_to_cancel.append(self._connect_task)
        if self._retry_task and not self._retry_task.done():
            tasks_to_cancel.append(self._retry_task)
        if self._reconnect_task and not self._reconnect_task.done():
            tasks_to_cancel.append(self._reconnect_task)
        
        for task in tasks_to_cancel:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                _LOGGER.debug("[%s] Task cancellato con errore: %s", self.centrale_id, e)
        
        # Disconnetti fisicamente la socket
        if self.sio:
            try:
                if self.sio.connected:
                    await self.sio.disconnect()
                    _LOGGER.debug("[%s] Socket disconnessa", self.centrale_id)
                
                # Attendi un attimo per la disconnessione
                await asyncio.sleep(0.1)
                
                # Pulisci gli handler per evitare riferimenti pendenti
                self.sio._event_handlers.clear()
                self.sio._namespace_handlers.clear()
                
            except Exception as e:
                _LOGGER.debug("[%s] Errore durante disconnessione socket: %s", self.centrale_id, e)
            finally:
                # Rilascia il riferimento all'oggetto socket
                self.sio = None
        
        # Reset tutti i task
        self._connect_task = None
        self._retry_task = None
        self._reconnect_task = None
        
        _LOGGER.info("[%s] Socket client completamente fermato", self.centrale_id)

    def is_connected(self) -> bool:
        return self._connected

    def _build_connect_url(self) -> str:
        # querystring con token + system_id
        return f"{API_SOCKET_IO_URL}/?token={self.token}&system_id={self.centrale_id}"

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def refresh_connection(self, new_token: Optional[str] = None) -> None:
        """API pubblica: aggiorna token e forza un reconnect."""
        if new_token:
            self.token = new_token
        await self._force_reconnect_with_new_token()

    async def _force_reconnect_with_new_token(self) -> None:
        """Disconnette e riconnette con i nuovi parametri (token/headers/URL)."""
        # Controlla il flag _stop all'inizio
        if self._stop:
            _LOGGER.debug("[%s] Riconnessione forzata annullata (stop richiesto)", self.centrale_id)
            return
        
        async with self._reconnect_lock:
            try:
                if self.sio.connected:
                    await self.sio.disconnect()
            except Exception:
                pass

            self._connected = False
            self._connected_event.clear()

            url = self._build_connect_url()
            headers = self._build_headers()
            _LOGGER.debug(
                "[%s] Riconnessione forzata con nuovo token (headers aggiornati)",
                self.centrale_id,
            )
            try:
                await self.sio.connect(
                    url,
                    headers=headers,
                    namespaces=[SOCKET_NAMESPACE],
                    wait_timeout=10,
                )
                # attende la conferma via callback on_connect
                await asyncio.wait_for(self._connected_event.wait(), timeout=3.0)
                self._reconnect_backoff = 2.0
            except Exception as err:
                _LOGGER.warning(
                    "[%s] Fallita riconnessione forzata: %s", self.centrale_id, err
                )
                await self._schedule_reconnect_backoff("force_reconnect_failed")

    async def _schedule_reconnect_backoff(self, reason: str) -> None:
        """Pianifica un tentativo di riconnessione con backoff esponenziale + jitter."""
        delay = min(self._reconnect_backoff, self._reconnect_backoff_max)
        delay += random.uniform(0, 1.0)
        _LOGGER.debug(
            "[%s] Riconnessione pianificata fra %.1fs (motivo: %s)",
            self.centrale_id,
            delay,
            reason,
        )

        async def _reconnect_later():
            await asyncio.sleep(delay)
            await self._force_reconnect_with_new_token()

        if self.hass:
            self.hass.async_create_task(_reconnect_later())
        else:
            asyncio.create_task(_reconnect_later())

        self._reconnect_backoff = min(
            self._reconnect_backoff * 2, self._reconnect_backoff_max
        )

    # ------------------------------ Ciclo di start/stop ------------------------------

    async def start(self):
        """Avvia la connessione in background. Ritorna True se già connesso entro pochi secondi."""
        if self._connected or (self._task and not self._task.done()):
            _LOGGER.debug(
                "[%s] Socket già connessa o in fase di connessione.",
                self.centrale_id,
            )
            return self._connected

        self._stop = False

        async def run():
            # Backoff veloce per fallimenti di connessione iniziale (rete, DNS, ecc.)
            backoff = INITIAL_BACKOFF_START
            while not self._stop:
                try:
                    url = self._build_connect_url()
                    await self.sio.connect(
                        url,
                        headers=self._build_headers(),
                        namespaces=[SOCKET_NAMESPACE],
                        wait_timeout=10,
                    )
                    # attesa conferma via callback on_connect
                    await asyncio.wait_for(self._connected_event.wait(), timeout=2.0)
                    # una volta connessi, usciamo: da qui in poi gestisce l'auto-reconnect interno + i nostri handler
                    return
                except asyncio.TimeoutError as e:
                    # timeout nel "wait()" del nostro evento di connessione
                    delay = min(backoff, INITIAL_BACKOFF_MAX) + random.uniform(0, 0.5)
                    _LOGGER.warning(
                        "[%s] Timeout in attesa della conferma di connessione: %s. Retry fra %.1fs",
                        self.centrale_id, e, delay
                    )
                except Exception as e:
                    # include OSError: [Errno 101] Network unreachable, DNS, ecc.
                    delay = min(backoff, INITIAL_BACKOFF_MAX) + random.uniform(0, 0.5)
                    _LOGGER.warning(
                        "[%s] Connessione fallita (%s). Retry fra %.1fs",
                        self.centrale_id, e, delay
                    )
                # attende e poi ritenta con backoff crescente
                await asyncio.sleep(delay)
                backoff = min(backoff * 2, INITIAL_BACKOFF_MAX)

            _LOGGER.debug("[%s] Loop di connessione terminato (stop richiesto).", self.centrale_id)

        self._task = asyncio.create_task(run())
        # attesa "soft" dell'evento connesso: non blocca l'avvio dell'integrazione
        try:
            await asyncio.wait_for(self._connected_event.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            pass
        return self._connected

    async def stop(self):
        """Ferma DEFINITIVAMENTE il client e TUTTI i task di connessione/retry."""
        _LOGGER.info("[%s] Richiesta STOP definitivo del socket client", self.centrale_id)
        
        # Flag di stop PRIMA di tutto
        self._stop = True
        self._connected = False
        self._connected_event.clear()
        
        # Cancella TUTTI i task pendenti di reconnect
        # (possono essere stati schedulati da _schedule_reconnect_backoff)
        tasks_to_cancel = []
        
        # Cancella il task principale se esiste
        if self._task and not self._task.done():
            tasks_to_cancel.append(self._task)
            self._task = None
        
        # Trova e cancella tutti i task di reconnect schedulati
        if self.hass:
            # In Home Assistant, i task sono gestiti dal loop principale
            # Dobbiamo marcare lo stop in modo che non proseguano
            pass  # Il flag _stop è già True, quindi i task si fermeranno
        
        # Disconnetti il socket.io client
        try:
            if self.sio.connected:
                # Disabilita temporaneamente il reconnect automatico
                self.sio.reconnection = False
                await self.sio.disconnect()
        except Exception as e:
            _LOGGER.debug("[%s] Errore durante disconnect: %s", self.centrale_id, e)
        finally:
            # Assicurati che il client non tenti più di riconnettersi
            self.sio.reconnection = False
        
        # Cancella i task
        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        _LOGGER.info("[%s] Socket client COMPLETAMENTE arrestato", self.centrale_id)

    async def _schedule_reconnect_backoff(self, reason: str) -> None:
        """Pianifica un tentativo di riconnessione con backoff esponenziale + jitter."""
        # IMPORTANTE: Controlla il flag _stop prima di schedulare
        if self._stop:
            _LOGGER.debug(
                "[%s] Riconnessione NON pianificata (stop richiesto). Motivo originale: %s",
                self.centrale_id,
                reason,
            )
            return
            
        delay = min(self._reconnect_backoff, self._reconnect_backoff_max)
        delay += random.uniform(0, 1.0)
        _LOGGER.debug(
            "[%s] Riconnessione pianificata fra %.1fs (motivo: %s)",
            self.centrale_id,
            delay,
            reason,
        )

        async def _reconnect_later():
            await asyncio.sleep(delay)
            # Controlla di nuovo il flag prima di riconnettersi
            if not self._stop:
                await self._force_reconnect_with_new_token()
            else:
                _LOGGER.debug("[%s] Riconnessione annullata (stop richiesto)", self.centrale_id)

        if self.hass:
            self.hass.async_create_task(_reconnect_later())
        else:
            asyncio.create_task(_reconnect_later())

        self._reconnect_backoff = min(
            self._reconnect_backoff * 2, self._reconnect_backoff_max
        )

    # ------------------------------ Event handlers ------------------------------

    async def on_connect(self):
        self._connected = True
        self._connected_event.set()
        self._reconnect_backoff = 2.0
        centrale_name = "Sconosciuta"
        _LOGGER.debug("[%s] Socket.IO connesso", self.centrale_id)

        coordinator = self.hass.data[DOMAIN]["coordinator"]
        for system in coordinator.data:
            if (system["id"] == self.centrale_id):
                centrale_name = f'{system.get("name", "Sconosciuta")}'
                break;
        
        await send_multiple_notifications(
            self.hass,
            message=f"🔗 WebSocket connessa per {centrale_name}",
            title=f"LinceCloud - WebSocket",
            persistent=True,
            persistent_id=f"socket_connected_{self.centrale_id}",
            mobile=True,  # Solo persistente
            centrale_id=self.centrale_id
        )

        if self.connect_callback:
            await self.connect_callback(self.centrale_id)

    async def on_disconnect(self):
        self._connected = False
        self._connected_event.clear()
        centrale_name = "Sconosciuta"
        _LOGGER.warning("[%s] Socket.IO disconnesso", self.centrale_id)

        coordinator = self.hass.data[DOMAIN]["coordinator"]
        for system in coordinator.data:
            if (system["id"] == self.centrale_id):
                centrale_name = f'{system.get("name", "Sconosciuta")}'
                break;
        
        await send_multiple_notifications(
            self.hass,
            message=f"🔗 WebSocket disconnessa per {centrale_name}",
            title=f"LinceCloud - WebSocket",
            persistent=True,
            persistent_id=f"socket_connected_{self.centrale_id}",
            mobile=True,  # Solo persistente
            centrale_id=self.centrale_id
        )

        if self.disconnect_callback:
            await self.disconnect_callback(self.centrale_id)

    async def on_connect_error(self, data: Any = None):
        """
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

        if any(s in msg.lower() for s in _UNAUTH_STRINGS):
            if self.hass:
                try:
                    centrale_name = f"Centrale {self.centrale_id}"
                    coordinator = self.hass.data[DOMAIN]["coordinator"]
                    for system in coordinator.data:
                        if (system["id"] == self.centrale_id):
                            centrale_name = f'{system.get("name", "Sconosciuta")}'
                            break
                    
                    await send_multiple_notifications(
                        self.hass,
                        message=f"🔐 Errore autenticazione WebSocket per {centrale_name}. Tentativo re-login...",
                        title=f"LinceCloud - Errore Autenticazione",
                        persistent=True,
                        persistent_id=f"socket_auth_error_{self.centrale_id}",
                        mobile=False,
                        centrale_id=self.centrale_id
                    )
                except Exception as e:
                    _LOGGER.debug("[%s] Errore invio notifica auth error: %s", self.centrale_id, e)

            await self._handle_unauthorized()
        else:
            await self._schedule_reconnect_backoff("generic_connect_error")

    async def on_message(self, data):
        _LOGGER.debug("[%s] Messaggio ricevuto: %s", self.centrale_id, data)
        if self.message_callback:
            await self.message_callback(self.centrale_id, data)

    async def on_any_event(self, event, data):
        _LOGGER.debug(
            "[%s] Evento generico ricevuto: %s -> %s", self.centrale_id, event, data
        )

    async def on_status(self, data):
        _LOGGER.debug("[%s] Messaggio onStatus ricevuto: %s", self.centrale_id, data)
        if self.message_callback:
            await self.message_callback(self.centrale_id, data)

    # ------------------------------ Re-login ------------------------------

    def _get_credentials(self) -> tuple[Optional[str], Optional[str]]:
        """
        Recupera credenziali con priorità:
        1) parametri espliciti passati al costruttore,
        2) config_entry,
        3) attributi della GoldCloudAPI (._email / ._password) o .get_credentials().
        """
        email = self._email or (self._entry.data.get("email") if self._entry else None)
        password = self._password or (
            self._entry.data.get("password") if self._entry else None
        )
        if (not email or not password) and self._api is not None:
            try:
                creds = getattr(self._api, "get_credentials", None)
                if callable(creds):
                    api_email, api_pwd = creds()
                    email = email or api_email
                    password = password or api_pwd
                else:
                    email = email or getattr(self._api, "_email", None)
                    password = password or getattr(self._api, "_password", None)
            except Exception:
                pass
        return email, password

    async def _handle_unauthorized(self) -> None:
        """Tenta il re-login con credenziali disponibili; aggiorna token e riconnette."""
        async with self._relogin_lock:
            email, password = self._get_credentials()
            if not (self._api and email and password):
                _LOGGER.error(
                    "[%s] Re-login non possibile: API/credenziali non disponibili.",
                    self.centrale_id,
                )
                await self._schedule_reconnect_backoff("unauthorized_no_creds")
                return

            _LOGGER.debug("[%s] Tentativo di re-login automatico…", self.centrale_id)
            try:
                await self._api.login(email, password)
                new_token = getattr(self._api, "token", None)
                if not new_token:
                    raise RuntimeError("Login OK ma token non valorizzato")
                self.token = new_token
                self._login_failures = 0
                _LOGGER.debug(
                    "[%s] Re-login OK. Aggiorno token ed eseguo riconnessione.",
                    self.centrale_id,
                )
                await self._force_reconnect_with_new_token()
            except Exception as err:
                self._login_failures += 1
                _LOGGER.warning(
                    "[%s] Re-login fallito (%s). Tentativi: %s",
                    self.centrale_id,
                    err,
                    self._login_failures,
                )
                if self._auth_failed_cb and self._login_failures >= 2:
                    try:
                        await self._auth_failed_cb(self.centrale_id, str(err))
                    except Exception:
                        pass
                await self._schedule_reconnect_backoff("unauthorized_relogin_failed")

    # ------------------------------ Utility PIN / CAP ------------------------------

    def _ensure_event(self, row_id: int) -> asyncio.Event:
        ev = self._auth_events.get(row_id)
        if ev is None:
            ev = asyncio.Event()
            self._auth_events[row_id] = ev
        return ev

    def reset_authorized(self, row_id: int) -> None:
        ev = self._ensure_event(row_id)
        ev.clear()

    async def wait_for_authorized(self, row_id: int, timeout: float = 0.5) -> bool:
        ev = self._ensure_event(row_id)
        try:
            await asyncio.wait_for(ev.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def async_send_pin(self, pin: list[int]) -> None:
        """Invia il login (type=251) con payload di esattamente 6 cifre 0..9."""
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

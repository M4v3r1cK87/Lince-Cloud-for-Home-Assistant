"""Base Socket.IO client comune a tutti i brand - gestione connessione/disconnessione/errori."""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Callable, Optional

import socketio

_LOGGER = logging.getLogger(__name__)

# Backoff per riconnessioni durante la vita della sessione
RETRY_INTERVAL = 300  # 5 minuti per errori generici non gestiti nel connect loop

# Backoff per il PRIMO aggancio (prima dell'handshake SIO)
INITIAL_BACKOFF_START = 2.0   # secondi
INITIAL_BACKOFF_MAX = 60.0    # secondi

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


class BaseSocketClient:
    """
    Client Socket.IO base con:
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
        api=None,
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

    # ------------------------------ Helpers connessione ------------------------------

    async def stop(self):
        """Ferma DEFINITIVAMENTE il client e TUTTI i task di connessione/retry."""
        _LOGGER.info("[%s] Richiesta STOP definitivo del socket client", self.centrale_id)
        
        # Flag di stop PRIMA di tutto
        self._stop = True
        self._connected = False
        self._connected_event.clear()
        
        # Cancella TUTTI i task pendenti di reconnect
        tasks_to_cancel = []
        
        # Cancella il task principale se esiste
        if self._task and not self._task.done():
            tasks_to_cancel.append(self._task)
            self._task = None
        
        # Disconnetti il socket.io client
        try:
            if self.sio and self.sio.connected:
                # Disabilita temporaneamente il reconnect automatico
                self.sio.reconnection = False
                await self.sio.disconnect()
        except Exception as e:
            _LOGGER.debug("[%s] Errore durante disconnect: %s", self.centrale_id, e)
        finally:
            # Assicurati che il client non tenti più di riconnettersi
            if self.sio:
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

    def is_connected(self) -> bool:
        return self._connected

    def _build_connect_url(self) -> str:
        """Da override nelle sottoclassi per URL specifici."""
        raise NotImplementedError("Sottoclasse deve implementare _build_connect_url")

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get_namespace(self) -> str:
        """Da override nelle sottoclassi per namespace specifici."""
        raise NotImplementedError("Sottoclasse deve implementare _get_namespace")

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
                if self.sio and self.sio.connected:
                    await self.sio.disconnect()
            except Exception:
                pass

            self._connected = False
            self._connected_event.clear()

            url = self._build_connect_url()
            headers = self._build_headers()
            namespace = self._get_namespace()
            
            _LOGGER.debug(
                "[%s] Riconnessione forzata con nuovo token (headers aggiornati)",
                self.centrale_id,
            )
            try:
                await self.sio.connect(
                    url,
                    headers=headers,
                    namespaces=[namespace],
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

        # Registra gli handler prima di connettersi
        self._register_handlers()

        async def run():
            # Backoff veloce per fallimenti di connessione iniziale (rete, DNS, ecc.)
            backoff = INITIAL_BACKOFF_START
            while not self._stop:
                try:
                    url = self._build_connect_url()
                    namespace = self._get_namespace()
                    await self.sio.connect(
                        url,
                        headers=self._build_headers(),
                        namespaces=[namespace],
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

    def _register_handlers(self):
        """Da override nelle sottoclassi per registrare handler specifici."""
        raise NotImplementedError("Sottoclasse deve implementare _register_handlers")

    # ------------------------------ Re-login ------------------------------

    def _get_credentials(self) -> tuple[Optional[str], Optional[str]]:
        """
        Recupera credenziali con priorità:
        1) parametri espliciti passati al costruttore,
        2) config_entry,
        3) attributi della API (._email / ._password) o .get_credentials().
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
                
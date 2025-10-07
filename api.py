from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .socket_client import LinceSocketClient
from .europlusParser import europlusParser
from .const import (
    API_SESSION_URL,
    API_SYSTEMS_URL,
    API_SYSTEM_ACCESS_URL,
    DOMAIN,
)
from .utils import convert_zone_attributes
from .binary_sensor import update_buscomm_binarysensors
from .sensor import update_buscomm_sensors

_LOGGER = logging.getLogger(__name__)

RETRY_INTERVAL = 300  # 5 minuti
TOKEN_EXPIRY_MINUTES = 60           # TTL default se il backend non fornisce exp
TOKEN_SAFETY_SKEW_SECONDS = 30      # margine anti-race prima della scadenza
AUTH_FAIL_NOTIFY_COOLDOWN = 15 * 60  # 15 minuti


class GoldCloudAPI:
    def __init__(self, hass, email: str | None = None, password: str | None = None):
        self.hass = hass
        self.session = async_get_clientsession(hass)

        # Auth
        self.token: str | None = None
        self.token_expiry: datetime | None = None
        self._email = email
        self._password = password

        # Socket state
        self._socket_clients: dict[int, LinceSocketClient] = {}
        self.latest_socket_message: dict[int, dict] = {}
        self._lock = asyncio.Lock()

        # Entity registries (popolate dall’integrazione)
        self.socket_message_sensor: dict[int, object] = {}
        self.socket_connection_sensor: dict[int, object] = {}
        self.zone_sensors: dict[int, dict] = {}         # {row_id: {'filare': {1:sensor,...}, 'radio': {...}}}
        self.buscomm_sensors: dict[int, dict] = {}      # {row_id: {...}}

        # Parser condiviso
        self._europlusParser = europlusParser(None)

        # Debounce notifiche re-auth
        self._auth_failed_last_notify: dict[int, datetime] = {}

    # -------------------------------------------------------------------------
    # Auth helpers
    # -------------------------------------------------------------------------

    def get_credentials(self) -> tuple[str | None, str | None]:
        """Espone email/password al client socket per re-login."""
        return (self._email, self._password)

    async def login(self, email: str | None = None, password: str | None = None):
        """Esegue la login al servizio REST e aggiorna token + scadenza stimata."""
        payload = {"email": email, "password": password}
        try:
            async with self.session.post(API_SESSION_URL, json=payload) as resp:
                if resp.status not in (200, 201):
                    _LOGGER.error("Login fallita. Status code: %s", resp.status)
                    raise Exception(f"Login fallita errore {resp.status}")

                data = await resp.json()
                self.token = data.get("token")

                # Prova a dedurre la scadenza dal payload, altrimenti fallback 60'
                expires_at: datetime | None = None
                try:
                    if isinstance(data, dict):
                        if "expiresAt" in data:  # ISO8601
                            expires_at = datetime.fromisoformat(data["expiresAt"])
                        elif "exp" in data:      # epoch seconds (JWT)
                            expires_at = datetime.fromtimestamp(int(data["exp"]), tz=timezone.utc)
                        elif "expiresIn" in data:
                            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(data["expiresIn"]))
                except Exception:
                    expires_at = None

                if not expires_at:
                    expires_at = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRY_MINUTES)

                # Applica uno skew anti-race
                self.token_expiry = expires_at - timedelta(seconds=TOKEN_SAFETY_SKEW_SECONDS)

                _LOGGER.debug("Login effettuata con successo. Token acquisito.")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            _LOGGER.error("Errore di rete durante la login: %s", e)
            self.token = None
            self.token_expiry = None
            raise
        except Exception as e:
            _LOGGER.exception("Errore durante la login: %s", e)
            self.token = None
            self.token_expiry = None
            raise

    def get_auth_header(self) -> dict[str, str]:
        """Header Authorization Bearer, se disponibile."""
        if not self.token:
            raise Exception("Token non disponibile. Effettua il login prima.")
        return {"Authorization": f"Bearer {self.token}"}

    def is_token_expired(self) -> bool:
        """True se il token è scaduto o mancante (con piccolo skew)."""
        if self.token is None or self.token_expiry is None:
            return True
        return datetime.now(timezone.utc) >= self.token_expiry

    async def refresh_token_for_all_clients(self):
        """Propaga il nuovo token a tutti i client socket e forza il reconnect."""
        for cid, client in list(self._socket_clients.items()):
            try:
                await client.refresh_connection(self.token)
            except Exception:
                _LOGGER.debug("[%s] refresh_connection fallita (ignoro).", cid)

    async def close_all_sockets(self):
        """Chiude tutte le socket attive in modo pulito."""
        _LOGGER.info("Chiusura di tutte le socket attive...")
        
        # Copia la lista per evitare modifiche durante l'iterazione
        _socket_clients = list(self._socket_clients.items())
        
        for row_id, client in _socket_clients:
            try:
                _LOGGER.info(f"Chiusura socket per centrale {row_id}...")
                if client:
                    # Imposta il flag di stop PRIMA di disconnettere
                    client._stop = True
                    # Disconnetti la socket
                    if hasattr(client, 'sio') and client.sio:
                        await client.sio.disconnect()
                    # Chiama il metodo stop del client
                    await client.stop()
                    _LOGGER.info(f"Socket {row_id} chiusa correttamente")
            except Exception as e:
                _LOGGER.error(f"Errore chiusura socket {row_id}: {e}")
            finally:
                # Rimuovi il client dalla lista
                if row_id in self._socket_clients:
                    del self._socket_clients[row_id]
        
        # Pulisci completamente il dizionario
        self._socket_clients.clear()
        _LOGGER.info("Tutte le socket sono state chiuse")

    # -------------------------------------------------------------------------
    # REST endpoints
    # -------------------------------------------------------------------------

    async def fetch_systems(self):
        """Recupera la lista sistemi (singolo tentativo)."""
        headers = self.get_auth_header()
        try:
            async with self.session.get(API_SYSTEMS_URL, headers=headers) as resp:
                if resp.status != 200:
                    raise Exception(f"Errore nel recupero sistemi: Error code {resp.status}")
                data = await resp.json()
                if not data:
                    _LOGGER.warning("fetch_systems ha restituito un array vuoto!")
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            _LOGGER.error("Errore di rete durante fetch_systems: %s", e)
            raise
        except Exception as e:
            _LOGGER.exception("Errore durante fetch_systems: %s", e)
            raise

    async def fetch_system_access(self, row_id: int):
        """Recupera i dettagli di accesso a un sistema (singolo tentativo)."""
        headers = self.get_auth_header()
        url = f"{API_SYSTEM_ACCESS_URL}/{row_id}"
        try:
            async with self.session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    raise Exception(f"Errore nel recupero system-access per {row_id}: HTTP {resp.status}")
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            _LOGGER.error("Errore di rete durante fetch_system_access(%s): %s", row_id, e)
            raise
        except Exception as e:
            _LOGGER.exception("Errore durante fetch_system_access(%s): %s", row_id, e)
            raise

    # -------------------------------------------------------------------------
    # Socket lifecycle
    # -------------------------------------------------------------------------

    def get_socket_client(self, row_id: int) -> LinceSocketClient | None:
        """Restituisce il client socket associato alla centrale, se presente."""
        return self._socket_clients.get(row_id)

    async def start_socket_connection(self, row_id: int):
        """Tenta l’avvio della socket per una centrale. Ritorna True/False velocemente."""
        _LOGGER.debug(f"Avvio connessione socket per centrale {row_id}")
        async with self._lock:
            try:
                coord = self.hass.data[DOMAIN].get("coordinator")
            except Exception:
                coord = None

            async def connect_callback(cb_row_id: int):
                _LOGGER.info(f"[{cb_row_id}] Riconnesso alla socket")
                sensor = self.socket_connection_sensor.get(cb_row_id)
                if sensor:
                    sensor.update_status(True)

            async def disconnect_callback(cb_row_id: int):
                _LOGGER.warning(f"[{cb_row_id}] Disconnessione dalla socket rilevata")
                sensor = self.socket_connection_sensor.get(cb_row_id)
                if sensor:
                    sensor.update_status(False)

            async def message_callback(cb_row_id: int, message):
                _LOGGER.debug(f"[{cb_row_id}] Messaggio socket ricevuto: {message}")
                self.latest_socket_message[cb_row_id] = message

                # Aggiorna l’eventuale “sensore messaggi”
                sensor = self.socket_message_sensor.get(cb_row_id)
                if sensor:
                    sensor.update_message(message)

                # Parsing messaggio
                _LOGGER.debug(f"[{cb_row_id}] Inizio parsing zone/sensori")
                zone_dict_filare = self.zone_sensors.get(cb_row_id, {}).get("filare", {})
                zone_dict_radio = self.zone_sensors.get(cb_row_id, {}).get("radio", {})

                self._europlusParser.parse(message)

                # Aggiorna evento autorizzazione Teknox (per pannello/alarm)
                try:
                    c = self._europlusParser.get_isTeknoxAuthorized() or {}
                    client = self._socket_clients[cb_row_id]
                    ev = client._ensure_event(cb_row_id)
                    if bool(c.get("authorized", False)):
                        ev.set()
                    else:
                        ev.clear()
                except Exception:
                    pass

                # Zone filari
                ingressi_filari = self._europlusParser.get_ingressi_filari(len(zone_dict_filare))
                if ingressi_filari:
                    for idx, state in enumerate(ingressi_filari):
                        s = zone_dict_filare.get(idx + 1)  # +1 perché le zone partono da 1
                        if s:
                            attributes = convert_zone_attributes("filare", ingressi_filari[idx])
                            s.update_attributes("filare", attributes)

                # Zone radio
                ingressi_radio = self._europlusParser.get_ingressi_radio(len(zone_dict_radio))
                if ingressi_radio:
                    for idx, state in enumerate(ingressi_radio):
                        s = zone_dict_radio.get(idx + 1)
                        if s:
                            attributes = convert_zone_attributes("radio", ingressi_radio[idx])
                            s.update_attributes("radio", attributes)

                # Stato centrale -> usa il contenitore persistente self.buscomm_sensors
                if cb_row_id not in self.buscomm_sensors:
                    self.buscomm_sensors[cb_row_id] = {}

                self.buscomm_sensors[cb_row_id]["firmwareVersion"] = self._europlusParser.get_firmware_version()
                self.buscomm_sensors[cb_row_id]["temperature"] = self._europlusParser.get_temperature()
                self.buscomm_sensors[cb_row_id]["vBatt"] = self._europlusParser.get_vbatt()
                self.buscomm_sensors[cb_row_id]["vBus"] = self._europlusParser.get_vbus()
                self.buscomm_sensors[cb_row_id]["generali_1"] = self._europlusParser.get_generali_1()
                self.buscomm_sensors[cb_row_id]["generali_2"] = self._europlusParser.get_generali_2()
                self.buscomm_sensors[cb_row_id]["generali_3"] = self._europlusParser.get_generali_3()
                self.buscomm_sensors[cb_row_id]["generali_4"] = self._europlusParser.get_generali_4()
                self.buscomm_sensors[cb_row_id]["generali_5"] = self._europlusParser.get_generali_5()
                self.buscomm_sensors[cb_row_id]["pag0_impedimenti_1"] = self._europlusParser.get_pag0_impedimenti_1()
                self.buscomm_sensors[cb_row_id]["pag0_impedimenti_2"] = self._europlusParser.get_pag0_impedimenti_2()
                self.buscomm_sensors[cb_row_id]["espansioni"] = self._europlusParser.get_espansioni()
                self.buscomm_sensors[cb_row_id]["attivazioni"] = self._europlusParser.get_attivazioni()
                self.buscomm_sensors[cb_row_id]["isTeknoxAuthorized"] = self._europlusParser.get_isTeknoxAuthorized()
                self.buscomm_sensors[cb_row_id]["comandicentrale"] = self._europlusParser.get_comandi_centrale()

                _LOGGER.debug(f"[{cb_row_id}] Stato centrale aggiornato: {self.buscomm_sensors[cb_row_id]}")
                update_buscomm_binarysensors(self, cb_row_id, self.buscomm_sensors[cb_row_id])
                update_buscomm_sensors(self, cb_row_id, self.buscomm_sensors[cb_row_id])

                # Push immediato al DataUpdateCoordinator (per alarm_control_panel)
                if coord and getattr(coord, "data", None):
                    systems = list(coord.data)  # shallow copy
                    for i, s in enumerate(systems):
                        if s.get("id") == cb_row_id:
                            s2 = dict(s)
                            s2["socket_message"] = message
                            systems[i] = s2
                            coord.async_set_updated_data(systems)
                            break

            # Se il token è già scaduto prima di connettersi, prova la login ora
            if self.is_token_expired():
                _LOGGER.info("Token scaduto, provo login (single-shot)")
                try:
                    await self.login(self._email, self._password)
                    # opzionale: propaga il nuovo token ad altre socket aperte
                    try:
                        await self.refresh_token_for_all_clients()
                    except Exception:
                        pass
                except Exception as e:
                    _LOGGER.warning("[socket %s] Login fallita, non avvio la socket: %s", row_id, e)
                    self._update_socket_status(row_id, None, False)
                    self._reset_zone_sensors(row_id)
                    return False

            # Se esiste già un client per questa centrale
            if row_id in self._socket_clients:
                client = self._socket_clients[row_id]
                if client.is_connected():
                    _LOGGER.debug(f"Connessione socket già avviata per {row_id}")
                    return True
                else:
                    _LOGGER.info(f"Rimuovo client socket non connesso per {row_id}")
                    await client.stop()
                    self._socket_clients.pop(row_id, None)

            # Crea e avvia il nuovo client socket

            coord = self.hass.data[DOMAIN].get("coordinator")
            client = LinceSocketClient(
                self.token,
                row_id,
                message_callback=message_callback,
                disconnect_callback=disconnect_callback,
                connect_callback=connect_callback,
                # abilita re-login automatico lato socket
                hass=self.hass,
                api=self,
                auth_failed_callback=self._on_auth_failed
            )

            connected = await client.start()  # non blocca: ha retry interno
            if not connected:
                _LOGGER.info(f"[{row_id}] Connessione in corso... ricontrollo tra 3 secondi")
                await asyncio.sleep(3)
                if not client.is_connected():
                    await client.stop()
                    self._update_socket_status(row_id, None, False)
                    self._reset_zone_sensors(row_id)
                    return False

            self._update_socket_status(row_id, client, True)
            return True

    async def stop_socket_connection(self, row_id: int) -> None:
        """Ferma la connessione socket per una specifica centrale."""
        client = self._socket_clients.get(row_id)
        if client:
            try:
                # Imposta flag di stop volontario
                client._stop = True
                await client.stop()
                _LOGGER.info(f"Socket {row_id} fermata")
            except Exception as e:
                _LOGGER.error(f"Errore durante stop socket {row_id}: {e}")
            finally:
                # Rimuovi sempre il client
                if row_id in self._socket_clients:
                    del self._socket_clients[row_id]
        
        # Pulisci tutto lo stato associato
        self._update_socket_status(row_id, None, False)
        self._reset_zone_sensors(row_id)
        self.latest_socket_message.pop(row_id, None)  # Pulisci anche i messaggi
        update_buscomm_binarysensors(self, row_id, None)
        update_buscomm_sensors(self, row_id, None)
        
        _LOGGER.info(f"Socket {row_id} completamente fermata e stato pulito")

    def is_socket_connected(self, row_id: int) -> bool:
        client = self._socket_clients.get(row_id)
        return client.is_connected() if client else False

    def get_last_socket_message(self, row_id: int):
        """Ultimo messaggio socket ricevuto per la centrale."""
        return self.latest_socket_message.get(row_id)

    # -------------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------------

    def _update_socket_status(self, row_id: int, client: LinceSocketClient | None, connected: bool):
        """Aggiorna lo stato della connessione socket e il relativo sensore."""
        if connected and client:
            self._socket_clients[row_id] = client
            _LOGGER.info(f"[{DOMAIN}: {row_id}] Connessione socket avviata correttamente")
        else:
            self._socket_clients.pop(row_id, None)
            _LOGGER.warning(f"[{DOMAIN}: {row_id}] Connessione socket terminata o fallita")
            self._reset_zone_sensors(row_id)
            update_buscomm_binarysensors(self, row_id, None)
            update_buscomm_sensors(self, row_id, None)

        sensor = self.socket_connection_sensor.get(row_id)
        if sensor:
            sensor.update_status(connected)

    def _reset_zone_sensors(self, row_id: int):
        """Resetta lo stato di tutti i sensori di zona a None."""
        if hasattr(self, "zone_sensors"):
            for rid, zone_dict in self.zone_sensors.items():  # evita shadowing di row_id
                for sensor in zone_dict.get("filare", {}).values():
                    sensor.update_attributes("filare", None)
                for sensor in zone_dict.get("radio", {}).values():
                    sensor.update_attributes("radio", None)

    # Helper on-demand per capability Teknox dall'ultimo messaggio (post-PIN)
    def extract_teknox_caps_from_last_message(self, row_id: int) -> dict:
        msg = self.latest_socket_message.get(row_id)
        _LOGGER.debug(f"[{row_id}] Estraggo capability Teknox da ultimo messaggio WS: {msg}")
        if not msg:
            return {}
        try:
            # parser locale per evitare race sul parser condiviso
            from .europlusParser import europlusParser

            p = europlusParser(msg)
            c = p.get_isTeknoxAuthorized() or {}
            _LOGGER.debug(f"[{row_id}] Capability Teknox estratte: {c}")
            return {
                "g1": bool(c.get("g1", False)),
                "g2": bool(c.get("g2", False)),
                "g3": bool(c.get("g3", False)),
                "gext": bool(c.get("gext", False)),
                "authorized": bool(c.get("authorized", False)),
                "auth_level": int(c.get("auth_level", 0)),
            }
        except Exception:
            return {}

    # -------------------------------------------------------------------------
    # Callback dal client socket in caso di re-login ripetutamente fallito
    # -------------------------------------------------------------------------
    async def _on_auth_failed(self, row_id: int, reason: str):
        """
        Invocata dal LinceSocketClient dopo >= 2 fallimenti consecutivi di re-login.
        - Notifica persistente in HA (debounced).
        - Aggiorna eventuale sensore di connessione a False.
        - NON ferma la socket: i retry con backoff proseguono.
        """
        now = datetime.now(timezone.utc)
        last = self._auth_failed_last_notify.get(row_id)
        if last and (now - last).total_seconds() < AUTH_FAIL_NOTIFY_COOLDOWN:
            # troppo presto per una nuova notifica
            return

        # Notifica persistente in HA
        try:
            title = "GoldCloud: autenticazione richiesta"
            msg = (
                f"Centrale **{row_id}**: impossibile rinnovare l'autenticazione.\n\n"
                f"Motivo: `{reason}`.\n\n"
                "Verifica le credenziali dell'integrazione o rilancia la login."
            )
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": title,
                    "message": msg,
                    "notification_id": f"goldcloud_auth_failed_{row_id}",
                },
                blocking=False,
            )
        except Exception as e:
            _LOGGER.debug("Impossibile creare persistent_notification: %s", e)

        # Marca lo stato di connessione come non connesso (se presente il sensore)
        sensor = self.socket_connection_sensor.get(row_id)
        if sensor:
            try:
                sensor.update_status(False)
            except Exception:
                pass

        self._auth_failed_last_notify[row_id] = now
        _LOGGER.warning("[%s] Re-login ripetutamente fallito: %s", row_id, reason)
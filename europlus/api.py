"""API implementation for Lince Europlus."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from homeassistant.core import HomeAssistant

from .socket_client import EuroplusSocketClient
from .parser.parser import europlusParser
from ..const import (
    DOMAIN,
    AUTH_FAIL_NOTIFY_COOLDOWN,
    RETRY_INTERVAL,
)
from ..common.api import CommonAPI
from ..utils import convert_zone_attributes
from ..binary_sensor import update_buscomm_binarysensors
from ..sensor import update_buscomm_sensors

_LOGGER = logging.getLogger(__name__)


class EuroplusAPI(CommonAPI):
    """API implementation specific to Lince Europlus."""
    
    def __init__(self, hass: HomeAssistant, email: str | None = None, password: str | None = None):
        super().__init__(hass, email, password)  # Inizializza CommonAPI
        
        # Socket state specifico Europlus
        self._socket_clients: dict[int, EuroplusSocketClient] = {}
        self.latest_socket_message: dict[int, dict] = {}
        self._lock = asyncio.Lock()

        # Entity registries (popolate dall'integrazione)
        self.socket_message_sensor: dict[int, object] = {}
        self.socket_connection_sensor: dict[int, object] = {}
        self.zone_sensors: dict[int, dict] = {}
        self.buscomm_sensors: dict[int, dict] = {}

        # Parser Europlus
        self._europlusParser = europlusParser(None)

        # Debounce notifiche re-auth
        self._auth_failed_last_notify: dict[int, datetime] = {}

    def is_socket_connected(self, row_id: int) -> bool:
        """Verifica se la socket è connessa per un sistema - SPECIFICO EUROPLUS."""
        client = self._socket_clients.get(row_id)
        return client.is_connected() if client else False

    def get_socket_client(self, row_id: int) -> EuroplusSocketClient | None:
        """Restituisce il client socket - SPECIFICO EUROPLUS."""
        return self._socket_clients.get(row_id)

    async def start_socket_connection(self, row_id: int):
        """Avvia la connessione socket per un sistema - SPECIFICO EUROPLUS."""
        _LOGGER.debug(f"Avvio connessione socket Europlus per centrale {row_id}")
        
        async with self._lock:
            try:
                coord = self.hass.data[DOMAIN].get("coordinator")
            except Exception:
                coord = None

            # Callback per connessione
            async def connect_callback(cb_row_id: int):
                _LOGGER.info(f"[{cb_row_id}] Riconnesso alla socket Europlus")
                sensor = self.socket_connection_sensor.get(cb_row_id)
                if sensor:
                    sensor.update_status(True)

            # Callback per disconnessione
            async def disconnect_callback(cb_row_id: int):
                _LOGGER.warning(f"[{cb_row_id}] Disconnessione dalla socket Europlus rilevata")
                sensor = self.socket_connection_sensor.get(cb_row_id)
                if sensor:
                    sensor.update_status(False)

            # Callback per messaggi - PARSING SPECIFICO EUROPLUS
            async def message_callback(cb_row_id: int, message):
                _LOGGER.debug(f"[{cb_row_id}] Messaggio socket Europlus ricevuto")
                self.latest_socket_message[cb_row_id] = message

                # Aggiorna l'eventuale "sensore messaggi"
                sensor = self.socket_message_sensor.get(cb_row_id)
                if sensor:
                    sensor.update_message(message)

                # Parsing messaggio CON PARSER EUROPLUS
                _LOGGER.debug(f"[{cb_row_id}] Parsing Europlus zone/sensori")
                zone_dict_filare = self.zone_sensors.get(cb_row_id, {}).get("filare", {})
                zone_dict_radio = self.zone_sensors.get(cb_row_id, {}).get("radio", {})

                self._europlusParser.parse(message)

                # Aggiorna evento autorizzazione Teknox (SPECIFICO EUROPLUS)
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

                # Zone filari - PARSING EUROPLUS
                ingressi_filari = self._europlusParser.get_ingressi_filari(len(zone_dict_filare))
                if ingressi_filari:
                    for idx, state in enumerate(ingressi_filari):
                        s = zone_dict_filare.get(idx + 1)
                        if s:
                            attributes = convert_zone_attributes("filare", ingressi_filari[idx])
                            s.update_attributes("filare", attributes)

                # Zone radio - PARSING EUROPLUS
                ingressi_radio = self._europlusParser.get_ingressi_radio(len(zone_dict_radio))
                if ingressi_radio:
                    for idx, state in enumerate(ingressi_radio):
                        s = zone_dict_radio.get(idx + 1)
                        if s:
                            attributes = convert_zone_attributes("radio", ingressi_radio[idx])
                            s.update_attributes("radio", attributes)

                # Stato centrale EUROPLUS
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

                _LOGGER.debug(f"[{cb_row_id}] Stato centrale Europlus aggiornato")
                update_buscomm_binarysensors(self, cb_row_id, self.buscomm_sensors[cb_row_id])
                update_buscomm_sensors(self, cb_row_id, self.buscomm_sensors[cb_row_id])

                # Push al coordinator
                if coord and getattr(coord, "data", None):
                    systems = list(coord.data)
                    for i, s in enumerate(systems):
                        if s.get("id") == cb_row_id:
                            s2 = dict(s)
                            s2["socket_message"] = message
                            systems[i] = s2
                            coord.async_set_updated_data(systems)
                            break

            # Se il token è già scaduto, usa login() da CommonAPI
            if self.is_token_expired():
                _LOGGER.info("Token scaduto, provo login")
                try:
                    await self.login(self._email, self._password)  # USA METODO COMUNE!
                    await self.refresh_token_for_all_clients()
                except Exception as e:
                    _LOGGER.warning("[socket %s] Login fallita: %s", row_id, e)
                    self._update_socket_status(row_id, None, False)
                    self._reset_zone_sensors(row_id)
                    return False

            # Se esiste già un client per questa centrale
            if row_id in self._socket_clients:
                client = self._socket_clients[row_id]
                if client.is_connected():
                    _LOGGER.debug(f"Connessione socket Europlus già avviata per {row_id}")
                    return True
                else:
                    _LOGGER.info(f"Rimuovo client socket Europlus non connesso per {row_id}")
                    await client.stop()
                    self._socket_clients.pop(row_id, None)

            # Crea e avvia il nuovo client socket EUROPLUS
            client = EuroplusSocketClient(
                self.token,
                row_id,
                message_callback=message_callback,
                disconnect_callback=disconnect_callback,
                connect_callback=connect_callback,
                hass=self.hass,
                api=self,
                auth_failed_callback=self._on_auth_failed
            )

            connected = await client.start()
            if not connected:
                _LOGGER.info(f"[{row_id}] Connessione Europlus in corso...")
                await asyncio.sleep(3)
                if not client.is_connected():
                    await client.stop()
                    self._update_socket_status(row_id, None, False)
                    self._reset_zone_sensors(row_id)
                    return False

            self._update_socket_status(row_id, client, True)
            self._socket_clients[row_id] = client
            return True

    async def stop_socket_connection(self, row_id: int):
        """Ferma la connessione socket per un sistema - SPECIFICO EUROPLUS."""
        client = self._socket_clients.get(row_id)
        if client:
            try:
                client._stop = True
                await client.stop()
                _LOGGER.info(f"Socket Europlus {row_id} fermata")
            except Exception as e:
                _LOGGER.error(f"Errore durante stop socket Europlus {row_id}: {e}")
            finally:
                if row_id in self._socket_clients:
                    del self._socket_clients[row_id]
        
        self._update_socket_status(row_id, None, False)
        self._reset_zone_sensors(row_id)
        self.latest_socket_message.pop(row_id, None)
        update_buscomm_binarysensors(self, row_id, None)
        update_buscomm_sensors(self, row_id, None)
        
        _LOGGER.info(f"Socket Europlus {row_id} completamente fermata")

    async def send_arm_disarm_command(self, row_id: int, program_mask: int, pin: str):
        """Invia comando arm/disarm via socket - SPECIFICO EUROPLUS."""
        if row_id not in self._socket_clients:
            _LOGGER.error(f"[{row_id}] Socket Europlus non attiva per invio comando")
            raise Exception("Socket non attiva")
        
        client = self._socket_clients[row_id]
        
        # Converti PIN string in lista di interi - FORMATO EUROPLUS
        pin_digits = [int(d) for d in pin if d.isdigit()][:6]
        while len(pin_digits) < 6:
            pin_digits.append(0)
        
        # Invia PIN - METODO EUROPLUS
        await client.async_send_pin(pin_digits)
        
        # Attendi autorizzazione - LOGICA EUROPLUS
        authorized = await client.wait_for_authorized(row_id, timeout=10)
        if not authorized:
            _LOGGER.error(f"[{row_id}] Timeout autorizzazione PIN Europlus")
            raise Exception("Autorizzazione PIN fallita")
        
        # Decodifica mask - PROGRAMMI EUROPLUS (G1, G2, G3, GEXT)
        g1 = bool(program_mask & 1)
        g2 = bool(program_mask & 2)
        g3 = bool(program_mask & 4)
        gext = bool(program_mask & 8)
        
        await client.async_send_program_activation(g1, g2, g3, gext)
        _LOGGER.info(f"[{row_id}] Comando Europlus inviato: G1={g1}, G2={g2}, G3={g3}, GEXT={gext}")

    async def close_all_sockets(self):
        """Chiudi tutte le socket aperte - SPECIFICO EUROPLUS."""
        _LOGGER.info("Chiusura di tutte le socket Europlus attive...")
        
        _socket_clients = list(self._socket_clients.items())
        
        for row_id, client in _socket_clients:
            try:
                _LOGGER.info(f"Chiusura socket Europlus per centrale {row_id}...")
                if client:
                    client._stop = True
                    if hasattr(client, 'sio') and client.sio:
                        await client.sio.disconnect()
                    await client.stop()
                    _LOGGER.info(f"Socket Europlus {row_id} chiusa correttamente")
            except Exception as e:
                _LOGGER.error(f"Errore chiusura socket Europlus {row_id}: {e}")
            finally:
                if row_id in self._socket_clients:
                    del self._socket_clients[row_id]
        
        self._socket_clients.clear()
        _LOGGER.info("Tutte le socket Europlus sono state chiuse")

    def get_last_socket_message(self, row_id: int) -> Optional[str]:
        """Ritorna l'ultimo messaggio socket ricevuto - SPECIFICO EUROPLUS."""
        return self.latest_socket_message.get(row_id)

    async def refresh_token_for_all_clients(self):
        """Propaga il nuovo token a tutti i client socket - SPECIFICO EUROPLUS."""
        for cid, client in list(self._socket_clients.items()):
            try:
                await client.refresh_connection(self.token)
            except Exception:
                _LOGGER.debug("[%s] refresh_connection Europlus fallita.", cid)

    def extract_teknox_caps_from_last_message(self, row_id: int) -> dict:
        """Estrae le capability Teknox dall'ultimo messaggio - SPECIFICO EUROPLUS."""
        msg = self.latest_socket_message.get(row_id)
        _LOGGER.debug(f"[{row_id}] Estraggo capability Teknox Europlus")
        if not msg:
            return {}
        try:
            from .parser.parser import europlusParser
            p = europlusParser(msg)
            c = p.get_isTeknoxAuthorized() or {}
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

    # Metodi interni SPECIFICI EUROPLUS
    def _update_socket_status(self, row_id: int, client: EuroplusSocketClient | None, connected: bool):
        """Aggiorna lo stato della connessione socket - INTERNO EUROPLUS."""
        if connected and client:
            self._socket_clients[row_id] = client
            _LOGGER.info(f"[Europlus: {row_id}] Connessione socket avviata")
        else:
            self._socket_clients.pop(row_id, None)
            _LOGGER.warning(f"[Europlus: {row_id}] Connessione socket terminata")
            self._reset_zone_sensors(row_id)
            update_buscomm_binarysensors(self, row_id, None)
            update_buscomm_sensors(self, row_id, None)

        sensor = self.socket_connection_sensor.get(row_id)
        if sensor:
            sensor.update_status(connected)

    def _reset_zone_sensors(self, row_id: int):
        """Resetta lo stato di tutti i sensori di zona - INTERNO EUROPLUS."""
        if hasattr(self, "zone_sensors") and row_id in self.zone_sensors:
            zone_dict = self.zone_sensors.get(row_id, {})
            for sensor in zone_dict.get("filare", {}).values():
                if hasattr(sensor, 'update_attributes'):
                    sensor.update_attributes("filare", None)
            for sensor in zone_dict.get("radio", {}).values():
                if hasattr(sensor, 'update_attributes'):
                    sensor.update_attributes("radio", None)

    async def _on_auth_failed(self, row_id: int, reason: str):
        """Callback per auth fallita - SPECIFICO EUROPLUS."""
        now = datetime.now(timezone.utc)
        last = self._auth_failed_last_notify.get(row_id)
        if last and (now - last).total_seconds() < AUTH_FAIL_NOTIFY_COOLDOWN:
            return

        try:
            title = "LinceCloud Europlus: autenticazione richiesta"
            msg = (
                f"Centrale Europlus **{row_id}**: impossibile rinnovare l'autenticazione.\n\n"
                f"Motivo: `{reason}`.\n\n"
                "Verifica le credenziali dell'integrazione."
            )
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": title,
                    "message": msg,
                    "notification_id": f"europlus_auth_failed_{row_id}",
                },
                blocking=False,
            )
        except Exception as e:
            _LOGGER.debug("Impossibile creare persistent_notification: %s", e)

        sensor = self.socket_connection_sensor.get(row_id)
        if sensor:
            try:
                sensor.update_status(False)
            except Exception:
                pass

        self._auth_failed_last_notify[row_id] = now
        _LOGGER.warning("[Europlus %s] Re-login fallito: %s", row_id, reason)
        
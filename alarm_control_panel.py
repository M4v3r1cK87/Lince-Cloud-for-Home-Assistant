from __future__ import annotations
import asyncio
import logging
from typing import Optional, List, Tuple
from datetime import datetime, timedelta

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    CodeFormat,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .utils import send_multiple_notifications, dismiss_persistent_notification

_LOGGER = logging.getLogger(__name__)

# Bitmask per G1/G2/G3/GEXT
BIT_MAP = {"g1": 1, "g2": 2, "g3": 4, "gext": 8}

# Timeout di "decadimento" del pending se non arriva la conferma WS
PENDING_DECAY_SECONDS = 7.0


def _to_mask(programs: Optional[List[str]]) -> int:
    m = 0
    for p in programs or []:
        m |= BIT_MAP.get(p, 0)
    return m


def _mask_to_programs_list(mask: int) -> list[str]:
    return [p for p, bit in BIT_MAP.items() if mask & bit]


def _code_to_pin_list(code: Optional[str]) -> list[int]:
    if not code or not code.isdigit() or len(code) != 6:
        raise ValueError("Il codice deve essere una stringa di 6 cifre.")
    return [int(c) for c in code]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN]["coordinator"]
    api = hass.data[DOMAIN]["api"]
    systems = coordinator.data or []
    entities = []
    for s in systems:
        row_id = s["id"]
        name = s.get("nome") or s.get("name") or f"Centrale {row_id}"
        unique_id = f"lince_{row_id}_alarmpanel"
        entities.append(
            LinceAlarmPanelEntity(
                name, unique_id, row_id, coordinator, api, entry
            )
        )
    async_add_entities(entities, update_before_add=True)


class LinceAlarmPanelEntity(CoordinatorEntity, AlarmControlPanelEntity):
    """
    Stato da WS + pending ottimistico:
    - TRIGGERED -> generali_1.allarme True
    - PENDING   -> (entry timer attivo) generali_4.tempo_in_g1g2g3 OR generali_5.tempo_in_gext
    - DISARMED  -> tutti attivo_g* False
    - ARMING    -> (exit timer attivo) generali_4.tempo_out_g1g2g3 OR generali_5.tempo_out_gext
    - ARMED_*   -> (almeno un programma attivo) e nessun timer attivo -> mappa mask su profilo
    Pending locale (ARMING/DISARMING) per feedback immediato, chiuso alla conferma WS con invalidazione PIN.
    Ora include anche il profilo 'vacation' con mappatura a ARMED_VACATION.
    """

    _attr_code_format = CodeFormat.NUMBER

    def __init__(
        self,
        name: str,
        unique_id: str,
        row_id: int,
        coordinator,
        api,
        config_entry: ConfigEntry,
    ):
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._row_id = row_id
        self._api = api
        self._entry = config_entry

        self._last_error: str | None = None

        # Stato ottimistico transitorio
        self._pending_state: AlarmControlPanelState | None = None
        self._pending_expected_mask: int | None = None
        self._pending_profile: str | None = None
        self._pending_timeout_task: asyncio.Task | None = None
        self._should_invalidate_pin_when_confirmed: bool = False
        
        # Tracking per notifiche TRIGGERED
        self._last_triggered_notification: Optional[datetime] = None
        self._last_known_state: Optional[AlarmControlPanelState] = None  # Traccia ultimo stato
        self._internal_command_active: bool = False  # Traccia comandi interni
        self._initial_sync_done: bool = False  # Traccia se abbiamo fatto la sync iniziale

    # ---------- Funzioni unificate per notifiche ----------
    
    async def _send_armed_notification(self, profile: str = None):
        """Invia notifica ARMED unificata."""
        if not profile:
            # Determina il profilo dallo stato corrente
            state = self.alarm_state
            if state == AlarmControlPanelState.ARMED_HOME:
                profile = "home"
            elif state == AlarmControlPanelState.ARMED_AWAY:
                profile = "away"
            elif state == AlarmControlPanelState.ARMED_NIGHT:
                profile = "night"
            elif state == AlarmControlPanelState.ARMED_VACATION:
                profile = "vacation"
            else:
                profile = "custom"
        
        profile_names = {
            "home": "HOME",
            "away": "AWAY",
            "night": "NIGHT",
            "vacation": "VACATION",
            "custom": "CUSTOM"
        }
        
        try:
            await send_multiple_notifications(
                self.hass,
                message=f"🔒 {self._attr_name} armata in modalità {profile_names.get(profile, profile.upper())}",
                title=f"LinceCloud - {self._attr_name} - Sistema Armato - {profile_names.get(profile, profile.upper())}",
                persistent=True,
                persistent_id=f"alarm_armed_{self._row_id}",
                mobile=True,
                centrale_id=self._row_id,
                data={
                    "tag": f"alarm_armed_{self._row_id}",
                    "priority": "high",
                    "color": "green",
                    "notification_icon": "mdi:shield-check"
                }
            )
            _LOGGER.debug("[%s] Notifica ARMED (%s) inviata", self._row_id, profile)
        except Exception as e:
            _LOGGER.error("[%s] Errore invio notifica ARMED: %s", self._row_id, e)

    async def _send_disarmed_notification(self):
        """Invia notifica DISARMED unificata."""
        try:
            await send_multiple_notifications(
                self.hass,
                message=f"🔓 {self._attr_name} disarmata",
                title=f"LinceCloud - {self._attr_name} - Sistema Disarmato",
                persistent=True,
                persistent_id=f"alarm_disarmed_{self._row_id}",
                mobile=True,
                centrale_id=self._row_id,
                data={
                    "tag": f"alarm_disarmed_{self._row_id}",
                    "priority": "normal",
                    "color": "blue",
                    "notification_icon": "mdi:shield-off"
                }
            )
            _LOGGER.debug("[%s] Notifica DISARMED inviata", self._row_id)
        except Exception as e:
            _LOGGER.debug("[%s] Errore invio notifica DISARMED: %s", self._row_id, e)

    async def _send_triggered_notification(self):
        """Invia notifica TRIGGERED unificata."""
        try:
            await send_multiple_notifications(
                self.hass,
                message=f"⚠️ ALLARME IN CORSO - {self._attr_name}",
                title=f"LinceCloud - {self._attr_name} - 🚨 ALLARME SCATTATO",
                persistent=True,
                persistent_id=f"alarm_triggered_{self._row_id}",
                mobile=True,
                centrale_id=self._row_id,
                data={
                    "tag": f"alarm_triggered_{self._row_id}",
                    "priority": "high",
                    "color": "red",
                    "notification_icon": "mdi:bell-ring"
                }
            )
            _LOGGER.info("[%s] Notifica TRIGGERED inviata", self._row_id)
        except Exception as e:
            _LOGGER.error("[%s] Errore invio notifica TRIGGERED: %s", self._row_id, e)

    async def _send_pin_error_notification(self, action: str = "operazione"):
        """Invia notifica PIN errato unificata."""
        try:
            await send_multiple_notifications(
                self.hass,
                message=f"❌ PIN errato per {self._attr_name}. {action.capitalize()} rifiutato.",
                title=f"LinceCloud - {self._attr_name} - Errore Autenticazione",
                persistent=True,
                persistent_id=f"pin_error_{self._row_id}",
                mobile=True,
                centrale_id=self._row_id,
                data={
                    "tag": f"pin_error_{self._row_id}",
                    "priority": "high",
                    "color": "red"
                }
            )
        except Exception as e:
            _LOGGER.debug("[%s] Errore invio notifica PIN errato: %s", self._row_id, e)

    # ---------- Proprietà base ----------
    @property
    def name(self) -> str | None:
        return self._attr_name

    @property
    def device_info(self):
        return DeviceInfo(identifiers={(f"{DOMAIN}", self._row_id)})

    @property
    def code_arm_required(self) -> bool:
        return True

    @property
    def supported_features(self) -> int:
        pm = self._build_profile_masks()
        feats = 0
        if pm.get("home", 0) != 0:
            feats |= AlarmControlPanelEntityFeature.ARM_HOME
        if pm.get("away", 0) != 0:
            feats |= AlarmControlPanelEntityFeature.ARM_AWAY
        if pm.get("night", 0) != 0:
            feats |= AlarmControlPanelEntityFeature.ARM_NIGHT
        if pm.get("vacation", 0) != 0:
            feats |= AlarmControlPanelEntityFeature.ARM_VACATION
        return feats

    # ---------- Stato ----------
    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """
        Precedenze (WS sovrasta il pending locale, TRIGGERED ha massima priorità):
        0) Se allarme attivo -> TRIGGERED
        0bis) Se pending DISARMING -> mostra DISARMING fino a spegnimento programmi
        1) Se entry timer attivo -> PENDING (verso TRIGGERED)
        2) Se tutti i programmi inattivi -> DISARMED
        3) Se exit timer attivo -> ARMING
        4) Se almeno un programma attivo e nessun timer -> ARMED_* (o CUSTOM_BYPASS)
        5) Fallback -> pending locale (se presente) o None
        """
        system = self._get_system()
        socket_msg = system.get("socket_message") if system else None
        (
            mask,
            tempo_out_active,
            progs_any,
            tempo_in_active,
            alarm_triggered,
        ) = self._parse_ws_status(socket_msg)

        # 0) TRIGGERED ha massima priorità
        if alarm_triggered:
            #self.hass.async_create_task(self._send_triggered_notification())
            return AlarmControlPanelState.TRIGGERED

        # 0bis) Priorità al pending DISARMING (UI reattiva durante il disinserimento)
        if self._pending_state == AlarmControlPanelState.DISARMING:
            return (
                AlarmControlPanelState.DISARMED
                if progs_any is False
                else AlarmControlPanelState.DISARMING
            )

        # 1) PENDING: entry timer di ingresso attivo
        if tempo_in_active:
            return AlarmControlPanelState.PENDING

        # 2) DISARMED: tutti attivo_g* False
        if progs_any is False:
            #self.hass.async_create_task(self._send_disarmed_notification())
            return AlarmControlPanelState.DISARMED

        # 0ter) Priorità al pending ARMING (UI reattiva appena validato il PIN)
        if self._pending_state == AlarmControlPanelState.ARMING:
            # Se WS ha già completato l'inserimento, mostra ARMED_*;
            # altrimenti resta in ARMING anche se i timer non sono ancora partiti.
            if progs_any and not tempo_out_active and not tempo_in_active:
                mapped = self._mask_to_ha_state_by_profiles(mask or 0)
                return mapped or AlarmControlPanelState.ARMED_CUSTOM_BYPASS
            return AlarmControlPanelState.ARMING

        # 3) ARMING: exit timer attivo
        if progs_any and tempo_out_active:
            return AlarmControlPanelState.ARMING

        # 4) ARMED_*: almeno un attivo, nessun timer
        if progs_any and not tempo_out_active and not tempo_in_active:
            mapped = self._mask_to_ha_state_by_profiles(mask or 0)
            #self.hass.async_create_task(self._send_armed_notification())
            return mapped or AlarmControlPanelState.ARMED_CUSTOM_BYPASS

        # 5) fallback al pending (es. durante avvio o frame parziali)
        if self._pending_state is not None:
            return self._pending_state

        return None

    @property
    def extra_state_attributes(self):
        attrs = {}
        system = self._get_system() or {}
        socket_msg = system.get("socket_message")
        (
            mask,
            tempo_out_active,
            progs_any,
            tempo_in_active,
            alarm_triggered,
        ) = self._parse_ws_status(socket_msg)
        pm = self._build_profile_masks()
        attrs["current_mask"] = mask or 0
        attrs["current_programs"] = _mask_to_programs_list(mask or 0)
        attrs["profile_masks"] = pm  # include anche 'vacation'
        attrs["arming_timers_active"] = bool(tempo_out_active)
        attrs["entry_timers_active"] = bool(tempo_in_active)
        attrs["any_program_active"] = bool(progs_any)
        attrs["alarm_triggered"] = bool(alarm_triggered)
        if self._pending_state is not None:
            attrs["pending_state"] = self._pending_state.name
            attrs["pending_expected_mask"] = self._pending_expected_mask
            attrs["pending_profile"] = self._pending_profile
        if getattr(self, "_last_error", None):
            attrs["last_error"] = self._last_error
        return attrs

    # ---------- Coordinator push (chiusura pending alla conferma WS) ----------
    def _handle_coordinator_update(self) -> None:
        """
        Gestisce cambio stati e invia notifiche per cambiamenti esterni.
        """
        try:
            current_state = self.alarm_state
            previous_state = self._last_known_state
            
            # Gestione sincronizzazione iniziale dopo riavvio
            if not self._initial_sync_done and current_state is not None:
                self._initial_sync_done = True
                self._last_known_state = current_state
                
                _LOGGER.info(
                    "[%s] Sincronizzazione iniziale completata. Stato: %s",
                    self._row_id,
                    current_state.name if current_state else "None"
                )
                
                # Se la centrale è ARMED al riavvio, invia notifica informativa
                if current_state in [
                    AlarmControlPanelState.ARMED_HOME,
                    AlarmControlPanelState.ARMED_AWAY,
                    AlarmControlPanelState.ARMED_NIGHT,
                    AlarmControlPanelState.ARMED_VACATION,
                    AlarmControlPanelState.ARMED_CUSTOM_BYPASS
                ]:
                    _LOGGER.info("[%s] Centrale già armata al riavvio, invio notifica stato", self._row_id)
                    # Notifica solo persistente per non spammare
                    self.hass.async_create_task(
                        send_multiple_notifications(
                            self.hass,
                            message=f"ℹ️ {self._attr_name} è attualmente ARMATA",
                            title=f"LinceCloud - Stato {self._attr_name}",
                            persistent=True,
                            persistent_id=f"alarm_sync_{self._row_id}",
                            mobile=False,  # No notifica mobile al boot
                            centrale_id=self._row_id
                        )
                    )
                
                # Se è in TRIGGERED al riavvio, notifica importante
                elif current_state == AlarmControlPanelState.TRIGGERED:
                    _LOGGER.warning("[%s] Centrale in allarme al riavvio!", self._row_id)
                    self.hass.async_create_task(self._send_triggered_notification())
                
                # Non serve altro, usciamo
                return
            
            # Rileva transizioni di stato e invia notifiche
            if previous_state != current_state and previous_state is not None:
                
                # Log per debug
                _LOGGER.info(
                    "[%s] Transizione stato: %s -> %s (internal_cmd: %s, pending: %s)",
                    self._row_id,
                    previous_state.name if previous_state else "None",
                    current_state.name if current_state else "None",
                    self._internal_command_active,
                    self._pending_state.name if self._pending_state else "None"
                )
                
                # TRIGGERED
                if current_state == AlarmControlPanelState.TRIGGERED:
                    now = datetime.now()
                    if (not self._last_triggered_notification or 
                        (now - self._last_triggered_notification) > timedelta(minutes=5)):
                        self._last_triggered_notification = now
                        self.hass.async_create_task(self._send_triggered_notification())
                
                # ARMED (qualsiasi fonte)
                elif current_state in [
                    AlarmControlPanelState.ARMED_HOME,
                    AlarmControlPanelState.ARMED_AWAY,
                    AlarmControlPanelState.ARMED_NIGHT,
                    AlarmControlPanelState.ARMED_VACATION,
                    AlarmControlPanelState.ARMED_CUSTOM_BYPASS
                ]:
                    # Invia SEMPRE la notifica quando lo stato diventa ARMED
                    # Il flag internal_command_active impedirà duplicati
                    if previous_state == AlarmControlPanelState.ARMING:
                        _LOGGER.info("[%s] Transizione ARMING -> ARMED, invio notifica", self._row_id)
                        self.hass.async_create_task(self._send_armed_notification())
                        # Reset flag se era comando interno
                        if self._internal_command_active:
                            self._internal_command_active = False
                    elif not self._internal_command_active:
                        # Comando esterno (non da ARMING)
                        _LOGGER.info("[%s] ARMED da fonte esterna, invio notifica", self._row_id)
                        self.hass.async_create_task(self._send_armed_notification())
                
                # DISARMED (qualsiasi fonte)  
                elif current_state == AlarmControlPanelState.DISARMED:
                    # Se viene da DISARMING ed è comando interno, skip (già notificato)
                    if previous_state == AlarmControlPanelState.DISARMING and self._internal_command_active:
                        _LOGGER.debug("[%s] DISARMED da comando interno, già notificato", self._row_id)
                        self._internal_command_active = False  # Reset flag
                    else:
                        # Era TRIGGERED? Pulisci notifica persistente
                        if previous_state == AlarmControlPanelState.TRIGGERED:
                            self.hass.async_create_task(
                                dismiss_persistent_notification(
                                    self.hass,
                                    f"alarm_triggered_{self._row_id}"
                                )
                            )
                            self._last_triggered_notification = None
                        
                        _LOGGER.info("[%s] Invio notifica DISARMED", self._row_id)
                        self.hass.async_create_task(self._send_disarmed_notification())
            
            # Salva stato corrente per prossimo ciclo
            self._last_known_state = current_state
            
            # Gestione pending per comandi interni
            if self._pending_state is not None:
                system = self._get_system() or {}
                socket_msg = system.get("socket_message")
                (
                    mask,
                    tempo_out_active,
                    progs_any,
                    tempo_in_active,
                    alarm_triggered,
                ) = self._parse_ws_status(socket_msg)

                if self._pending_state == AlarmControlPanelState.ARMING:
                    if not tempo_out_active and progs_any:
                        _LOGGER.info(
                            "[%s] Conferma ARMING via WS. Chiudo pending.",
                            self._row_id,
                        )
                        self._clear_pending(write_state=False)
                        self.hass.async_create_task(self._post_confirm_actions())
                        # La notifica verrà inviata sopra quando rileva la transizione ARMING->ARMED

                elif self._pending_state == AlarmControlPanelState.DISARMING:
                    if progs_any is False:
                        _LOGGER.info(
                            "[%s] Conferma DISARMING via WS.",
                            self._row_id,
                        )
                        self._clear_pending(write_state=False)
                        self.hass.async_create_task(self._post_confirm_actions())
                        # La notifica è già stata inviata in async_alarm_disarm
                        
        except Exception as e:
            _LOGGER.error("[%s] Errore in _handle_coordinator_update: %s", self._row_id, e)
        finally:
            super()._handle_coordinator_update()

    # ---------- Helpers diagnostici ----------
    def _set_error(self, msg: str):
        self._last_error = msg
        self.async_write_ha_state()
        _LOGGER.debug(f"[Alarm Control Panel - {self._row_id}] {msg}")

    def _clear_error(self):
        if self._last_error:
            self._last_error = None
            self.async_write_ha_state()

    def _build_profile_masks(self):
        """Ritorna {'home': int, 'away': int, 'night': int, 'vacation': int} dalle opzioni."""
        profiles = self._entry.options.get("arm_profiles", {})
        cfg = profiles.get(str(self._row_id), {}) or {}
        return {
            "home": _to_mask(cfg.get("home")),
            "away": _to_mask(cfg.get("away")),
            "night": _to_mask(cfg.get("night")),
            "vacation": _to_mask(cfg.get("vacation")),
        }

    # ---------- Parsing WS centralizzato ----------
    def _parse_ws_status(
        self, socket_msg
    ) -> Tuple[Optional[int], bool, bool, bool, bool]:
        """
        Ritorna: (mask, tempo_out_active, progs_any, tempo_in_active, alarm_triggered)

        - mask calcolata da generali_3.attivo_g*
        - tempo_out_active = generali_4.tempo_out_g1g2g3 OR generali_5.tempo_out_gext (EXIT)
        - progs_any = attivo_g1 OR attivo_g2 OR attivo_g3 OR attivo_gext
        - tempo_in_active = generali_4.tempo_in_g1g2g3 OR generali_5.tempo_in_gext (ENTRY -> PENDING)
        - alarm_triggered = generali_1.allarme
        """
        if not socket_msg:
            return None, False, False, False, False
        try:
            from .europlusParser import europlusParser

            p = europlusParser(socket_msg)

            g1 = p.get_generali_1() or {}
            g3 = p.get_generali_3() or {}
            g4 = p.get_generali_4() or {}
            g5 = p.get_generali_5() or {}

            a1 = bool(g3.get("attivo_g1"))
            a2 = bool(g3.get("attivo_g2"))
            a3 = bool(g3.get("attivo_g3"))
            ax = bool(g3.get("attivo_gext"))

            mask = 0
            if a1:
                mask |= 1
            if a2:
                mask |= 2
            if a3:
                mask |= 4
            if ax:
                mask |= 8

            tempo_out_active = bool(g4.get("tempo_out_g1g2g3")) or bool(
                g5.get("tempo_out_gext")
            )
            tempo_in_active = bool(g4.get("tempo_in_g1g2g3")) or bool(
                g5.get("tempo_in_gext")
            )
            progs_any = a1 or a2 or a3 or ax
            alarm_triggered = bool(g1.get("allarme"))

            return mask, tempo_out_active, progs_any, tempo_in_active, alarm_triggered

        except Exception as e:
            _LOGGER.debug("[%s] _parse_ws_status error: %s", self._row_id, e)
            return None, False, False, False, False

    def _mask_to_ha_state_by_profiles(
        self, current_mask: int
    ) -> AlarmControlPanelState | None:
        """Mappa mask -> stato HA in base alle configurazioni utente."""
        if current_mask == 0:
            return AlarmControlPanelState.DISARMED
        pm = self._build_profile_masks()
        if current_mask == (pm.get("home") or 0):
            return AlarmControlPanelState.ARMED_HOME
        if current_mask == (pm.get("away") or 0):
            return AlarmControlPanelState.ARMED_AWAY
        if current_mask == (pm.get("night") or 0):
            return AlarmControlPanelState.ARMED_NIGHT
        if current_mask == (pm.get("vacation") or 0):
            return AlarmControlPanelState.ARMED_VACATION
        return None  # non corrisponde a nessun profilo conosciuto

    def _get_system(self) -> Optional[dict]:
        if not self.coordinator.data:
            return None
        for s in self.coordinator.data:
            if s.get("id") == self._row_id:
                return s
        return None

    def _get_profile_programs(self, profile: str) -> Optional[List[str]]:
        profiles = self._entry.options.get("arm_profiles")
        if not profiles:
            return None
        return (profiles.get(str(self._row_id), {}) or {}).get(profile)

    async def _ensure_socket(self):
        if not self._api.is_socket_connected(self._row_id):
            await self._api.start_socket_connection(self._row_id)

    # ---------- Pending ottimistico + invalidazione PIN post-conferma ----------
    def _start_pending(
        self,
        state: AlarmControlPanelState,
        expected_mask: int,
        profile: str | None,
        timeout: float = PENDING_DECAY_SECONDS,
    ) -> None:
        """Imposta pending (ARMING/DISARMING) e timer di decadimento."""
        self._clear_pending(write_state=False)
        self._pending_state = state
        self._pending_expected_mask = expected_mask
        self._pending_profile = profile

        async def _decay():
            try:
                await asyncio.sleep(timeout)
                _LOGGER.debug(
                    "[%s] Pending %s scaduto senza conferma WS",
                    self._row_id,
                    state.name if state else "UNKNOWN",
                )
            except asyncio.CancelledError:
                return
            finally:
                self._clear_pending(write_state=True)

        self._pending_timeout_task = asyncio.create_task(_decay())
        self.async_write_ha_state()

    def _clear_pending(self, write_state: bool = True) -> None:
        if self._pending_timeout_task and not self._pending_timeout_task.done():
            self._pending_timeout_task.cancel()
        self._pending_timeout_task = None
        self._pending_state = None
        self._pending_expected_mask = None
        self._pending_profile = None
        if write_state:
            self.async_write_ha_state()

    async def _post_confirm_actions(self) -> None:
        """Azioni post-conferma WS: invalidazione PIN (logout) se richiesto."""
        if not self._should_invalidate_pin_when_confirmed:
            return
        try:
            await self._ensure_socket()
            client = self._api.get_socket_client(self._row_id)
            if client is None:
                _LOGGER.debug(
                    "[%s] Socket non disponibile per invalidazione PIN",
                    self._row_id,
                )
                return
            await self._pin_invalidation(client)
        finally:
            self._should_invalidate_pin_when_confirmed = False

    async def _pin_invalidation(self, client) -> None:
        """Invia il PIN di invalidazione (000000) dopo la conferma WS."""
        try:
            pin = _code_to_pin_list("000000")
        except ValueError as e:
            self._set_error(str(e))
            await self._send_pin_error_notification("Invalidazione PIN")
            return
        try:
            await client.async_send_pin(pin)
            _LOGGER.debug("[%s] PIN di invalidazione inviato", self._row_id)
        except Exception as e:
            self._set_error(f"Errore invio PIN di logout {e}")

    # ---------- Comandi ----------
    async def _arm_with_profile(self, profile: str, code: Optional[str]) -> None:
        # 0) Config profilo
        configured = self._get_profile_programs(profile)
        if configured is None:
            self._set_error(
                f"Profilo '{profile}' non configurato. Controlla le Opzioni della centrale."
            )
            return
        if _to_mask(configured) == 0:
            self._set_error(
                f"Profilo '{profile}' non disponibile (nessun programma selezionato)."
            )
            return
        if not configured:
            self._set_error(
                f"Profilo '{profile}' vuoto. Controlla le Opzioni della centrale."
            )
            return

        # 1) Socket
        await self._ensure_socket()
        client = self._api.get_socket_client(self._row_id)
        if client is None:
            self._set_error("Socket non disponibile.")
            return
        client.reset_authorized(self._row_id)

        # 2) PIN
        try:
            pin = _code_to_pin_list(code)
        except ValueError as e:
            self._set_error(str(e))
            await self._send_pin_error_notification("Inserimento")
            return
        try:
            await client.async_send_pin(pin)
        except Exception as e:
            self._set_error(f"Errore invio PIN: {e}")
            return

        # 3) Attesa autorizzazione (10s)
        ok = await client.wait_for_authorized(self._row_id, timeout=10.0)
        if not ok:
            self._set_error("Autorizzazione non confermata (PIN errato).")
            # Notifica PIN errato - persistente + mobile
            await self._send_pin_error_notification("Inserimento")
            return

        # 4) Verifica capability Teknox dal LAST message parsato
        caps = self._api.extract_teknox_caps_from_last_message(self._row_id) or {}
        invalid = [p for p in configured if not caps.get(p, False)]
        if invalid:
            nice = ", ".join(p.upper() for p in invalid)
            error_msg = (
                f"Attivazione negata: programmi non attivabili ({nice}). "
                "Controlla l'associazione programmi nelle Opzioni della centrale."
            )
            self._set_error(error_msg)
            await self._send_pin_error_notification("Programma")  # Usa funzione unificata
            return

        # >>> Avvio pending ARMING PRIMA dell'invio per UI reattiva <<<
        expected_mask = _to_mask(configured)
        self._clear_error()
        self._should_invalidate_pin_when_confirmed = True
        self._internal_command_active = True  # Segna comando interno
        self._start_pending(
            state=AlarmControlPanelState.ARMING,
            expected_mask=expected_mask,
            profile=profile,
            timeout=PENDING_DECAY_SECONDS,
        )

        # 5) Invia ATTIVAZIONE; se fallisce, annulla il pending
        g1, g2, g3, gext = (
            "g1" in configured,
            "g2" in configured,
            "g3" in configured,
            "gext" in configured,
        )
        try:
            await client.async_send_program_activation(g1, g2, g3, gext)
            # Notifica ARMED
            #profile_names = {
            #    "home": "HOME",
            #    "away": "AWAY",
            #    "night": "NIGHT",
            #    "vacation": "VACATION"
            #}
            #try:
            #    await self._send_armed_notification(profile)
            #    _LOGGER.debug("[%s] Notifica ARMED (%s) inviata", self._row_id, profile)
            #except Exception as e:
            #    _LOGGER.debug("[%s] Errore invio notifica ARMED: %s", self._row_id, e)
        except Exception as e:
            self._clear_pending(write_state=True)
            self._set_error(f"Errore invio attivazione: {e}")
            return

    async def async_alarm_disarm(self, code: Optional[str] = None) -> None:
        await self._ensure_socket()
        client = self._api.get_socket_client(self._row_id)
        if client is None:
            self._set_error("Socket non disponibile.")
            return
        try:
            pin = _code_to_pin_list(code)
        except ValueError as e:
            self._set_error(str(e))
            await self._send_pin_error_notification("Disinserimento")  # Usa funzione unificata
            return

        client.reset_authorized(self._row_id)
        await client.async_send_pin(pin)
        ok = await client.wait_for_authorized(self._row_id, timeout=10.0)
        if not ok:
            self._set_error("Autorizzazione non confermata (PIN errato).")
            await self._send_pin_error_notification("PIN")  # Usa funzione unificata
            return

        await client.async_send_program_activation(False, False, False, False)
        self._clear_error()
        
        # Pulisci notifica TRIGGERED se presente
        try:
            await dismiss_persistent_notification(
                self.hass,
                f"alarm_triggered_{self._row_id}"
            )
            self._last_triggered_notification = None
        except Exception as e:
            _LOGGER.debug("[%s] Errore rimozione notifica TRIGGERED: %s", self._row_id, e)
        
        # Notifica DISARMED
        try:
            # Notifica DISARMED - solo mobile
            await self._send_disarmed_notification()
        except Exception as e:
            _LOGGER.debug("[%s] Errore invio notifica DISARMED: %s", self._row_id, e)
        
        # Pending DISARMING; logout post-conferma quando WS indica progs_any=False
        self._should_invalidate_pin_when_confirmed = True
        self._internal_command_active = True  # Segna comando interno
        self._start_pending(
            state=AlarmControlPanelState.DISARMING,
            expected_mask=0,
            profile="disarm",
            timeout=PENDING_DECAY_SECONDS,
        )

    async def async_alarm_arm_home(self, code: Optional[str] = None) -> None:
        await self._arm_with_profile("home", code)

    async def async_alarm_arm_away(self, code: Optional[str] = None) -> None:
        await self._arm_with_profile("away", code)

    async def async_alarm_arm_night(self, code: Optional[str] = None) -> None:
        await self._arm_with_profile("night", code)

    async def async_alarm_arm_vacation(self, code: Optional[str] = None) -> None:
        await self._arm_with_profile("vacation", code)

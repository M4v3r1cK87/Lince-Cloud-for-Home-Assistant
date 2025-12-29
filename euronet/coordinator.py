"""
Coordinator per connessione locale EuroPlus/EuroNET.

Gestisce l'aggiornamento periodico dei dati dalla centrale locale.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import timedelta
from typing import Any, Optional
from dataclasses import asdict

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import EuroNetClient, StatoCentrale
from .zone_config import (
    ZoneConfigFetcher,
    ZoneConfigs,
    ZoneFilareConfig,
    ZoneRadioConfig,
)
from .const import (
    CONF_NUM_ZONE_FILARI,
    CONF_NUM_ZONE_RADIO,
    CONF_ARM_PROFILES,
    CONF_POLLING_INTERVAL,
    DEFAULT_POLLING_INTERVAL_MS,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_INSTALLER_CODE,
    DEFAULT_LOCAL_USERNAME,
)
from ..utils import send_persistent_notification, send_multiple_notifications

_LOGGER = logging.getLogger(__name__)

# Intervallo di polling di fallback (usato se non configurato)
DEFAULT_UPDATE_INTERVAL = timedelta(milliseconds=DEFAULT_POLLING_INTERVAL_MS)

# Configurazione retry per caricamento zone
ZONE_CONFIG_RETRY_DELAY = 60  # Secondi tra un retry e l'altro
ZONE_CONFIG_MAX_RETRIES = 10  # Numero massimo di retry automatici


class EuroNetCoordinator(DataUpdateCoordinator):
    """Coordinator per gestire l'aggiornamento dati dalla centrale locale."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: EuroNetClient,
        config_entry: ConfigEntry,
    ) -> None:
        """Inizializza il coordinator."""
        # Calcola l'intervallo di polling dalla configurazione
        polling_ms = config_entry.options.get(
            CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL_MS
        )
        update_interval = timedelta(milliseconds=polling_ms)
        
        super().__init__(
            hass,
            _LOGGER,
            name="EuroNET",
            update_interval=update_interval,
        )
        self.client = client
        self.config_entry = config_entry
        self._systems: list[dict] = []
        
        # Stato sessione web
        self._session_valid = False
        self._login_retry_count = 0
        self._max_login_retries = 3
        
        # Cache configurazione zone (caricata una volta all'init)
        self._zone_configs: Optional[ZoneConfigs] = None
        self._zone_configs_loaded = False
        self._zone_configs_complete = False  # True se tutte le zone sono state caricate
        self._zone_config_retry_count = 0
        self._zone_config_retry_task: Optional[asyncio.Task] = None
        self._zone_config_lock = asyncio.Lock()  # Lock per evitare caricamenti paralleli
        
        _LOGGER.info(
            "EuroNET coordinator inizializzato con polling interval: %dms",
            polling_ms
        )
    
    @property
    def num_zone_filari(self) -> int:
        """Numero di zone filari configurate."""
        return self.config_entry.options.get(CONF_NUM_ZONE_FILARI, 0)
    
    @property
    def num_zone_radio(self) -> int:
        """Numero di zone radio configurate."""
        return self.config_entry.options.get(CONF_NUM_ZONE_RADIO, 0)
    
    @property
    def arm_profiles(self) -> dict:
        """Profili ARM configurati."""
        return self.config_entry.options.get(CONF_ARM_PROFILES, {})
    
    @property
    def zone_configs(self) -> Optional[ZoneConfigs]:
        """Configurazioni complete delle zone."""
        return self._zone_configs
    
    def reset_zone_configs_cache(self) -> None:
        """Resetta la cache delle configurazioni zone per forzare un reload.
        
        Chiamare questo metodo quando il codice installatore viene modificato
        o quando è necessario ricaricare le configurazioni.
        """
        # Cancella eventuale task di retry in corso
        if self._zone_config_retry_task and not self._zone_config_retry_task.done():
            self._zone_config_retry_task.cancel()
            self._zone_config_retry_task = None
        
        self._zone_configs = None
        self._zone_configs_loaded = False
        self._zone_configs_complete = False
        self._zone_config_retry_count = 0
        _LOGGER.info("Cache configurazioni zone resettata")
    
    async def _schedule_zone_config_retry(self) -> None:
        """Programma un retry per il caricamento delle zone mancanti."""
        if self._zone_config_retry_count >= ZONE_CONFIG_MAX_RETRIES:
            _LOGGER.warning(
                "Raggiunto il limite massimo di retry (%d) per caricamento zone. "
                "Alcune zone potrebbero non essere configurate correttamente.",
                ZONE_CONFIG_MAX_RETRIES
            )
            return
        
        self._zone_config_retry_count += 1
        _LOGGER.info(
            "Programmato retry automatico caricamento zone tra %d secondi (tentativo %d/%d)",
            ZONE_CONFIG_RETRY_DELAY,
            self._zone_config_retry_count,
            ZONE_CONFIG_MAX_RETRIES
        )
        
        await asyncio.sleep(ZONE_CONFIG_RETRY_DELAY)
        
        # Salva il numero di zone caricate prima del retry
        prev_filari = len(self._zone_configs.zone_filari) if self._zone_configs else 0
        prev_radio = len(self._zone_configs.zone_radio) if self._zone_configs else 0
        
        # Reset per permettere un nuovo tentativo
        self._zone_configs_loaded = False
        
        # Esegui il caricamento (passiamo from_retry=True per gestire la logica)
        await self._async_load_zone_configs(from_retry=True)
        
        # Dopo il retry, verifica se abbiamo caricato nuove zone
        if self._zone_configs:
            new_filari = len(self._zone_configs.zone_filari)
            new_radio = len(self._zone_configs.zone_radio)
            
            # Se abbiamo caricato nuove zone, forza un reload dell'integrazione
            if new_filari > prev_filari or new_radio > prev_radio:
                _LOGGER.info(
                    "Caricate nuove zone (filari: %d->%d, radio: %d->%d). "
                    "Ricarico l'integrazione per creare le nuove entità...",
                    prev_filari, new_filari, prev_radio, new_radio
                )
                # Schedula il reload per non bloccare
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self.config_entry.entry_id)
                )
            else:
                # Non abbiamo caricato nuove zone, programma un altro retry
                num_filari = self.num_zone_filari
                num_radio = self.num_zone_radio
                if (new_filari < num_filari or new_radio < num_radio) and self._zone_config_retry_count < ZONE_CONFIG_MAX_RETRIES:
                    _LOGGER.info("Retry non ha caricato nuove zone, ne programmo un altro")
                    self._zone_config_retry_task = asyncio.create_task(
                        self._schedule_zone_config_retry()
                    )
        
    async def _async_load_zone_configs(self, from_retry: bool = False) -> None:
        """Carica le configurazioni complete delle zone usando il codice installatore.
        
        Questo metodo viene chiamato una sola volta durante l'inizializzazione
        o durante il reload dell'integrazione. Usa ZoneConfigFetcher per
        recuperare tutti i dati di configurazione delle zone filari e radio
        dalla centrale tramite web scraping.
        
        Args:
            from_retry: Se True, siamo in un retry e non creiamo nuovi task di retry
        """
        # Usa lock per evitare caricamenti paralleli
        async with self._zone_config_lock:
            if self._zone_configs_loaded:
                return
            
            num_filari = self.num_zone_filari
            num_radio = self.num_zone_radio
            
            if num_filari == 0 and num_radio == 0:
                _LOGGER.info("Nessuna zona configurata - salta caricamento configurazioni")
                self._zone_configs_loaded = True
                return
            
            # Recupera credenziali dalla configurazione dell'utente
            options = self.config_entry.options
            data = self.config_entry.data
            
            host = options.get(CONF_HOST) or data.get(CONF_HOST, "")
            password = options.get(CONF_PASSWORD) or data.get(CONF_PASSWORD, "")
            installer_code = options.get(CONF_INSTALLER_CODE) or data.get(CONF_INSTALLER_CODE, "")
            
            if not installer_code:
                _LOGGER.info(
                    "Codice installatore non configurato - "
                    "i dettagli di configurazione delle zone non saranno disponibili"
                )
                self._zone_configs_loaded = True
                return
            
            if not host or not password:
                _LOGGER.warning(
                    "Credenziali incomplete - "
                    "impossibile caricare configurazione zone"
                )
                self._zone_configs_loaded = True
                return
                
            try:
                _LOGGER.info(
                    "Caricamento configurazione zone: %d filari, %d radio",
                    num_filari, num_radio
                )
                
                # Usa ZoneConfigFetcher per recuperare le configurazioni
                fetcher = ZoneConfigFetcher(
                    host=host,
                    username=DEFAULT_LOCAL_USERNAME,
                    password=password,
                    installer_code=installer_code,
                    num_zone_filari=num_filari,
                    num_zone_radio=num_radio,
                    timeout=30,  # Timeout più lungo per il fetch iniziale
                )
                
                # Esegui il fetch in un executor per non bloccare
                new_configs = await fetcher.fetch_all_zones()
                
                # Debug: log stato prima del merge
                prev_count = len(self._zone_configs.zone_filari) if self._zone_configs else 0
                new_count = len(new_configs.zone_filari) if new_configs else 0
                _LOGGER.info(
                    "Merge zone: precedenti=%d, nuove=%d, self._zone_configs=%s, new_configs=%s",
                    prev_count, new_count, 
                    bool(self._zone_configs), bool(new_configs)
                )
                
                # Merge con le configurazioni esistenti (per retry)
                if self._zone_configs and new_configs:
                    # Unisci le zone: le nuove si aggiungono/sovrascrivono le vecchie
                    _LOGGER.info("Merge: zone esistenti=%s, nuove=%s", 
                        list(self._zone_configs.zone_filari.keys()),
                        list(new_configs.zone_filari.keys())
                    )
                    for zona_num, zona_config in new_configs.zone_filari.items():
                        self._zone_configs.zone_filari[zona_num] = zona_config
                    for zona_num, zona_config in new_configs.zone_radio.items():
                        self._zone_configs.zone_radio[zona_num] = zona_config
                    self._zone_configs.timestamp = new_configs.timestamp
                    _LOGGER.info("Dopo merge: zone=%s", list(self._zone_configs.zone_filari.keys()))
                elif new_configs:
                    _LOGGER.info("No merge: self._zone_configs è None/vuoto, uso new_configs")
                    self._zone_configs = new_configs
                else:
                    _LOGGER.warning("No merge: new_configs è None/vuoto")
                
                # Log dei risultati e verifica completezza
                if self._zone_configs:
                    loaded_filari = len(self._zone_configs.zone_filari)
                    loaded_radio = len(self._zone_configs.zone_radio)
                    configured_filari = len(self._zone_configs.zone_filari_configurate)
                    configured_radio = len(self._zone_configs.zone_radio_configurate)
                    
                    _LOGGER.info(
                        "Configurazioni zone caricate: %d/%d filari (%d configurate), "
                        "%d/%d radio (%d configurate)",
                        loaded_filari, num_filari, configured_filari,
                        loaded_radio, num_radio, configured_radio,
                    )
                    
                    # Verifica se tutte le zone attese sono state caricate
                    if loaded_filari >= num_filari and loaded_radio >= num_radio:
                        self._zone_configs_complete = True
                        _LOGGER.info("Caricamento zone completato con successo")
                    else:
                        self._zone_configs_complete = False
                        missing_filari = num_filari - loaded_filari
                        missing_radio = num_radio - loaded_radio
                        _LOGGER.warning(
                            "Caricamento zone incompleto: mancano %d filari e %d radio",
                            max(0, missing_filari), max(0, missing_radio)
                        )
                        # Programma retry automatico solo se non siamo già in un retry
                        # (il retry gestisce autonomamente il prossimo tentativo)
                        if not from_retry and self._zone_config_retry_count < ZONE_CONFIG_MAX_RETRIES:
                            self._zone_config_retry_task = asyncio.create_task(
                                self._schedule_zone_config_retry()
                            )
                else:
                    self._zone_configs_complete = False
                    _LOGGER.warning("Nessuna configurazione zone caricata")
                    # Programma retry automatico solo se non siamo già in un retry
                    if not from_retry and self._zone_config_retry_count < ZONE_CONFIG_MAX_RETRIES:
                        self._zone_config_retry_task = asyncio.create_task(
                            self._schedule_zone_config_retry()
                        )
                
                self._zone_configs_loaded = True
                
            except Exception as e:
                _LOGGER.error("Errore caricamento configurazioni zone: %s", e)
                self._zone_configs_loaded = True
                # Programma retry anche in caso di errore (solo se non siamo già in un retry)
                if not from_retry and self._zone_config_retry_count < ZONE_CONFIG_MAX_RETRIES:
                    self._zone_config_retry_task = asyncio.create_task(
                        self._schedule_zone_config_retry()
                    )
        
    async def _ensure_session(self) -> bool:
        """Assicura che la sessione web sia valida, effettuando login se necessario.
        
        Returns:
            True se la sessione è valida, False se il login fallisce
        """
        if self._session_valid:
            return True
        
        # Ottieni il codice installatore per il login
        installer_code = getattr(self.client, 'installer_code', None)
        if not installer_code:
            _LOGGER.warning("Codice installatore non configurato - alcune funzionalità potrebbero non essere disponibili")
            # Prova comunque a leggere lo stato senza login (potrebbe funzionare per dati base)
            return True
        
        _LOGGER.debug("Tentativo login sessione web EuroNET...")
        
        try:
            success = await self.hass.async_add_executor_job(
                self.client.login, installer_code
            )
            if success:
                self._session_valid = True
                self._login_retry_count = 0
                _LOGGER.info("Sessione web EuroNET stabilita")
                return True
            else:
                self._login_retry_count += 1
                _LOGGER.warning(
                    "Login EuroNET fallito (tentativo %d/%d)",
                    self._login_retry_count, self._max_login_retries
                )
                return False
        except Exception as e:
            self._login_retry_count += 1
            _LOGGER.error("Errore durante login EuroNET: %s", e)
            return False
    
    def invalidate_session(self) -> None:
        """Invalida la sessione corrente, forzando un re-login al prossimo update."""
        self._session_valid = False
        _LOGGER.debug("Sessione EuroNET invalidata")

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch data dalla centrale locale."""
        try:
            # Assicura che la sessione sia valida
            await self._ensure_session()
            
            # Al primo update, carica le configurazioni delle zone
            if not self._zone_configs_loaded:
                await self._async_load_zone_configs()
            
            # Esegui operazioni sincrone in executor
            stato = await self.hass.async_add_executor_job(
                self.client.get_stato_centrale
            )
            
            if not stato:
                # Sessione potrebbe essere scaduta - invalida e riprova
                if self._session_valid:
                    _LOGGER.debug("Stato centrale non disponibile - possibile sessione scaduta")
                    self.invalidate_session()
                    # Tenta un re-login
                    if await self._ensure_session():
                        # Riprova a leggere lo stato
                        stato = await self.hass.async_add_executor_job(
                            self.client.get_stato_centrale
                        )
                
                if not stato:
                    raise UpdateFailed("Impossibile leggere stato centrale")
            
            # Leggi zone filari
            zone_filari = await self.hass.async_add_executor_job(
                self.client.get_stato_zone_filari
            )
            
            # Costruisci struttura dati compatibile con l'integrazione esistente
            # Simuliamo un "sistema" cloud-like per compatibilità
            system_data = self._build_system_data(stato, zone_filari)
            
            self._systems = [system_data]
            
            # IMPORTANTE: restituisce direttamente la lista dei sistemi
            # per compatibilità con le piattaforme che iterano su coordinator.data
            return self._systems
            
        except UpdateFailed:
            # Re-raise senza log aggiuntivo (già loggato sopra)
            raise
        except Exception as e:
            _LOGGER.error(f"Errore aggiornamento dati locali: {e}")
            raise UpdateFailed(f"Errore comunicazione: {e}")
    
    def _build_system_data(self, stato: StatoCentrale, zone_filari: list) -> dict:
        """Costruisce struttura dati sistema compatibile con cloud."""
        # Mappiamo lo stato locale a una struttura simile a quella cloud
        # per minimizzare le modifiche alle entità esistenti
        
        # Determina lo stato generale
        gstate = []
        if stato.g1:
            gstate.append("G1")
        if stato.g2:
            gstate.append("G2")
        if stato.g3:
            gstate.append("G3")
        if stato.gext:
            gstate.append("GEXT")
        
        # Numero di zone configurate dall'utente
        num_filari = self.num_zone_filari
        num_radio = self.num_zone_radio
            
        # Costruisci entries per le zone (solo quelle configurate)
        entries = {}
        for zona in zone_filari:
            # Filtra: includi solo zone fino al numero configurato
            if zona.numero > num_filari:
                continue
                
            # Usa chiave zona_filare_X per distinguere da zone radio
            entry_key = f"zona_filare_{zona.numero}"
            
            # Recupera configurazione dalla cache (se disponibile)
            zone_config = None
            nome = None  # None = nome non trovato, userà fallback nel binary_sensor
            if self._zone_configs and zona.numero in self._zone_configs.zone_filari:
                zone_config = self._zone_configs.zone_filari[zona.numero]
                # Usa il nome solo se è un nome personalizzato (non "INGRESSO XX")
                if zone_config.is_configured:
                    nome = zone_config.nome
            
            # Costruisci entry con stato runtime
            entry_data = {
                "numero": zona.numero,
                "nome": nome,
                "aperta": zona.aperta,
                "esclusa": zona.esclusa,
                "allarme_24h": zona.allarme_24h,
                "memoria_24h": zona.memoria_24h,
                "memoria_allarme": zona.memoria_allarme,
            }
            
            # Aggiungi attributi di configurazione se disponibili
            if zone_config:
                entry_data["config"] = {
                    "tipo": zone_config.tipo_label,
                    "trigger": zone_config.trigger_label,
                    "logica": zone_config.logica_label,
                    "numero_allarmi": zone_config.numero_allarmi_label,
                    "tempo_ingresso": zone_config.tempo_ingresso_totale,
                    "tempo_uscita": zone_config.tempo_uscita_totale,
                    "programmi": [k for k, v in zone_config.programmi.items() if v],
                    "parzializzabile": zone_config.parzializzabile,
                    "ritardato": zone_config.ritardato,
                    "silenzioso": zone_config.silenzioso,
                    "test": zone_config.test,
                    "ronda": zone_config.ronda,
                    "h24": zone_config.h24,
                    "percorso": zone_config.percorso,
                    "uscita_a": zone_config.uscita_a,
                    "uscita_k": zone_config.uscita_k,
                    "fuoco": zone_config.fuoco,
                    "campanello": zone_config.campanello,
                    "elettroserratura": zone_config.elettroserratura,
                }
            
            entries[entry_key] = entry_data
        
        # Aggiungi zone radio (se configurate)
        # Per ora usiamo solo i dati di configurazione, lo stato runtime
        # verrà aggiunto quando il client supporterà la lettura dello stato radio
        if self._zone_configs and num_radio > 0:
            for numero, zone_config in self._zone_configs.zone_radio.items():
                if numero > num_radio:
                    continue
                    
                entry_key = f"zona_radio_{numero}"
                
                # Usa il nome solo se è configurato (non "Non Disponibile")
                nome = zone_config.nome if zone_config.is_configured else None
                
                entry_data = {
                    "numero": numero,
                    "nome": nome,
                    "tipo": "radio",
                    # Stato runtime placeholder (sarà aggiornato quando supportato)
                    "aperta": False,
                    "esclusa": zone_config.escluso,
                    "allarme_24h": False,
                    "memoria_24h": False,
                    "memoria_allarme": False,
                    # Configurazione
                    "config": {
                        "supervisionato": zone_config.supervisionato,
                        "escluso": zone_config.escluso,
                        "associazioni_filari": zone_config.associazioni_filari,
                        "associazione_26_31": zone_config.associazione_26_31,
                        "associazione_27_32": zone_config.associazione_27_32,
                        "associazione_28_33": zone_config.associazione_28_33,
                        "associazione_29_34": zone_config.associazione_29_34,
                        "associazione_30_35": zone_config.associazione_30_35,
                    },
                }
                entries[entry_key] = entry_data
        
        return {
            "id": 1,  # ID locale fisso
            "name": "Centrale Locale",
            "id_centrale": self.client.host,
            "_detected_brand": "lince-europlus",
            "_local": True,
            
            # Stato programmi
            "gstate": ",".join(gstate) if gstate else "",
            "g1": stato.g1,
            "g2": stato.g2,
            "g3": stato.g3,
            "gext": stato.gext,
            
            # Stato generale
            "allarme": stato.allarme,
            "guasto": stato.guasto,
            "rete_220v": stato.rete_220v,
            "batteria_interna_ok": stato.batteria_interna_ok,
            "batteria_esterna_ok": stato.batteria_esterna_ok,
            "modo_servizio": stato.modo_servizio,
            
            # Sabotaggi
            "sabotaggio_centrale": stato.sabotaggio_centrale,
            "sabotaggio_ingressi": stato.sabotaggio_ingressi,
            "sabotaggio_dispositivi_bus": stato.sabotaggio_dispositivi_bus,
            "allarme_integrita_bus": stato.allarme_integrita_bus,
            
            # Memorie sabotaggi
            "memoria_sabotaggio_centrale": stato.memoria_sabotaggio_centrale,
            "memoria_sabotaggio_ingressi": stato.memoria_sabotaggio_ingressi,
            "memoria_sabotaggio_dispositivi_bus": stato.memoria_sabotaggio_dispositivi_bus,
            "memoria_integrita_bus": stato.memoria_integrita_bus,
            
            # Valori
            "tensione_batteria": stato.tensione_batteria,
            "tensione_bus": stato.tensione_bus,
            "temperatura": stato.temperatura,
            "release_sw": stato.release_sw,
            # Alias per compatibilità con entities.py
            "tensione_batteria_v": stato.tensione_batteria,
            "tensione_bus_v": stato.tensione_bus,
            "temperatura_c": stato.temperatura,
            
            # Espansioni
            "espansione_1": stato.espansione_1,
            "espansione_2": stato.espansione_2,
            "espansione_3": stato.espansione_3,
            "espansione_4": stato.espansione_4,
            "espansione_5": stato.espansione_5,
            "espansione_radio": stato.espansione_radio,
            
            # Zone
            "entries": entries,
            "ingressi_aperti": stato.ingressi_aperti,
            "ingressi_esclusi": stato.ingressi_esclusi,
            
            # Configurazione zone
            "num_zone_filari": num_filari,
            "num_zone_radio": num_radio,
            
            # Profili ARM configurati
            "arm_profiles": self.arm_profiles,
            
            # Compatibilità cloud
            "access_data": {},
            "datetime": stato.datetime,
        }
    
    @property
    def systems(self) -> list[dict]:
        """Restituisce la lista dei sistemi."""
        return self._systems
    
    async def async_arm(self, code: str, programs: list[str], arm_mode: str = "away") -> bool:
        """Arma i programmi specificati.
        
        Args:
            code: Codice utente inserito nel pannello allarme
            programs: Lista programmi da armare
            arm_mode: Modalità di armamento (away, home, night, vacation)
        """
        if not code:
            _LOGGER.error("Codice utente non fornito")
            return False
            
        try:
            result = await self.hass.async_add_executor_job(
                self.client.arm, code, programs
            )
            if result:
                await self.async_request_refresh()
                
                # Invia notifica di armamento (rispetta lo switch notifiche)
                mode_names = {
                    "away": "Fuori casa",
                    "home": "In casa", 
                    "night": "Notte",
                    "vacation": "Vacanza"
                }
                mode_name = mode_names.get(arm_mode, arm_mode.capitalize())
                
                await send_multiple_notifications(
                    self.hass,
                    message=f"Centrale armata in modalità **{mode_name}**",
                    title="🔒 Allarme Attivato",
                    persistent=True,
                    persistent_id=f"lince_alarm_armed_{self.client.host}",
                    mobile=True,
                    centrale_id=self.client.host,  # Usa host per controllare le notifiche
                    data={
                        "tag": "lince_alarm_status",
                        "importance": "high",
                        "channel": "alarm",
                        "actions": [
                            {"action": "URI", "title": "Apri Home Assistant", "uri": "/lovelace"}
                        ]
                    }
                )
            return result
        except Exception as e:
            _LOGGER.error(f"Errore arm: {e}")
            return False
    
    async def async_disarm(self, code: str) -> bool:
        """Disarma tutti i programmi.
        
        Args:
            code: Codice utente inserito nel pannello allarme
        """
        if not code:
            _LOGGER.error("Codice utente non fornito")
            return False
            
        try:
            result = await self.hass.async_add_executor_job(
                self.client.disarm, code
            )
            if result:
                await self.async_request_refresh()
                
                # Invia notifica di disarmo (rispetta lo switch notifiche)
                await send_multiple_notifications(
                    self.hass,
                    message="Centrale disarmata",
                    title="🔓 Allarme Disattivato",
                    persistent=True,
                    persistent_id=f"lince_alarm_armed_{self.client.host}",
                    mobile=True,
                    centrale_id=self.client.host,  # Usa host per controllare le notifiche
                    data={
                        "tag": "lince_alarm_status",
                        "importance": "default",
                        "channel": "alarm"
                    }
                )
            return result
        except Exception as e:
            _LOGGER.error(f"Errore disarm: {e}")
            return False

    async def async_shutdown(self) -> None:
        """Cancella task in background, ferma il polling e pulisce le risorse."""
        _LOGGER.info("Shutdown EuroNET coordinator...")
        
        # Ferma gli aggiornamenti periodici
        self.update_interval = None
        
        # Cancella task retry zone config
        if self._zone_config_retry_task and not self._zone_config_retry_task.done():
            _LOGGER.debug("Cancellazione task retry zone config")
            self._zone_config_retry_task.cancel()
            try:
                await self._zone_config_retry_task
            except asyncio.CancelledError:
                pass
            self._zone_config_retry_task = None
        
        # Esegui logout dal client
        try:
            await self.hass.async_add_executor_job(self.client.logout, True)
            _LOGGER.info("Logout EuroNET eseguito durante shutdown coordinator")
        except Exception as e:
            _LOGGER.debug(f"Errore logout durante shutdown (ignorato): {e}")
        
        _LOGGER.info("EuroNET coordinator shutdown completato")

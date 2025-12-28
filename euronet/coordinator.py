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
        await self._async_load_zone_configs()
        
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
        
    async def _async_load_zone_configs(self) -> None:
        """Carica le configurazioni complete delle zone usando il codice installatore.
        
        Questo metodo viene chiamato una sola volta durante l'inizializzazione
        o durante il reload dell'integrazione. Usa ZoneConfigFetcher per
        recuperare tutti i dati di configurazione delle zone filari e radio
        dalla centrale tramite web scraping.
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
                self._zone_configs = await fetcher.fetch_all_zones()
                
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
                        # Programma retry automatico in background (solo se non c'è già un task attivo)
                        if (self._zone_config_retry_count < ZONE_CONFIG_MAX_RETRIES and 
                            (self._zone_config_retry_task is None or self._zone_config_retry_task.done())):
                            self._zone_config_retry_task = asyncio.create_task(
                                self._schedule_zone_config_retry()
                            )
                else:
                    self._zone_configs_complete = False
                    _LOGGER.warning("Nessuna configurazione zone caricata")
                    # Programma retry automatico (solo se non c'è già un task attivo)
                    if (self._zone_config_retry_count < ZONE_CONFIG_MAX_RETRIES and
                        (self._zone_config_retry_task is None or self._zone_config_retry_task.done())):
                        self._zone_config_retry_task = asyncio.create_task(
                            self._schedule_zone_config_retry()
                        )
                
                self._zone_configs_loaded = True
                
            except Exception as e:
                _LOGGER.error("Errore caricamento configurazioni zone: %s", e)
                self._zone_configs_loaded = True
                # Programma retry anche in caso di errore (solo se non c'è già un task attivo)
                if (self._zone_config_retry_count < ZONE_CONFIG_MAX_RETRIES and
                    (self._zone_config_retry_task is None or self._zone_config_retry_task.done())):
                    self._zone_config_retry_task = asyncio.create_task(
                        self._schedule_zone_config_retry()
                    )
        
    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch data dalla centrale locale."""
        try:
            # Al primo update, carica le configurazioni delle zone
            if not self._zone_configs_loaded:
                await self._async_load_zone_configs()
            
            # Esegui operazioni sincrone in executor
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
    
    async def async_arm(self, code: str, programs: list[str]) -> bool:
        """Arma i programmi specificati.
        
        Args:
            code: Codice utente inserito nel pannello allarme
            programs: Lista programmi da armare
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
            return result
        except Exception as e:
            _LOGGER.error(f"Errore disarm: {e}")
            return False

    async def async_shutdown(self) -> None:
        """Cancella task in background e pulisce le risorse."""
        if self._zone_config_retry_task and not self._zone_config_retry_task.done():
            _LOGGER.debug("Cancellazione task retry zone config")
            self._zone_config_retry_task.cancel()
            try:
                await self._zone_config_retry_task
            except asyncio.CancelledError:
                pass
            self._zone_config_retry_task = None

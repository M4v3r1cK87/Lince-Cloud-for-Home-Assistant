"""State parser for Gold centrals - DEFINITIVE VERSION."""
import logging
from typing import Dict, Any, List, Tuple, Optional

_LOGGER = logging.getLogger(__name__)


def stateParser(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse Gold state message from socket.
    Converte i byte ricevuti in dizionario con valori comprensibili.
    """
    _LOGGER.debug(f"stateParser input: {state}")
    
    try:
        parsed = {
            "stato": {
                "sabotaggio_centrale": bool(state.get("stato", 0) & 1),
                "sabotaggio_as_esterno": bool(state.get("stato", 0) & 2),
                "memoria_sabotaggio": bool(state.get("stato", 0) & 4),
                "memoria_sabotaggio_as": bool(state.get("stato", 0) & 8),
                "memoria_allarme_ingressi": bool(state.get("stato", 0) & 16),
                "memoria_sabotaggio_ingresso": bool(state.get("stato", 0) & 32),
                "allarme_inserito": bool(state.get("stato", 0) & 64),
                "servizio": bool(state.get("stato", 0) & 128)
            },
            "alim": {
                # NOTA: I primi 5 bit di alim hanno logica INVERSA nel protocollo!
                # Il bit settato indica PROBLEMA, non stato OK.
                # Per device_class "plug" (rete_220, fusibile): invertiamo perché bit=1 significa problema
                # ma "plug" mostra on=collegato, off=scollegato
                # Per device_class "battery": NON invertiamo perché bit=1 significa problema
                # e "battery" mostra già on=low battery, off=OK
                "rete_220_vca": not bool(state.get("alim", 0) & 1),  # Invertito: bit=1 significa assente, plug on=presente
                "stato_batteria_interna": bool(state.get("alim", 0) & 2),  # NON invertito: bit=1 problema, battery on=low
                "fusibile": not bool(state.get("alim", 0) & 4),  # Invertito: bit=1 significa guasto, plug on=ok
                "stato_batteria_esterna": bool(state.get("alim", 0) & 8),  # NON invertito: bit=1 problema, battery on=low
                "presenza_batteria_interna": bool(state.get("alim", 0) & 16),  # NON invertito: bit=1 assente, battery on=problema
                # Gli allarmi hanno logica normale: bit=1 significa allarme attivo
                "allarme_a": bool(state.get("alim", 0) & 32),
                "allarme_k": bool(state.get("alim", 0) & 64),
                "allarme_tecnologico": bool(state.get("alim", 0) & 128)
            },
            "uscite": {
                "uscita1": bool(state.get("uscite", 0) & 0x01),
                "uscita2": bool(state.get("uscite", 0) & 0x02),
                "uscita3": bool(state.get("uscite", 0) & 0x04),
                "uscita4": bool(state.get("uscite", 0) & 0x08),
                "uscita5": bool(state.get("uscite", 0) & 0x10),
                "elettroserratura": bool(state.get("uscite", 0) & 0x20),
                "sirena_interna": bool(state.get("uscite", 0) & 0x40),
                "sirena_esterna": bool(state.get("uscite", 0) & 0x80)
            },
            "wifi": {
                "connesso": bool(state.get("wifi", 0) & 0x01),
                "configurato": bool(state.get("wifi", 0) & 0x02),
                "errore": bool(state.get("wifi", 0) & 0x04)
            },
            "conn_type": "signal" if int(state.get("gprs", 0)) == 2 else "wifi",
            "vbatt": f"{state.get('vbatt', 0) / 10:.1f}",
            "corrente": f"{(((state.get('electricAC_H', 0) << 8) & 0xFF00) + (state.get('electricAC_L', 0) & 0xFF)) / 1000.0:.1f}",
            "prog": {
                "g1": bool(state.get("prog", 0) & 1),
                "g2": bool(state.get("prog", 0) & 2),
                "g3": bool(state.get("prog", 0) & 4)
            },
            "prog_active": bool(state.get("prog", 0) & 7),
            "programs": state.get("prog", 0),
            "ingr": {
                "g1_aperto": bool(state.get("ingr", 0) & 0x01),
                "g2_aperto": bool(state.get("ingr", 0) & 0x02),
                "g3_aperto": bool(state.get("ingr", 0) & 0x04),
                "supervisione_ingressi": bool(state.get("ingr", 0) & 0x10),
                "guasto_ingressi_radio": bool(state.get("ingr", 0) & 0x20),
                "sabotaggio_ingressi": bool(state.get("ingr", 0) & 0x40)
            },
            "bus": {
                "tamper_bus": bool(state.get("bus", 0) & 0x08),
                "dispositivo_bus_intruso": bool(state.get("bus", 0) & 0x10),
                "sabotaggio_hw_bus": bool(state.get("bus", 0) & 0xB0),
                "guasto_bus": bool(state.get("bus", 0) & 0x80)
            },
            "sync": state.get("sync", 0),
            "sync_perc": state.get("sync_perc", 0),
            "connesso": state.get("connesso", 0),
            "fw_ver": state.get("fw_ver", "").lstrip("0"),
            "raw": state.get("raw", [])
        }
        return parsed
        
    except Exception as e:
        _LOGGER.error(f"Error in stateParser: {e}", exc_info=True)
        return {}


def checkStatoImpianto(state: Dict[str, Any]) -> bool:
    """
    Verifica se ci sono problemi con l'impianto.
    Usa i valori raw (byte) non parsati.
    """
    try:
        result = bool(
            (state.get("alim", 0) & 0x7A) or 
            (state.get("stato", 0) & 0x3F) or 
            (state.get("wifi", 0) & 0x04) or 
            (state.get("bus", 0) & 0xB8)
        )
        
        if result:
            _LOGGER.debug(f"checkStatoImpianto: Issues found")
        
        return result
    except Exception as e:
        _LOGGER.error(f"Error in checkStatoImpianto: {e}")
        return False


def checkZoneAperte(state: Dict[str, Any], intl=None, activation_prog: Optional[int] = None) -> Tuple[bool, List[str], bool]:
    """
    Verifica zone aperte e problemi che impediscono l'inserimento.
    
    Returns:
        Tuple di (ci_sono_problemi, lista_problemi, blocco_totale)
    """
    status = False
    block = False
    string_impedimenti = []
    programs = activation_prog if activation_prog is not None else state.get("programs", 0)
    
    _LOGGER.debug(f"checkZoneAperte: checking with programs={programs:02x}")
    
    # Priorità 1: usa raw array se disponibile (più preciso)
    if "raw" in state and state["raw"] and len(state["raw"]) > 10:
        raw = state["raw"]
        
        # Alimentazione (byte 4)
        if len(raw) > 4:
            if (raw[4] & 0x01) != 0:
                status = True
                string_impedimenti.append("Rete 220Vca assente")
            
            if (raw[4] & 0x04) != 0:
                status = True
                string_impedimenti.append("Fusibile guasto")
        
        # Ingressi (byte 9)
        if len(raw) > 9:
            if (raw[9] & 0x01) != 0 and bool(programs & 0x01):
                status = True
                string_impedimenti.append("G1 Aperto")
            
            if (raw[9] & 0x02) != 0 and bool(programs & 0x02):
                status = True
                string_impedimenti.append("G2 Aperto")
            
            if (raw[9] & 0x04) != 0 and bool(programs & 0x04):
                status = True
                string_impedimenti.append("G3 Aperto")
            
            if (raw[9] & 0x10) != 0:
                status = True
                block = True
                string_impedimenti.append("Supervisione ingressi")
            
            if (raw[9] & 0x20) != 0:
                status = True
                string_impedimenti.append("Guasto ingressi")
            
            if (raw[9] & 0x40) != 0:
                status = True
                string_impedimenti.append("Sabotaggio ingressi")
        
        # Bus (byte 10)
        if len(raw) > 10:
            if (raw[10] & 0x10) != 0:
                status = True
                string_impedimenti.append("Dispositivo bus intruso")
            
            if (raw[10] & 0x20) != 0:
                status = True
                string_impedimenti.append("Sabotaggio hardware bus")
            
            if (raw[10] & 0x08) != 0:
                status = True
                string_impedimenti.append("Tamper bus")
    
    # Priorità 2: fallback su valori parsati se raw non disponibile
    elif state:
        _LOGGER.debug("checkZoneAperte: Using parsed values (no raw array)")
        
        # Alimentazione
        if "alim" in state:
            alim = state["alim"] if isinstance(state["alim"], dict) else {}
            if not alim.get("rete_220_vca", True):
                status = True
                string_impedimenti.append("Rete 220Vca assente")
            if not alim.get("fusibile", True):
                status = True
                string_impedimenti.append("Fusibile guasto")
        
        # Ingressi
        if "ingr" in state:
            ingr = state["ingr"] if isinstance(state["ingr"], dict) else {}
            if ingr.get("g1_aperto", False) and bool(programs & 0x01):
                status = True
                string_impedimenti.append("G1 Aperto")
            if ingr.get("g2_aperto", False) and bool(programs & 0x02):
                status = True
                string_impedimenti.append("G2 Aperto")
            if ingr.get("g3_aperto", False) and bool(programs & 0x04):
                status = True
                string_impedimenti.append("G3 Aperto")
            
            if ingr.get("supervisione_ingressi", False):
                status = True
                block = True
                string_impedimenti.append("Supervisione ingressi")
            if ingr.get("guasto_ingressi_radio", False):
                status = True
                string_impedimenti.append("Guasto ingressi")
            if ingr.get("sabotaggio_ingressi", False):
                status = True
                string_impedimenti.append("Sabotaggio ingressi")
        
        # Bus
        if "bus" in state:
            bus = state["bus"] if isinstance(state["bus"], dict) else {}
            if bus.get("dispositivo_bus_intruso", False):
                status = True
                string_impedimenti.append("Dispositivo bus intruso")
            if bus.get("sabotaggio_hw_bus", False):
                status = True
                string_impedimenti.append("Sabotaggio hardware bus")
            if bus.get("tamper_bus", False):
                status = True
                string_impedimenti.append("Tamper bus")
    else:
        # Nessun dato disponibile
        return (True, ["Problemi di comunicazione"], False)
    
    # Check servizio (sempre da stato parsato)
    if isinstance(state.get("stato"), dict) and state["stato"].get("servizio", False):
        status = True
        string_impedimenti.append("Centrale in servizio")
    
    _LOGGER.debug(f"checkZoneAperte result: status={status}, issues={len(string_impedimenti)}, block={block}")
    return (status, string_impedimenti, block)


class GoldStateParser:
    """Parser completo per stato centrali Gold."""
    
    def __init__(self):
        """Initialize parser."""
        self._last_raw_state = None
        self._last_parsed = None
        _LOGGER.debug("GoldStateParser initialized")
    
    def parse(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Parse stato raw in formato comprensibile."""
        self._last_raw_state = state
        self._last_parsed = stateParser(state)
        return self._last_parsed
    
    def check_stato_impianto(self, state: Optional[Dict[str, Any]] = None) -> bool:
        """Verifica problemi impianto (usa stato raw)."""
        if state is None:
            state = self._last_raw_state
        if not state:
            return False
        return checkStatoImpianto(state)
    
    def check_zone_aperte(self, state: Optional[Dict[str, Any]] = None,
                         activation_prog: Optional[int] = None) -> Tuple[bool, List[str], bool]:
        """Verifica zone aperte (usa stato parsato)."""
        if state is None:
            state = self._last_parsed
        if not state:
            return (True, ["Stato non disponibile"], False)
        return checkZoneAperte(state, None, activation_prog)
    
    # ========== METODI GETTER UTILI ==========
    
    def is_armed(self) -> bool:
        """Verifica se almeno un programma è inserito."""
        if self._last_parsed:
            return self._last_parsed.get("prog_active", False)
        return False
    
    def get_armed_programs(self) -> List[str]:
        """Ottieni lista programmi inseriti."""
        if not self._last_parsed:
            return []
        
        prog = self._last_parsed.get("prog", {})
        armed = []
        if prog.get("g1", False):
            armed.append("G1")
        if prog.get("g2", False):
            armed.append("G2")  
        if prog.get("g3", False):
            armed.append("G3")
        return armed
    
    def get_battery_voltage(self) -> Optional[float]:
        """Ottieni tensione batteria in Volt."""
        if self._last_parsed:
            try:
                return float(self._last_parsed.get("vbatt", "0"))
            except:
                return None
        return None
    
    def get_current_consumption(self) -> Optional[float]:
        """Ottieni consumo corrente in Ampere."""
        if self._last_parsed:
            try:
                return float(self._last_parsed.get("corrente", "0"))
            except:
                return None
        return None
    
    def get_firmware_version(self) -> Optional[str]:
        """Ottieni versione firmware."""
        if self._last_parsed:
            return self._last_parsed.get("fw_ver")
        return None
    
    def get_connection_type(self) -> str:
        """Ottieni tipo connessione (wifi/signal)."""
        if self._last_parsed:
            return self._last_parsed.get("conn_type", "unknown")
        return "unknown"
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Ottieni stato sincronizzazione."""
        if self._last_parsed:
            return {
                "sync": self._last_parsed.get("sync", 0),
                "sync_percentage": self._last_parsed.get("sync_perc", 0),
                "connected": bool(self._last_parsed.get("connesso", 0))
            }
        return {"sync": 0, "sync_percentage": 0, "connected": False}
    
    def get_open_zones(self) -> Dict[str, bool]:
        """Ottieni stato zone aperte."""
        if not self._last_parsed:
            return {}
        
        ingr = self._last_parsed.get("ingr", {})
        return {
            "g1": ingr.get("g1_aperto", False),
            "g2": ingr.get("g2_aperto", False),
            "g3": ingr.get("g3_aperto", False)
        }
    
    def get_outputs_status(self) -> Dict[str, bool]:
        """Ottieni stato uscite."""
        if self._last_parsed:
            return {k: v for k, v in self._last_parsed.get("uscite", {}).items() if not k.startswith("_")}
        return {}
    
    def get_wifi_status(self) -> Dict[str, bool]:
        """Ottieni stato WiFi."""
        if not self._last_parsed:
            return {}
        
        wifi = self._last_parsed.get("wifi", {})
        return {
            "connected": wifi.get("connesso", False),
            "configured": wifi.get("configurato", False),
            "error": wifi.get("errore", False)
        }
    
    def get_active_alarms(self) -> List[str]:
        """Ottieni lista allarmi attivi."""
        if not self._last_parsed:
            return []
        
        alarms = []
        alim = self._last_parsed.get("alim", {})
        stato = self._last_parsed.get("stato", {})
        
        if stato.get("allarme_inserito", False):
            alarms.append("Allarme inserito")
        if alim.get("allarme_a", False):
            alarms.append("Allarme A")
        if alim.get("allarme_k", False):
            alarms.append("Allarme K")
        if alim.get("allarme_tecnologico", False):
            alarms.append("Allarme tecnologico")
        
        return alarms
    
    def get_system_problems(self) -> List[str]:
        """Ottieni lista problemi sistema."""
        if not self._last_parsed:
            return []
        
        problems = []
        
        # Alimentazione
        alim = self._last_parsed.get("alim", {})
        if not alim.get("rete_220_vca", True):
            problems.append("Rete 220V assente")
        if not alim.get("fusibile", True):
            problems.append("Fusibile guasto")
        if alim.get("stato_batteria_interna", False):
            problems.append("Batteria scarica")
        
        # Stato centrale
        stato = self._last_parsed.get("stato", {})
        if stato.get("sabotaggio_centrale", False):
            problems.append("Sabotaggio centrale")
        if stato.get("servizio", False):
            problems.append("Modalità servizio")
        if stato.get("memoria_allarme_ingressi", False):
            problems.append("Memoria allarme")
        if stato.get("memoria_sabotaggio", False):
            problems.append("Memoria sabotaggio")
        
        # Ingressi
        ingr = self._last_parsed.get("ingr", {})
        if ingr.get("supervisione_ingressi", False):
            problems.append("Supervisione ingressi")
        if ingr.get("guasto_ingressi_radio", False):
            problems.append("Guasto ingressi")
        if ingr.get("sabotaggio_ingressi", False):
            problems.append("Sabotaggio ingressi")
        
        # Bus
        bus = self._last_parsed.get("bus", {})
        if bus.get("tamper_bus", False):
            problems.append("Tamper bus")
        if bus.get("guasto_bus", False):
            problems.append("Guasto bus")
        
        # WiFi
        wifi = self._last_parsed.get("wifi", {})
        if wifi.get("errore", False):
            problems.append("Errore WiFi")
        
        return problems
    
    def get_full_state(self) -> Optional[Dict[str, Any]]:
        """Ottieni stato parsato completo."""
        return self._last_parsed
    
    def get_raw_state(self) -> Optional[Dict[str, Any]]:
        """Ottieni stato raw non parsato."""
        return self._last_raw_state
    
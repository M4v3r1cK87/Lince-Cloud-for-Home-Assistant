"""Converter for Gold centrals - from converter.js"""
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from .byte_utils import int2bcd, string_to_array_int

_LOGGER = logging.getLogger(__name__)


def j2bAutoIns(obj: Dict[str, Any]) -> List[int]:
    """Convert auto-inserimento JSON to bytes."""
    try:
        return [
            int2bcd(obj["totale"]["tempo"] // 60) | (0x80 if obj["totale"]["abilitato"] else 0),
            int2bcd(obj["totale"]["tempo"] % 60),
            int2bcd(obj["g1"]["tempo"] // 60) | (0x80 if obj["g1"]["abilitato"] else 0),
            int2bcd(obj["g1"]["tempo"] % 60),
            int2bcd(obj["g2"]["tempo"] // 60) | (0x80 if obj["g2"]["abilitato"] else 0),
            int2bcd(obj["g2"]["tempo"] % 60),
            int2bcd(obj["g3"]["tempo"] // 60) | (0x80 if obj["g3"]["abilitato"] else 0),
            int2bcd(obj["g3"]["tempo"] % 60)
        ]
    except Exception as e:
        _LOGGER.error(f"Error in j2bAutoIns: {e}")
        return [0] * 8


def j2bBus(obj: Dict[str, Any], edit: bool = False) -> List[int]:
    """Convert BUS device JSON to bytes."""
    try:
        arr = []
        if not edit:
            arr.append(obj["identificativo"] & 0xFF)
            arr.append((obj["identificativo"] >> 8) & 0xFF)
            arr.append(int(obj["num_tipo_periferica"]))
            arr.append(int(obj["espansione"]))
        
        arr.extend(string_to_array_int(16, obj.get("nome", "")))
        return arr
    except Exception as e:
        _LOGGER.error(f"Error in j2bBus: {e}")
        return []


def j2bCodice(obj: Dict[str, Any], code: Optional[str] = None) -> List[int]:
    """Convert codice JSON to bytes."""
    try:
        arr = []
        
        # Add code if provided
        if code:
            key = []
            for char in code:
                key.append(0x0A if char == '0' else int(char))
            
            while len(key) < 6:
                key.append(0)
            
            arr.append(key[0] | (key[1] << 4))
            arr.append(key[2] | (key[3] << 4))
            arr.append(key[4] | (key[5] << 4))
        
        # Build permissions byte
        perms = 0
        if obj.get("g1"):
            perms |= 1
        if obj.get("g2"):
            perms |= 2
        if obj.get("g3"):
            perms |= 4
        if obj.get("elettroserratura"):
            perms |= 16
        if obj.get("ronda"):
            perms |= 32
        if obj.get("silenzioso"):
            perms |= 64
        if obj.get("antipanico"):
            perms |= 128
        arr.append(perms)
        
        # Build type byte
        tipo = int(obj.get("tipo_utente", 0))
        if obj.get("tipo_codice"):
            tipo |= 128
        arr.append(tipo)
        
        # Add padding and name
        arr.extend([0, 0, 0])
        arr.extend(string_to_array_int(16, obj.get("nome", "")))
        
        return arr
    except Exception as e:
        _LOGGER.error(f"Error in j2bCodice: {e}")
        return []


def j2bChiave(obj: Dict[str, Any]) -> List[int]:
    """Convert chiave JSON to bytes."""
    try:
        codice = int(obj.get("codice", 0))
        arr = [
            codice & 0xFF,
            (codice >> 8) & 0xFF,
            (codice >> 16) & 0xFF
        ]
        
        # Build permissions byte
        perms = 0
        if obj.get("g1"):
            perms |= 1
        if obj.get("g2"):
            perms |= 2
        if obj.get("g3"):
            perms |= 4
        if obj.get("elettroserratura"):
            perms |= 16
        if obj.get("ronda"):
            perms |= 32
        if obj.get("silenzioso"):
            perms |= 64
        if obj.get("antipanico"):
            perms |= 128
        arr.append(perms)
        
        # Build type byte
        tipo = int(obj.get("tipo_utente", 0))
        if obj.get("tipo_codice"):
            tipo |= 128
        arr.append(tipo)
        
        # Add padding and name
        arr.extend([0, 0, 0])
        arr.extend(string_to_array_int(16, obj.get("nome", "")))
        
        return arr
    except Exception as e:
        _LOGGER.error(f"Error in j2bChiave: {e}")
        return []


def j2bFilare(obj: Dict[str, Any]) -> List[int]:
    """Convert filare JSON to bytes."""
    try:
        arr = []
        
        # First byte - attributes
        byte1 = 0
        if obj.get("test"):
            byte1 |= 1
        if obj.get("escluso"):
            byte1 |= 2
        if obj.get("ronda"):
            byte1 |= 4
        if obj.get("fuoco"):
            byte1 |= 8
        if obj.get("campanello"):
            byte1 |= 16
        if obj.get("silenzioso"):
            byte1 |= 32
        if obj.get("elettroserratura"):
            byte1 |= 64
        if obj.get("parzializzabile"):
            byte1 |= 128
        arr.append(byte1)
        
        # Second byte - groups
        byte2 = 0
        if obj.get("g1"):
            byte2 |= 1
        if obj.get("g2"):
            byte2 |= 2
        if obj.get("g3"):
            byte2 |= 4
        if obj.get("a"):
            byte2 |= 8
        if obj.get("k"):
            byte2 |= 16
        if obj.get("ritardato"):
            byte2 |= 32
        if obj.get("percorso"):
            byte2 |= 64
        if obj.get("sempre_attivo"):
            byte2 |= 128
        arr.append(byte2)
        
        # Third byte - timing and type
        byte3 = obj.get("tempo_trigger", 0)
        byte3 |= obj.get("tipologia_ingresso", 0)
        if obj.get("doppio_impulso"):
            byte3 |= 8
        arr.append(byte3)
        
        # Timing values
        arr.append(int(obj.get("tempo_ingresso", 0)))
        arr.append(int(obj.get("tempo_uscita", 0)))
        arr.append(int(obj.get("cicli_autoesclusione", 0)))
        
        # Padding and name
        arr.extend([0, 0])
        arr.extend(string_to_array_int(16, obj.get("nome", "")))
        
        return arr
    except Exception as e:
        _LOGGER.error(f"Error in j2bFilare: {e}")
        return []


def j2bGsm(obj: Dict[str, Any]) -> List[int]:
    """Convert GSM configuration JSON to bytes."""
    try:
        # Options byte
        options = 0
        if obj.get("opzioni", {}).get("accesso_telegestione"):
            options |= 1
        if obj.get("opzioni", {}).get("visualizzazione_chiamate"):
            options |= 2
        if obj.get("opzioni", {}).get("on"):
            options |= 4
        if obj.get("opzioni", {}).get("gestione_credito"):
            options |= 16
        if obj.get("opzioni", {}).get("gestione_disturbo"):
            options |= 32
        
        # Parse esistenza_in_vita
        esistenza = int(obj.get("esistenza_in_vita", 0))
        days = esistenza // (24 * 60)
        hours = (esistenza % (24 * 60)) // 60
        minutes = esistenza % 60
        
        # Parse scadenza_sim
        scadenza = obj.get("scadenza_sim")
        if isinstance(scadenza, datetime):
            day = scadenza.day
            month = scadenza.month
            year = scadenza.year - 2000
        else:
            day = month = year = 0
        
        return [
            options,
            int(obj.get("numero_tentativi_chiamate", 0)),
            int(obj.get("numero_squilli_risposta", 0)),
            int2bcd(hours),
            int2bcd(minutes),
            int2bcd(days),
            int2bcd(day),
            int2bcd(month),
            int2bcd(year),
            int(obj.get("giorni_scadenza_sim", 0)),
            int(obj.get("giorni_credito_minimo", 0)),
            int(obj.get("credito_minimo", 0))
        ]
    except Exception as e:
        _LOGGER.error(f"Error in j2bGsm: {e}")
        return []


def j2bOpzioni(obj: Dict[str, bool]) -> List[int]:
    """Convert opzioni JSON to bytes."""
    try:
        arr = []
        
        # First byte
        byte1 = 0
        if obj.get("toni_ins"):
            byte1 |= 1
        if obj.get("toni_ingr"):
            byte1 |= 2
        if obj.get("led_on"):
            byte1 |= 4
        if obj.get("autoreset"):
            byte1 |= 8
        if obj.get("rit_no_rete"):
            byte1 |= 16
        if obj.get("all_falsa_chiave"):
            byte1 |= 32
        if obj.get("chiave_base"):
            byte1 |= 64
        if obj.get("buzzer"):
            byte1 |= 128
        arr.append(byte1)
        
        # Second byte
        byte2 = 0
        if obj.get("abil_campanello"):
            byte2 |= 1
        if obj.get("abil_asterisco"):
            byte2 |= 2
        if obj.get("des"):
            byte2 |= 4
        if obj.get("inversione"):
            byte2 |= 8
        if obj.get("antimask"):
            byte2 |= 16
        if obj.get("supervisione"):
            byte2 |= 32
        arr.append(byte2)
        
        return arr
    except Exception as e:
        _LOGGER.error(f"Error in j2bOpzioni: {e}")
        return [0, 0]


def j2bSupertasti(obj: Dict[str, bool]) -> List[int]:
    """Convert supertasti JSON to bytes."""
    try:
        value = 0
        if obj.get("supertasto1"):
            value |= 2
        if obj.get("supertasto2"):
            value |= 4
        if obj.get("supertasto3"):
            value |= 8
        if obj.get("supertasto4"):
            value |= 16
        return [value]
    except Exception as e:
        _LOGGER.error(f"Error in j2bSupertasti: {e}")
        return [0]


def j2bTel(obj: Dict[str, Any]) -> List[int]:
    """Convert telephone configuration JSON to bytes."""
    try:
        numero = string_to_array_int(16, obj.get("numero", ""))
        nome = string_to_array_int(16, obj.get("nome", ""))
        opzioni = []
        
        # First option byte
        byte1 = int(obj.get("ripetizioni", 0)) & 15
        if obj.get("sms_credito_scadenza"):
            byte1 |= 16
        if obj.get("abilitazione"):
            byte1 |= 32
        opzioni.append(byte1)
        
        # Second option byte
        byte2 = 0
        if obj.get("vocale_a"):
            byte2 |= 1
        if obj.get("vocale_k"):
            byte2 |= 2
        if obj.get("vocale_sabotaggio"):
            byte2 |= 4
        if obj.get("vocale_silenzioso"):
            byte2 |= 8
        if obj.get("sms_a"):
            byte2 |= 16
        if obj.get("sms_k"):
            byte2 |= 32
        if obj.get("sms_sabotaggio"):
            byte2 |= 64
        if obj.get("sms_silenzioso"):
            byte2 |= 128
        opzioni.append(byte2)
        
        # Third option byte
        byte3 = 0
        if obj.get("sms_batteria_centrale_carica"):
            byte3 |= 1
        if obj.get("sms_batteria_radio_carica"):
            byte3 |= 2
        if obj.get("sms_rete_elettrica_assente"):
            byte3 |= 4
        if obj.get("sms_rete_elettrica_ripristinata"):
            byte3 |= 8
        if obj.get("sms_variazione_programmi"):
            byte3 |= 16
        if obj.get("sms_accesso_sistema"):
            byte3 |= 32
        opzioni.append(byte3)
        
        # Fourth option byte
        byte4 = 0
        if obj.get("squillo_esistenza_vita"):
            byte4 |= 1
        if obj.get("sms_esistenza_vita"):
            byte4 |= 2
        if obj.get("squillo_conferma_uscite"):
            byte4 |= 4
        if obj.get("sms_conferma_uscite"):
            byte4 |= 8
        if obj.get("vocale_conferma_uscite"):
            byte4 |= 16
        if obj.get("apri_cancello_na"):
            byte4 |= 32
        if obj.get("apri_cancello_out1"):
            byte4 |= 64
        if obj.get("impulsato"):
            byte4 |= 128
        opzioni.append(byte4)
        
        opzioni.append(int(obj.get("durata_impulso", 0)))
        
        return numero + opzioni + nome
    except Exception as e:
        _LOGGER.error(f"Error in j2bTel: {e}")
        return []


def j2bTempi(obj: Dict[str, int]) -> List[int]:
    """Convert tempi JSON to bytes."""
    try:
        allarme = int(obj.get("allarme", 0))
        ronda = int(obj.get("ronda", 0))
        
        return [
            (allarme >> 8) & 0xFF,
            allarme & 0xFF,
            int(obj.get("fuoco", 0)),
            int(obj.get("silenzioso", 0)) * 2,
            int(obj.get("campanello", 0)) * 2,
            int(obj.get("elettroserratura", 0)) * 2,
            (ronda >> 8) & 0xFF,
            ronda & 0xFF
        ]
    except Exception as e:
        _LOGGER.error(f"Error in j2bTempi: {e}")
        return [0] * 8


def j2bUscite(data: Dict[str, Dict[str, Any]]) -> List[int]:
    """Convert uscite JSON to bytes."""
    try:
        def j2bUscita(obj: Dict[str, Any]) -> int:
            value = int(obj.get("attributo", 0))
            if obj.get("polarita") != "normale":
                value |= 128
            return value
        
        return [
            j2bUscita(data.get("uscita4", {})),
            j2bUscita(data.get("uscita0", {})),
            j2bUscita(data.get("uscita1", {})),
            j2bUscita(data.get("uscita2", {})),
            j2bUscita(data.get("uscita3", {}))
        ]
    except Exception as e:
        _LOGGER.error(f"Error in j2bUscite: {e}")
        return [0] * 5


def j2bRadio(obj: Dict[str, Any]) -> List[int]:
    """Convert radio device JSON to bytes."""
    try:
        arr = []
        
        # First byte - attributes
        byte1 = 0
        if obj.get("test"):
            byte1 |= 1
        if obj.get("escluso"):
            byte1 |= 2
        if obj.get("ronda"):
            byte1 |= 4
        if obj.get("fuoco"):
            byte1 |= 8
        if obj.get("campanello"):
            byte1 |= 16
        if obj.get("silenzioso"):
            byte1 |= 32
        if obj.get("elettroserratura"):
            byte1 |= 64
        if obj.get("parzializzabile"):
            byte1 |= 128
        arr.append(byte1)
        
        # Second byte - depends on device type
        byte2 = 0
        if obj.get("num_tipo_periferica") == 5 and obj.get("antintrusione") is not None:
            # Uscita
            byte2 = int(obj.get("antintrusione", 0)) & 0x7F
        else:
            if obj.get("g1"):
                byte2 |= 1
            if obj.get("g2"):
                byte2 |= 2
            if obj.get("g3"):
                byte2 |= 4
            if obj.get("a"):
                byte2 |= 8
            if obj.get("k"):
                byte2 |= 16
            if obj.get("ritardato"):
                byte2 |= 32
            if obj.get("percorso"):
                byte2 |= 64
            if obj.get("sempre_attivo"):
                byte2 |= 128
        arr.append(byte2)
        
        # Third byte - device specific
        byte3 = 0
        device_type = obj.get("num_tipo_periferica", 0)
        
        if device_type == 2:  # movimento
            if obj.get("supervisione"):
                byte3 |= 1
            if obj.get("led_on"):
                byte3 |= 2
            byte3 |= int(obj.get("aux1", 0))
            if int(obj.get("logica", 0)) == 0:
                byte3 |= int(obj.get("cd_cs", 0))
            byte3 |= int(obj.get("logica", 0))
            byte3 |= int(obj.get("conf", 0))
            if obj.get("num_spec_periferica") == 3:
                if obj.get("reed"):
                    byte3 |= 4
                if obj.get("prog"):
                    byte3 |= 32
                    
        # Add other device types as in JS...
        # (Similar logic for types 3, 4, 5, 6, 8)
        
        arr.append(byte3)
        
        # Add remaining fields
        arr.append(int(obj.get("tempo_ingresso", 0)))
        arr.append(int(obj.get("tempo_uscita", 0)))
        arr.append(int(obj.get("cicli_autoesclusione", 0)))
        
        indirizzo = int(obj.get("indirizzo_periferica", 0))
        arr.append(indirizzo & 0xFF)
        arr.append((indirizzo >> 8) & 0xFF)
        
        arr.append(int(obj.get("num_tipo_periferica", 0)))
        arr.append(int(obj.get("num_spec_periferica", 0)))
        arr.append(int(obj.get("mw", 0)))
        arr.append(int(obj.get("pir1", 0)))
        arr.append(int(obj.get("pir2", 0)))
        arr.append(int(obj.get("am", 0)))
        
        arr.extend(string_to_array_int(16, obj.get("nome", "")))
        
        return arr
    except Exception as e:
        _LOGGER.error(f"Error in j2bRadio: {e}")
        return []


class GoldConverter:
    """Converter class for Gold commands."""
    
    def __init__(self):
        """Initialize converter."""
        _LOGGER.debug("GoldConverter initialized")
    
    def convert_to_bytes(self, command_type: str, data: Any) -> List[int]:
        """
        Convert command to bytes based on type.
        
        Args:
            command_type: Type of command to convert
            data: Data to convert
            
        Returns:
            Byte array for command
        """
        try:
            converters = {
                "autoins": j2bAutoIns,
                "bus": j2bBus,
                "codice": j2bCodice,
                "chiave": j2bChiave,
                "filare": j2bFilare,
                "gsm": j2bGsm,
                "opzioni": j2bOpzioni,
                "supertasti": j2bSupertasti,
                "tel": j2bTel,
                "tempi": j2bTempi,
                "uscite": j2bUscite,
                "radio": j2bRadio
            }
            
            converter = converters.get(command_type.lower())
            if converter:
                result = converter(data)
                _LOGGER.debug(f"Converted {command_type}: {result}")
                return result
            else:
                _LOGGER.warning(f"No converter for command type: {command_type}")
                return []
                
        except Exception as e:
            _LOGGER.error(f"Error converting {command_type}: {e}")
            return []
        
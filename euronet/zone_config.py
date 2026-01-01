"""
Zone configuration retrieval for EuroNET local mode.

This module handles scraping zone names and configurations from the EuroNET
web interface pages (ingresso-filari.html and ingresso-radio.html).

Requires installer login to access configuration pages.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import aiohttp
import asyncio

_LOGGER = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ZoneFilareConfig:
    """Configuration for a wired zone (ingresso filare)."""
    numero: int
    nome: str
    tipo: int  # 0=NC, 1=Bilanciato, 2=Doppio Bilanciato
    tipo_label: str
    programmi: Dict[str, bool] = field(default_factory=dict)  # G1, G2, G3, GExt
    
    # Timing parameters
    trigger: int = 0  # 0=300ms, 1=600ms
    trigger_label: str = "300ms"
    tempo_ingresso_min: int = 0  # 0-4 minutes
    tempo_ingresso_sec: int = 0  # 0-59 seconds
    tempo_uscita_min: int = 0  # 0-4 minutes
    tempo_uscita_sec: int = 0  # 0-59 seconds
    
    # Logic and alarms
    logica: int = 0  # 0=AND, 1=OR
    logica_label: str = "AND"
    numero_allarmi: int = 0  # 0=Infiniti, 1-15
    numero_allarmi_label: str = "Infiniti"
    
    # Zone options (checkboxes)
    escluso: bool = False
    silenzioso: bool = False
    test: bool = False
    parzializzabile: bool = False
    ronda: bool = False
    h24: bool = False
    ritardato: bool = False
    percorso: bool = False
    
    # Output associations
    uscita_a: bool = False  # A (allarme 1)
    uscita_k: bool = False  # K (allarme 2)
    fuoco: bool = False
    campanello: bool = False
    elettroserratura: bool = False
    
    @property
    def tempo_ingresso_totale(self) -> int:
        """Total entry time in seconds."""
        return self.tempo_ingresso_min * 60 + self.tempo_ingresso_sec
    
    @property
    def tempo_uscita_totale(self) -> int:
        """Total exit time in seconds."""
        return self.tempo_uscita_min * 60 + self.tempo_uscita_sec
    
    @property
    def is_configured(self) -> bool:
        """Check if zone has a custom name (not default INGRESSO XX)."""
        return not self.nome.upper().startswith("INGRESSO")


@dataclass
class ZoneRadioConfig:
    """Configuration for a radio zone (ingresso radio)."""
    numero: int
    nome: str
    supervisionato: bool = False
    escluso: bool = True
    
    # Associazioni a ingressi filari (checkbox a1_r to a5_r)
    # Ogni checkbox corrisponde a un ingresso filare specifico
    associazione_26_31: bool = False  # a1_r - Ingresso filare 26/31
    associazione_27_32: bool = False  # a2_r - Ingresso filare 27/32
    associazione_28_33: bool = False  # a3_r - Ingresso filare 28/33
    associazione_29_34: bool = False  # a4_r - Ingresso filare 29/34
    associazione_30_35: bool = False  # a5_r - Ingresso filare 30/35
    
    @property
    def associazioni_filari(self) -> List[str]:
        """Return list of associated wired zones as descriptive strings."""
        associazioni = []
        if self.associazione_26_31:
            associazioni.append("26/31")
        if self.associazione_27_32:
            associazioni.append("27/32")
        if self.associazione_28_33:
            associazioni.append("28/33")
        if self.associazione_29_34:
            associazioni.append("29/34")
        if self.associazione_30_35:
            associazioni.append("30/35")
        return associazioni
    
    @property
    def is_configured(self) -> bool:
        """Check if zone is configured (not 'Non Disponibile')."""
        return bool(self.nome) and "non disponibile" not in self.nome.lower()


@dataclass
class ZoneConfigs:
    """Container for all zone configurations."""
    zone_filari: Dict[int, ZoneFilareConfig] = field(default_factory=dict)
    zone_radio: Dict[int, ZoneRadioConfig] = field(default_factory=dict)
    timestamp: float = 0.0
    
    @property
    def zone_filari_configurate(self) -> Dict[int, ZoneFilareConfig]:
        """Return only configured wired zones (with custom names)."""
        return {k: v for k, v in self.zone_filari.items() if v.is_configured}
    
    @property
    def zone_radio_configurate(self) -> Dict[int, ZoneRadioConfig]:
        """Return only configured radio zones."""
        return {k: v for k, v in self.zone_radio.items() if v.is_configured}


# ============================================================================
# TIPO CONTATTO MAPPING
# ============================================================================

TIPO_CONTATTO = {
    0: "NC",
    1: "Bilanciato",
    2: "Doppio Bilanciato",
}

TRIGGER_TIME = {
    0: "300ms",
    1: "600ms",
}

LOGICA = {
    0: "AND",
    1: "OR",
}

NUMERO_ALLARMI = {
    0: "Infiniti",
    **{i: str(i) for i in range(1, 16)}
}


# ============================================================================
# XOR ENCODING
# ============================================================================

def encode_euronet_password(code: str, keys: List[int]) -> str:
    """
    Encode password/code for EuroNET using XOR.
    
    Args:
        code: Numeric code (max 6 digits)
        keys: XOR keys from index.htm
        
    Returns:
        Encoded string of 18 characters
    """
    result = ""
    for i in range(6):
        if i < len(code):
            char_code = ord(code[i])
        else:
            char_code = 245 + i  # Padding
        xored = char_code ^ keys[i]
        result += str(xored).zfill(3)
    return result


# ============================================================================
# ZONE CONFIG FETCHER
# ============================================================================

class ZoneConfigFetcher:
    """Fetches zone configurations from EuroNET web interface."""
    
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        installer_code: str,
        num_zone_filari: int = 10,
        num_zone_radio: int = 0,
        timeout: int = 10,
    ):
        """
        Initialize the zone config fetcher.
        
        Args:
            host: EuroNET IP address
            username: HTTP Basic Auth username
            password: HTTP Basic Auth password
            installer_code: Installer code for accessing config pages
            num_zone_filari: Number of wired zones to fetch (1-35)
            num_zone_radio: Number of radio zones to fetch (0-64)
            timeout: Request timeout in seconds
        """
        self.host = host
        self.username = username
        self.password = password
        self.installer_code = installer_code
        self.num_zone_filari = min(num_zone_filari, 35)
        self.num_zone_radio = min(num_zone_radio, 64)
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.base_url = f"http://{host}"
        self._session: Optional[aiohttp.ClientSession] = None
        self._logged_in = False
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with basic auth."""
        if self._session is None or self._session.closed:
            auth = aiohttp.BasicAuth(self.username, self.password)
            self._session = aiohttp.ClientSession(
                auth=auth,
                timeout=self.timeout,
            )
        return self._session
    
    async def _logout(self, force: bool = True):
        """
        Logout from EuroNET web interface.
        
        Args:
            force: Se True, forza il logout anche di altri utenti
        """
        if self._session and not self._session.closed:
            try:
                if force:
                    # Force logout - disconnette qualsiasi utente collegato
                    async with self._session.post(
                        f"{self.base_url}/NoLogin.html",
                        data="Login=force",
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    ) as response:
                        _LOGGER.debug("Force logout response: %s", response.status)
                
                # Logout normale
                async with self._session.get(f"{self.base_url}/logout.html?logout") as response:
                    _LOGGER.debug("Logout response: %s", response.status)
                
                self._logged_in = False
            except Exception as e:
                _LOGGER.debug("Logout error (ignored): %s", e)
    
    async def close(self):
        """Logout and close the session."""
        # Prima fai logout dall'interfaccia EuroNET
        await self._logout(force=True)
        # Poi chiudi la sessione HTTP
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def _get_xor_keys(self, session: aiohttp.ClientSession) -> Optional[List[int]]:
        """
        Extract dynamic XOR keys from index.htm.
        
        The server generates new keys for each request.
        Keys are in JavaScript: arr = "142,136,156,115,..."
        """
        try:
            async with session.get(f"{self.base_url}/index.htm") as response:
                if response.status != 200:
                    _LOGGER.error("Failed to get index.htm: %s", response.status)
                    return None
                
                html = await response.text(encoding='latin-1')
                match = re.search(r'arr\s*=\s*"([\d,]+)"', html)
                if not match:
                    return None
                
                keys = [int(k) for k in match.group(1).strip(',').split(',') if k]
                if len(keys) < 16:
                    return None
                
                return keys[:16]
                
        except Exception as e:
            _LOGGER.debug("Error extracting XOR keys: %s", e)
            return None
    
    async def _login_installer(self, session: aiohttp.ClientSession) -> bool:
        """
        Login with installer code to access configuration pages.
        
        Returns True if login successful.
        """
        try:
            # Get dynamic XOR keys
            keys = await self._get_xor_keys(session)
            if not keys:
                return False
            
            # Encode installer code
            encoded = encode_euronet_password(self.installer_code, keys)
            _LOGGER.debug("Logging in with encoded installer code")
            
            # Send login request
            async with session.post(
                f"{self.base_url}/login.html",
                data=f"psw={encoded}",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status != 200:
                    _LOGGER.error("Login failed: %s", response.status)
                    return False
            
            # Wait for session to stabilize (EuroNET needs time to process login)
            await asyncio.sleep(0.5)
            
            self._logged_in = True
            _LOGGER.debug("Installer login successful")
            return True
            
        except Exception as e:
            _LOGGER.error("Login error: %s", e)
            return False
    
    async def _fetch_zone_filare(
        self,
        session: aiohttp.ClientSession,
        numero: int,
    ) -> Optional[ZoneFilareConfig]:
        """
        Fetch configuration for a single wired zone.
        
        Args:
            session: aiohttp session
            numero: Zone number (1-35)
            
        Returns:
            ZoneFilareConfig or None if error
        """
        try:
            async with session.get(
                f"{self.base_url}/ingresso-filari.html?{numero}"
            ) as response:
                if response.status != 200:
                    _LOGGER.warning("Failed to fetch zone %d: %s", numero, response.status)
                    return None
                
                html = await response.text(encoding='latin-1')
                
                # Check if it's a loading page (not logged in)
                if "In attesa" in html:
                    _LOGGER.warning("Got loading page for zone %d - not logged in?", numero)
                    return None
                
                return self._parse_zone_filare(html, numero)
                
        except Exception as e:
            _LOGGER.error("Error fetching zone %d: %s", numero, e)
            return None
    
    def _parse_zone_filare(self, html: str, numero: int) -> Optional[ZoneFilareConfig]:
        """Parse HTML to extract wired zone configuration."""
        try:
            # Helper function to extract select value
            def get_select_value(name: str) -> tuple[int, str]:
                match = re.search(rf'<select[^>]*name="{name}"[^>]*>(.*?)</select>', html, re.DOTALL | re.IGNORECASE)
                if match:
                    sel_match = re.search(r'<option\s+value="(\d+)"[^>]*selected[^>]*>([^<]+)</option>', 
                                         match.group(1), re.IGNORECASE)
                    if sel_match:
                        return int(sel_match.group(1)), sel_match.group(2).strip()
                return 0, ""
            
            # Helper function to check checkbox
            def is_checked(name: str) -> bool:
                match = re.search(rf'<input[^>]*name="{name}"[^>]*>', html, re.IGNORECASE)
                return match is not None and "checked" in match.group(0).lower()
            
            # Extract zone name from input nom_i
            nome = ""
            match_nome = re.search(r'<input[^>]*name="nom_i"[^>]*value="([^"]*)"', html, re.IGNORECASE)
            if match_nome:
                nome = match_nome.group(1).strip()
            
            # If no nome found, try to get from select option
            if not nome:
                match_select = re.search(r'<select[^>]*id="num_in"[^>]*>(.*?)</select>', html, re.DOTALL | re.IGNORECASE)
                if match_select:
                    match_opt = re.search(rf'<option\s+value="{numero}"[^>]*selected[^>]*>([^<]+)</option>', 
                                         match_select.group(1), re.IGNORECASE)
                    if match_opt:
                        opt_text = match_opt.group(1).strip()
                        if " - " in opt_text:
                            nome = opt_text.split(" - ", 1)[1].strip()
            
            if not nome:
                nome = f"INGRESSO {numero}"
            
            # Extract tipo (contact type): 0=NC, 1=Bilanciato, 2=Doppio Bilanciato
            tipo, tipo_label = get_select_value("tipo")
            if not tipo_label:
                tipo_label = TIPO_CONTATTO.get(tipo, "NC")
            
            # Extract trigger time: 0=300ms, 1=600ms
            trigger, trigger_label = get_select_value("Trig")
            if not trigger_label:
                trigger_label = TRIGGER_TIME.get(trigger, "300ms")
            
            # Extract logica: 0=AND, 1=OR
            logica, logica_label = get_select_value("Log")
            if not logica_label:
                logica_label = LOGICA.get(logica, "AND")
            
            # Extract numero allarmi: 0=Infiniti, 1-15
            numero_allarmi, numero_allarmi_label = get_select_value("NMA")
            if not numero_allarmi_label:
                numero_allarmi_label = NUMERO_ALLARMI.get(numero_allarmi, "Infiniti")
            
            # Extract tempo ingresso (entry time)
            tempo_ingresso_min, _ = get_select_value("t_inM")
            tempo_ingresso_sec, _ = get_select_value("t_inS")
            
            # Extract tempo uscita (exit time)
            tempo_uscita_min, _ = get_select_value("t_ouM")
            tempo_uscita_sec, _ = get_select_value("t_ouS")
            
            # Extract programmi (G1, G2, G3, GExt)
            programmi = {
                "G1": is_checked("G1_i"),
                "G2": is_checked("G2_i"),
                "G3": is_checked("G3_i"),
                "GExt": is_checked("Ge_i"),
            }
            
            # Extract zone options (checkboxes)
            escluso = is_checked("esc_i")
            silenzioso = is_checked("sil_i")
            test = is_checked("tes_i")
            parzializzabile = is_checked("par_i")
            ronda = is_checked("ron_i")
            h24 = is_checked("h24_i")
            ritardato = is_checked("rit_i")
            percorso = is_checked("per_i")
            
            # Extract output associations
            uscita_a = is_checked("A_i")
            uscita_k = is_checked("K_i")
            fuoco = is_checked("F_i")
            campanello = is_checked("C_i")
            elettroserratura = is_checked("E_i")
            
            return ZoneFilareConfig(
                numero=numero,
                nome=nome,
                tipo=tipo,
                tipo_label=tipo_label,
                programmi=programmi,
                trigger=trigger,
                trigger_label=trigger_label,
                tempo_ingresso_min=tempo_ingresso_min,
                tempo_ingresso_sec=tempo_ingresso_sec,
                tempo_uscita_min=tempo_uscita_min,
                tempo_uscita_sec=tempo_uscita_sec,
                logica=logica,
                logica_label=logica_label,
                numero_allarmi=numero_allarmi,
                numero_allarmi_label=numero_allarmi_label,
                escluso=escluso,
                silenzioso=silenzioso,
                test=test,
                parzializzabile=parzializzabile,
                ronda=ronda,
                h24=h24,
                ritardato=ritardato,
                percorso=percorso,
                uscita_a=uscita_a,
                uscita_k=uscita_k,
                fuoco=fuoco,
                campanello=campanello,
                elettroserratura=elettroserratura,
            )
            
        except Exception as e:
            _LOGGER.error("Error parsing zone %d: %s", numero, e)
            return None
    
    async def _fetch_zone_radio(
        self,
        session: aiohttp.ClientSession,
        numero: int,
    ) -> Optional[ZoneRadioConfig]:
        """
        Fetch configuration for a single radio zone.
        
        Args:
            session: aiohttp session
            numero: Zone number (1-64)
            
        Returns:
            ZoneRadioConfig or None if error
        """
        try:
            async with session.get(
                f"{self.base_url}/ingresso-radio.html?{numero}"
            ) as response:
                if response.status != 200:
                    _LOGGER.warning("Failed to fetch radio zone %d: %s", numero, response.status)
                    return None
                
                html = await response.text(encoding='latin-1')
                
                # Check if it's a loading page
                if "In attesa" in html:
                    _LOGGER.warning("Got loading page for radio zone %d", numero)
                    return None
                
                return self._parse_zone_radio(html, numero)
                
        except Exception as e:
            _LOGGER.error("Error fetching radio zone %d: %s", numero, e)
            return None
    
    def _parse_zone_radio(self, html: str, numero: int) -> Optional[ZoneRadioConfig]:
        """Parse HTML to extract radio zone configuration."""
        try:
            # Helper function to check checkbox
            def is_checked(name: str) -> bool:
                match = re.search(rf'<input[^>]*name="{name}"[^>]*>', html, re.IGNORECASE)
                return match is not None and "checked" in match.group(0).lower()
            
            # Extract zone name from input nom_r
            nome = ""
            match_nome = re.search(r'<input[^>]*name="nom_r"[^>]*value="([^"]*)"', html, re.IGNORECASE)
            if match_nome:
                nome = match_nome.group(1).strip()
            
            # If no nome found, try to get from select option
            if not nome:
                match_select = re.search(r'<select[^>]*id="num_r"[^>]*>(.*?)</select>', html, re.DOTALL | re.IGNORECASE)
                if match_select:
                    match_opt = re.search(rf'<option\s+value="{numero}"[^>]*selected[^>]*>([^<]+)</option>', 
                                         match_select.group(1), re.IGNORECASE)
                    if match_opt:
                        opt_text = match_opt.group(1).strip()
                        if " - " in opt_text:
                            nome = opt_text.split(" - ", 1)[1].strip()
            
            if not nome:
                nome = "Non Disponibile"
            
            # Extract checkboxes
            supervisionato = is_checked("sup_r")
            escluso = is_checked("esc_r")
            
            # Extract associazioni filari (a1_r to a5_r)
            associazione_26_31 = is_checked("a1_r")
            associazione_27_32 = is_checked("a2_r")
            associazione_28_33 = is_checked("a3_r")
            associazione_29_34 = is_checked("a4_r")
            associazione_30_35 = is_checked("a5_r")
            
            return ZoneRadioConfig(
                numero=numero,
                nome=nome,
                supervisionato=supervisionato,
                escluso=escluso,
                associazione_26_31=associazione_26_31,
                associazione_27_32=associazione_27_32,
                associazione_28_33=associazione_28_33,
                associazione_29_34=associazione_29_34,
                associazione_30_35=associazione_30_35,
            )
            
        except Exception as e:
            _LOGGER.error("Error parsing radio zone %d: %s", numero, e)
            return None
    
    async def fetch_all_zones(self, max_retries: int = 3) -> ZoneConfigs:
        """
        Fetch all zone configurations (wired and radio).
        
        This performs installer login, then fetches each zone's configuration
        by scraping the web pages. If a zone fails to load (e.g. "In attesa" page),
        it will retry up to max_retries times with a fresh login.
        
        Args:
            max_retries: Maximum number of retry attempts for failed zones
        
        Returns:
            ZoneConfigs with all zone configurations
        """
        configs = ZoneConfigs(timestamp=time.time())
        
        # Track zones that need fetching
        pending_filari = set(range(1, self.num_zone_filari + 1))
        pending_radio = set(range(1, self.num_zone_radio + 1)) if self.num_zone_radio > 0 else set()
        
        for attempt in range(max_retries + 1):
            if not pending_filari and not pending_radio:
                break  # All zones fetched successfully
                
            if attempt > 0:
                _LOGGER.info(
                    "Retry attempt %d/%d for %d wired and %d radio zones",
                    attempt, max_retries, len(pending_filari), len(pending_radio)
                )
                # Close previous session and wait before retry
                await self.close()
                await asyncio.sleep(1.0)
            
            try:
                session = await self._get_session()
                
                # Login with installer code
                if not await self._login_installer(session):
                    _LOGGER.error("Failed to login as installer (attempt %d)", attempt + 1)
                    continue  # Try again with new session
                
                # Wait after login to let the device stabilize
                await asyncio.sleep(0.5)
                
                # Fetch wired zones that are still pending
                if pending_filari:
                    if attempt == 0:
                        _LOGGER.info("Fetching %d wired zone configurations...", self.num_zone_filari)
                    
                    failed_filari = set()
                    # Fetch in reverse order - lower zones seem to fail more often initially
                    for i in sorted(pending_filari, reverse=True):
                        zone_config = await self._fetch_zone_filare(session, i)
                        if zone_config:
                            configs.zone_filari[i] = zone_config
                            _LOGGER.debug("Zone %d: %s (%s)", i, zone_config.nome, zone_config.tipo_label)
                        else:
                            failed_filari.add(i)
                        # Delay between requests to avoid overwhelming the device
                        await asyncio.sleep(0.2)
                    
                    pending_filari = failed_filari
                
                # Fetch radio zones that are still pending
                if pending_radio:
                    if attempt == 0:
                        _LOGGER.info("Fetching %d radio zone configurations...", self.num_zone_radio)
                    
                    failed_radio = set()
                    for i in list(pending_radio):
                        zone_config = await self._fetch_zone_radio(session, i)
                        if zone_config:
                            configs.zone_radio[i] = zone_config
                            _LOGGER.debug("Radio zone %d: %s", i, zone_config.nome)
                        else:
                            failed_radio.add(i)
                        await asyncio.sleep(0.1)
                    
                    pending_radio = failed_radio
                
            except Exception as e:
                _LOGGER.error("Error fetching zone configs (attempt %d): %s", attempt + 1, e)
        
        # Log final results
        if pending_filari or pending_radio:
            _LOGGER.debug(
                "Could not fetch all zones after %d attempts. Missing: %d wired, %d radio",
                max_retries + 1, len(pending_filari), len(pending_radio)
            )
        
        _LOGGER.debug(
            "Fetched %d wired zones (%d configured) and %d radio zones (%d configured)",
            len(configs.zone_filari),
            len(configs.zone_filari_configurate),
            len(configs.zone_radio),
            len(configs.zone_radio_configurate),
        )
        
        # Close session
        await self.close()
        
        return configs
    
    async def fetch_zone_names_only(self) -> Dict[str, Dict[int, str]]:
        """
        Fetch only zone names (faster, single page per type).
        
        Returns dict with 'filari' and 'radio' keys, each containing
        {zone_number: zone_name} mappings.
        """
        result = {"filari": {}, "radio": {}}
        
        try:
            session = await self._get_session()
            
            # Login
            if not await self._login_installer(session):
                return result
            
            # Fetch first wired zone page - contains all names in select
            async with session.get(f"{self.base_url}/ingresso-filari.html?1") as response:
                if response.status == 200:
                    html = await response.text(encoding='latin-1')
                    if "In attesa" not in html:
                        match_select = re.search(
                            r'<select[^>]*id="num_in"[^>]*>(.*?)</select>',
                            html, re.DOTALL | re.IGNORECASE
                        )
                        if match_select:
                            options = re.findall(
                                r'<option\s+value="(\d+)"[^>]*>([^<]+)</option>',
                                match_select.group(1), re.IGNORECASE
                            )
                            for val, text in options:
                                num = int(val)
                                if num <= self.num_zone_filari:
                                    # Extract name after "XX - "
                                    if " - " in text:
                                        name = text.split(" - ", 1)[1].strip()
                                    else:
                                        name = text.strip()
                                    result["filari"][num] = name
            
            # Fetch first radio zone page - contains all names in select
            if self.num_zone_radio > 0:
                async with session.get(f"{self.base_url}/ingresso-radio.html?1") as response:
                    if response.status == 200:
                        html = await response.text(encoding='latin-1')
                        if "In attesa" not in html:
                            match_select = re.search(
                                r'<select[^>]*id="num_r"[^>]*>(.*?)</select>',
                                html, re.DOTALL | re.IGNORECASE
                            )
                            if match_select:
                                options = re.findall(
                                    r'<option\s+value="(\d+)"[^>]*>([^<]+)</option>',
                                    match_select.group(1), re.IGNORECASE
                                )
                                for val, text in options:
                                    num = int(val)
                                    if num <= self.num_zone_radio:
                                        if " - " in text:
                                            name = text.split(" - ", 1)[1].strip()
                                        else:
                                            name = text.strip()
                                        result["radio"][num] = name
            
        except Exception as e:
            _LOGGER.error("Error fetching zone names: %s", e)
        finally:
            await self.close()
        
        return result


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def get_zone_configs(
    host: str,
    username: str,
    password: str,
    installer_code: str,
    num_zone_filari: int = 10,
    num_zone_radio: int = 0,
) -> ZoneConfigs:
    """
    Convenience function to fetch all zone configurations.
    
    Args:
        host: EuroNET IP address
        username: HTTP Basic Auth username
        password: HTTP Basic Auth password
        installer_code: Installer code
        num_zone_filari: Number of wired zones
        num_zone_radio: Number of radio zones
        
    Returns:
        ZoneConfigs with all configurations
    """
    fetcher = ZoneConfigFetcher(
        host=host,
        username=username,
        password=password,
        installer_code=installer_code,
        num_zone_filari=num_zone_filari,
        num_zone_radio=num_zone_radio,
    )
    return await fetcher.fetch_all_zones()


async def get_zone_names(
    host: str,
    username: str,
    password: str,
    installer_code: str,
    num_zone_filari: int = 10,
    num_zone_radio: int = 0,
) -> Dict[str, Dict[int, str]]:
    """
    Convenience function to fetch only zone names (faster).
    
    Returns dict with 'filari' and 'radio' keys.
    """
    fetcher = ZoneConfigFetcher(
        host=host,
        username=username,
        password=password,
        installer_code=installer_code,
        num_zone_filari=num_zone_filari,
        num_zone_radio=num_zone_radio,
    )
    return await fetcher.fetch_zone_names_only()

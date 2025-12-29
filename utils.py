import aiohttp
import os
import logging

from homeassistant.core import HomeAssistant
from .const import DOMAIN
from typing import Optional, Dict, Any, List
from datetime import datetime

_LOGGER = logging.getLogger(__name__)

async def ensure_device_icon_exists(hass: HomeAssistant, model: str, icon_url: str) -> str:
    """Scarica l'immagine del modello se non è già presente."""
    local_icons_path = hass.config.path("www", DOMAIN, "icons")
    os.makedirs(local_icons_path, exist_ok=True)

    filename = f"{model}.png"
    file_path = os.path.join(local_icons_path, filename)

    if not os.path.isfile(file_path):
        try:
            session = aiohttp.ClientSession()
            async with session.get(icon_url, ssl=False) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    with open(file_path, "wb") as f:
                        f.write(content)
                    _LOGGER.info(f"Scaricata icona per modello {model}")
                else:
                    _LOGGER.warning(f"Errore HTTP {resp.status} durante il download dell'icona per {model}")
            await session.close()
        except Exception as e:
            _LOGGER.warning(f"Impossibile scaricare icona per {model}: {e}")

    return f"{file_path}"    

def prima_lettera_maiuscola(s):
    s = s.strip()
    if not s:
        return ""
    return s[0].upper() + s[1:].lower()

def convert_zone_attributes(zone_type, zone_state):
    """Converte gli attributi della zona da formato parser a formato più leggibile."""
    attributes = {}
    if zone_type == "filare":
        attributes['Ingresso Aperto'] = zone_state['filari_oi']
        attributes['Ingresso Escluso'] = zone_state['filari_esclusioni']
        attributes['Memoria Allarme'] = zone_state['filari_memorie']
        attributes['Allarme 24h'] = zone_state['filari_oi24']
        attributes['Memoria 24h'] = zone_state['filari_memorie24']
    else:
        attributes['Allarme 24h'] = zone_state['as_radio']
        attributes['Memoria 24h'] = zone_state['mem_as_radio']
        attributes['Ingresso Allarme'] = zone_state['oi_radio']
        attributes['Memoria Allarme'] = zone_state['mem_oi_radio']
        attributes['Supervisione'] = zone_state['supervisioni_radio']
        attributes['Batteria'] = zone_state['lo_batt_radio']
    return attributes

def is_notifications_enabled(hass, centrale_id: Optional[Any] = None) -> bool:
    """
    Controlla se le notifiche sono abilitate per una centrale specifica o globalmente.
    
    Args:
        hass: Home Assistant instance
        centrale_id: ID della centrale (int per cloud, str/host per locale)
        
    Returns:
        bool: True se le notifiche sono abilitate
    """
    if DOMAIN not in hass.data:
        return True  # Default: abilitate
    
    notifications_settings = hass.data[DOMAIN].get("notifications_enabled", {})
    
    if centrale_id is not None:
        # Controlla per centrale specifica
        result = notifications_settings.get(centrale_id, True)
        _LOGGER.debug(f"Notifiche per centrale {centrale_id}: {result}")
        return result
    
    # Se non specificata la centrale, controlla se almeno una è abilitata
    # o ritorna True se il dizionario è vuoto (nessuna configurazione = tutto abilitato)
    if len(notifications_settings) == 0:
        return True
    
    return any(notifications_settings.values())

async def send_persistent_notification(
    hass,
    message: str,
    title: str = "Notifica",
    notification_id: Optional[str] = None,
    centrale_id: Optional[int] = None,
    force: bool = False,
    **kwargs
) -> str:
    """
    Invia una notifica persistente in Home Assistant.
    
    Args:
        hass: Istanza di Home Assistant
        message: Messaggio della notifica
        title: Titolo della notifica
        notification_id: ID univoco per la notifica (generato se None)
        **kwargs: Parametri aggiuntivi supportati dal servizio
        
    Returns:
        str: L'ID della notifica creata, stringa vuota se fallisce
    """

    # Controlla se le notifiche sono abilitate (a meno che non sia forzato)
    if not force and not is_notifications_enabled(hass, centrale_id):
        _LOGGER.debug(f"Notifica persistente non inviata (disabilitate): {title}")
        return ""

    if notification_id is None:
        notification_id = f"notification_{datetime.now().timestamp()}"
    
    service_data = {
        "message": message,
        "title": title,
        "notification_id": notification_id
    }
    
    # Aggiungi eventuali parametri extra
    service_data.update(kwargs)
    
    try:
        await hass.services.async_call(
            "persistent_notification",
            "create",
            service_data
        )
        _LOGGER.debug(f"Notifica persistente creata: {notification_id}")
        return notification_id
    except Exception as e:
        _LOGGER.error(f"Errore creazione notifica persistente: {e}")
        return ""  # Restituisce stringa vuota invece di sollevare eccezione

async def send_notification(
    hass,
    message: str,
    title: Optional[str] = None,
    target: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    centrale_id: Optional[int] = None,
    force: bool = False,  # Nuovo parametro per forzare l'invio
    **kwargs
) -> bool:
    """
    Invia una notifica generica (mobile, email, etc).
    
    Args:
        hass: Istanza di Home Assistant
        message: Messaggio della notifica
        title: Titolo della notifica (opzionale)
        target: Servizio di notifica target (es. "mobile_app_iphone", "email", "notify")
                Se None, usa il servizio notify di default
        data: Dati aggiuntivi per la notifica (actions, image, sound, etc)
        **kwargs: Parametri aggiuntivi per il servizio
        
    Returns:
        bool: True se inviata con successo, False altrimenti
    """

    # Controlla se le notifiche sono abilitate (a meno che non sia forzato)
    if not force and not is_notifications_enabled(hass, centrale_id):
        _LOGGER.debug(f"Notifica non inviata (disabilitate): {title or message[:30]}")
        return False

    # Costruisci i dati del servizio
    service_data = {"message": message}
    
    if title:
        service_data["title"] = title
    
    if data:
        service_data["data"] = data
    
    # Aggiungi eventuali parametri extra
    service_data.update(kwargs)
    
    # Determina dominio e servizio
    if target:
        if "." in target:
            # Target completo tipo "notify.mobile_app_iphone"
            domain, service = target.split(".", 1)
        else:
            # Solo nome servizio, usa dominio notify
            domain = "notify"
            service = target
    else:
        # Usa servizio di default
        domain = "notify"
        service = "notify"
    
    try:
        # Verifica prima se il servizio esiste
        if not hass.services.has_service(domain, service):
            _LOGGER.debug(f"Servizio {domain}.{service} non disponibile")
            return False
            
        await hass.services.async_call(
            domain,
            service,
            service_data,
            blocking=False  # Non bloccare se il dispositivo non è connesso
        )
        _LOGGER.debug(f"Notifica inviata a {domain}.{service}: {title or message[:30]}")
        return True
    except Exception as e:
        # Log solo come debug per errori comuni, error per errori inaspettati
        error_msg = str(e).lower()
        if "not connected" in error_msg or "unavailable" in error_msg:
            _LOGGER.debug(f"Dispositivo non connesso per {domain}.{service}: {e}")
        else:
            _LOGGER.warning(f"Errore invio notifica a {domain}.{service}: {e}")
        return False

async def dismiss_persistent_notification(
    hass,
    notification_id: str
) -> bool:
    """
    Rimuove una notifica persistente.
    
    Args:
        hass: Istanza di Home Assistant
        notification_id: ID della notifica da rimuovere
        
    Returns:
        bool: True se rimossa con successo, False altrimenti
        
    Example:
        await dismiss_persistent_notification(
            self.hass,
            "alarm_armed_123"
        )
    """
    try:
        await hass.services.async_call(
            "persistent_notification",
            "dismiss",
            {"notification_id": notification_id}
        )
        _LOGGER.debug(f"Notifica persistente rimossa: {notification_id}")
        return True
    except Exception as e:
        _LOGGER.error(f"Errore rimozione notifica persistente {notification_id}: {e}")
        return False

async def send_multiple_notifications(
    hass,
    message: str,
    title: Optional[str] = None,
    targets: Optional[List[str]] = None,
    persistent: bool = False,
    persistent_id: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    mobile: bool = True,
    centrale_id: Any = None,
    force: bool = False
) -> Dict[str, bool]:
    """
    Invia notifiche a multipli target contemporaneamente.
    """
    
    # Controlla se le notifiche sono abilitate (a meno che non sia forzato)
    if not force and not is_notifications_enabled(hass, centrale_id):
        _LOGGER.debug(f"Notifiche multiple non inviate (disabilitate): {title or message[:30]}")
        return {"skipped": True}

    results = {}
    
    # PRIMA invia la notifica persistente (non fallisce mai)
    if persistent:
        try:
            if persistent_id is None:
                persistent_id = f"notification_{datetime.now().timestamp()}"
            
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "message": message,
                    "title": title or "Notifica",
                    "notification_id": persistent_id
                },
                blocking=False  # Non bloccare
            )
            _LOGGER.debug(f"Notifica persistente creata: {persistent_id}")
            results["persistent"] = True
        except Exception as e:
            _LOGGER.error(f"Errore creazione notifica persistente: {e}")
            results["persistent"] = False
    
    # POI prova le notifiche mobile (possono fallire)
    if mobile:
        if targets is None:
            targets = ["notify"]
        
        for target in targets:
            try:
                # Determina dominio e servizio
                if "." in target:
                    domain, service = target.split(".", 1)
                else:
                    domain = "notify"
                    service = target
                
                # Verifica se il servizio esiste prima di chiamarlo
                if not hass.services.has_service(domain, service):
                    _LOGGER.debug(f"Servizio {domain}.{service} non disponibile")
                    results[target] = False
                    continue
                
                # Prepara i dati del servizio
                service_data = {
                    "message": message,
                    "title": title or "Notifica"
                }
                
                # Aggiungi data se fornito
                if data:
                    service_data["data"] = data
                
                # Chiama il servizio con blocking=False per evitare errori
                await hass.services.async_call(
                    domain,
                    service,
                    service_data,
                    blocking=False,  # IMPORTANTE: non bloccare
                    return_response=False
                )
                _LOGGER.debug(f"Notifica mobile inviata a {domain}.{service}")
                results[target] = True
                
            except Exception as e:
                error_msg = str(e).lower()
                if "not connected" in error_msg or "unavailable" in error_msg:
                    _LOGGER.debug(f"Dispositivo non connesso per {target}: {e}")
                else:
                    _LOGGER.warning(f"Errore invio notifica a {target}: {e}")
                results[target] = False
    
    return results

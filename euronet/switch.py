"""Switches per EuroPlus/EuroNET modalità locale."""
from __future__ import annotations
import logging
import asyncio
from datetime import timedelta

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.event import async_track_time_interval

from ..const import DOMAIN, MANUFACTURER
from ..utils import send_multiple_notifications

_LOGGER = logging.getLogger(__name__)

# Intervallo di controllo sabotaggi (10 minuti)
SABOTAGE_CHECK_INTERVAL = timedelta(minutes=10)


# ============================================================================
# SETUP FUNCTION
# ============================================================================

def setup_euronet_switches(coordinator, config_entry: ConfigEntry, hass):
    """
    Setup switches per EuroNET.
    """
    entities = []
    
    host = coordinator.client.host
    
    # Switch per abilitare/disabilitare le notifiche
    notifications_switch = EuroNetNotificationsSwitch(
        coordinator=coordinator,
        config_entry=config_entry,
        hass=hass,
        host=host,
    )
    entities.append(notifications_switch)
    
    # Switch per notifiche sabotaggi (controllo periodico ogni 10 minuti)
    sabotage_switch = EuroNetSabotageNotificationsSwitch(
        coordinator=coordinator,
        config_entry=config_entry,
        hass=hass,
        host=host,
    )
    entities.append(sabotage_switch)
    
    _LOGGER.info("Creati switch notifiche e sabotaggi per EuroNET")
    
    return entities


# ============================================================================
# NOTIFICATIONS SWITCH
# ============================================================================

class EuroNetNotificationsSwitch(SwitchEntity, RestoreEntity):
    """Switch per abilitare/disabilitare le notifiche della centrale."""
    
    def __init__(
        self,
        coordinator,
        config_entry: ConfigEntry,
        hass,
        host: str,
    ):
        """Inizializza lo switch notifiche."""
        self._coordinator = coordinator
        self._config_entry = config_entry
        self._hass = hass
        self._host = host
        self._is_on = True  # Default: notifiche abilitate
        
        self._attr_name = "Notifiche Pannello Allarme"
        self._attr_unique_id = f"euronet_{host}_notifications"
        self._attr_icon = "mdi:bell"
        
        # Device info - associa al device principale
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"euronet_{host}")},
            "name": f"EuroNET ({host})",
            "manufacturer": MANUFACTURER,
            "model": "4124EURONET",
        }
    
    async def async_added_to_hass(self) -> None:
        """Ripristina lo stato precedente quando l'entità viene aggiunta."""
        await super().async_added_to_hass()
        
        # Prova a ripristinare lo stato precedente
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._is_on = last_state.state == "on"
        
        # Inizializza il flag in hass.data
        self._update_hass_data()
        
        _LOGGER.debug(f"Switch notifiche ripristinato: {self._is_on}")
    
    def _update_hass_data(self) -> None:
        """Aggiorna il flag notifiche in hass.data."""
        if DOMAIN not in self._hass.data:
            self._hass.data[DOMAIN] = {}
        if "notifications_enabled" not in self._hass.data[DOMAIN]:
            self._hass.data[DOMAIN]["notifications_enabled"] = {}
        
        # Usa l'host come chiave identificativa
        self._hass.data[DOMAIN]["notifications_enabled"][self._host] = self._is_on
        _LOGGER.debug(f"Notifiche per {self._host}: {self._is_on}")
    
    @property
    def is_on(self) -> bool:
        """Restituisce lo stato dello switch."""
        return self._is_on
    
    async def async_turn_on(self, **kwargs) -> None:
        """Abilita le notifiche."""
        self._is_on = True
        self._update_hass_data()
        self.async_write_ha_state()
        _LOGGER.debug(f"Notifiche abilitate per {self._host}")
    
    async def async_turn_off(self, **kwargs) -> None:
        """Disabilita le notifiche."""
        self._is_on = False
        self._update_hass_data()
        self.async_write_ha_state()
        _LOGGER.debug(f"Notifiche disabilitate per {self._host}")


# ============================================================================
# SABOTAGE NOTIFICATIONS SWITCH
# ============================================================================

class EuroNetSabotageNotificationsSwitch(SwitchEntity, RestoreEntity):
    """Switch per abilitare il monitoraggio periodico dei sabotaggi.
    
    Quando attivo, ogni 10 minuti verifica:
    - Memorie sabotaggio (centrale, dispositivi bus, ingressi)
    - Allarme/memoria integrità bus
    - Zone filari e radio con memorie allarme attive
    
    Se trova anomalie, invia una notifica.
    """
    
    def __init__(
        self,
        coordinator,
        config_entry: ConfigEntry,
        hass,
        host: str,
    ):
        """Inizializza lo switch sabotaggi."""
        self._coordinator = coordinator
        self._config_entry = config_entry
        self._hass = hass
        self._host = host
        self._is_on = True  # Default: abilitato
        self._unsubscribe_timer = None
        
        self._attr_name = "Notifiche Sabotaggi"
        self._attr_unique_id = f"euronet_{host}_sabotage_notifications"
        self._attr_icon = "mdi:shield-alert"
        
        # Device info - associa al device principale
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"euronet_{host}")},
            "name": f"EuroNET ({host})",
            "manufacturer": MANUFACTURER,
            "model": "4124EURONET",
        }
    
    async def async_added_to_hass(self) -> None:
        """Ripristina lo stato precedente quando l'entità viene aggiunta."""
        await super().async_added_to_hass()
        
        # Prova a ripristinare lo stato precedente
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._is_on = last_state.state == "on"
        
        # Se era attivo, riavvia il timer
        if self._is_on:
            self._start_periodic_check()
        
        _LOGGER.debug(f"Switch sabotaggi ripristinato: {self._is_on}")
    
    async def async_will_remove_from_hass(self) -> None:
        """Cleanup quando l'entità viene rimossa."""
        self._stop_periodic_check()
        await super().async_will_remove_from_hass()
    
    def _start_periodic_check(self) -> None:
        """Avvia il controllo periodico ogni 10 minuti."""
        if self._unsubscribe_timer is not None:
            return  # Già attivo
        
        self._unsubscribe_timer = async_track_time_interval(
            self._hass,
            self._async_check_sabotage,
            SABOTAGE_CHECK_INTERVAL
        )
        _LOGGER.debug(f"Monitoraggio sabotaggi attivato per {self._host} (ogni 10 min)")
        
        # Esegui controllo immediato con delay per attendere dati coordinator
        async def delayed_check():
            # Attendi che il coordinator abbia dati validi
            for _ in range(30):  # Max 30 secondi di attesa
                if self._coordinator.data and len(self._coordinator.data) > 0:
                    await self._async_check_sabotage(None)
                    return
                await asyncio.sleep(1)
        
        self._hass.async_create_task(delayed_check())
    
    def _stop_periodic_check(self) -> None:
        """Ferma il controllo periodico."""
        if self._unsubscribe_timer is not None:
            self._unsubscribe_timer()
            self._unsubscribe_timer = None
            _LOGGER.debug(f"Monitoraggio sabotaggi disattivato per {self._host}")
    
    async def _async_check_sabotage(self, now) -> None:
        """Verifica stato sabotaggi e invia notifica se necessario."""
        if not self._is_on:
            return
        
        # Ottieni dati dal coordinator
        if not self._coordinator.data or len(self._coordinator.data) == 0:
            return
        
        system_data = self._coordinator.data[0]
        
        # Raccogli anomalie sabotaggi dalla centrale
        sabotaggi_attivi = []
        memorie_sabotaggio = []
        
        # Sabotaggi attivi
        if system_data.get("sabotaggio_centrale", False):
            sabotaggi_attivi.append("🚨 Sabotaggio centrale")
        if system_data.get("sabotaggio_ingressi", False):
            sabotaggi_attivi.append("🚨 Sabotaggio ingressi")
        if system_data.get("sabotaggio_dispositivi_bus", False):
            sabotaggi_attivi.append("🚨 Sabotaggio dispositivi bus")
        if system_data.get("allarme_integrita_bus", False):
            sabotaggi_attivi.append("⚠️ Allarme integrità bus")
        
        # Memorie sabotaggio
        if system_data.get("memoria_sabotaggio_centrale", False):
            memorie_sabotaggio.append("🔓 Memoria sabotaggio centrale")
        if system_data.get("memoria_sabotaggio_ingressi", False):
            memorie_sabotaggio.append("🔓 Memoria sabotaggio ingressi")
        if system_data.get("memoria_sabotaggio_dispositivi_bus", False):
            memorie_sabotaggio.append("🔓 Memoria sabotaggio dispositivi bus")
        if system_data.get("memoria_integrita_bus", False):
            memorie_sabotaggio.append("🔌 Memoria integrità bus")
        
        # Raccogli zone con memorie allarme attive
        zone_allarme = []
        zone_memoria_allarme = []
        zone_24h = []
        zone_memoria_24h = []
        
        entries = system_data.get("entries", {})
        for key, zona in entries.items():
            if not isinstance(zona, dict):
                continue
            
            # Ottieni nome zona (con fallback)
            numero = zona.get("numero", "?")
            nome = zona.get("nome")
            if not nome:
                if "filare" in key:
                    nome = f"Zona Filare {numero}"
                elif "radio" in key:
                    nome = f"Zona Radio {numero}"
                else:
                    nome = f"Zona {numero}"
            
            # Controlla i flag
            if zona.get("allarme_24h", False):
                zone_allarme.append(nome)
            if zona.get("memoria_allarme", False):
                zone_memoria_allarme.append(nome)
            if zona.get("memoria_24h", False):
                zone_memoria_24h.append(nome)
        
        # Se non c'è nulla da segnalare, esci
        if not sabotaggi_attivi and not memorie_sabotaggio and not zone_allarme and not zone_memoria_allarme and not zone_24h and not zone_memoria_24h:
            _LOGGER.debug(f"Controllo sabotaggi {self._host}: nessuna anomalia")
            return
        
        # Costruisci messaggio notifica
        lines = ["⚠️ **Controllo Sabotaggi** ⚠️\n"]
        
        if sabotaggi_attivi:
            lines.append("**Sabotaggi ATTIVI:**")
            for s in sabotaggi_attivi:
                lines.append(f"  {s}")
            lines.append("")
        
        if memorie_sabotaggio:
            lines.append("**Memorie sabotaggio:**")
            for m in memorie_sabotaggio:
                lines.append(f"  {m}")
            lines.append("")
        
        if zone_allarme:
            lines.append("**Zone in allarme 24h:**")
            for z in zone_allarme:
                lines.append(f"  • {z}")
            lines.append("")
        
        if zone_memoria_allarme:
            lines.append("**Zone con memoria allarme:**")
            for z in zone_memoria_allarme:
                lines.append(f"  • {z}")
            lines.append("")
        
        if zone_memoria_24h:
            lines.append("**Zone con memoria 24h:**")
            for z in zone_memoria_24h:
                lines.append(f"  • {z}")
            lines.append("")
        
        message = "\n".join(lines)
        
        # Invia notifica - questo switch è indipendente dal flag notifiche generale
        # Se lo switch è attivo, le notifiche sabotaggi vengono SEMPRE inviate
        await send_multiple_notifications(
            self._hass,
            message=message,
            title="⚠️ Controllo Sabotaggi - Centrale Lince",
            persistent=True,
            persistent_id=f"lince_sabotage_check_{self._host}",
            mobile=True,
            centrale_id=self._host,
            force=True,  # Ignora flag notifiche generale - questo switch è indipendente
            data={
                "tag": "lince_sabotage_check",
                "importance": "high",
                "priority": "high",
                "channel": "alarm",
            }
        )
        _LOGGER.warning(f"Notifica sabotaggi inviata per {self._host}")
    
    @property
    def is_on(self) -> bool:
        """Restituisce lo stato dello switch."""
        return self._is_on
    
    async def async_turn_on(self, **kwargs) -> None:
        """Abilita il monitoraggio sabotaggi."""
        self._is_on = True
        self._start_periodic_check()
        self.async_write_ha_state()
        _LOGGER.debug(f"Monitoraggio sabotaggi abilitato per {self._host}")
    
    async def async_turn_off(self, **kwargs) -> None:
        """Disabilita il monitoraggio sabotaggi."""
        self._is_on = False
        self._stop_periodic_check()
        self.async_write_ha_state()
        _LOGGER.debug(f"Monitoraggio sabotaggi disabilitato per {self._host}")

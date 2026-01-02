"""Alarm Control Panel per EuroPlus/EuroNET modalità locale."""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry

from ..const import DOMAIN, MANUFACTURER
from .const import CONF_ARM_PROFILES

_LOGGER = logging.getLogger(__name__)


# ============================================================================
# SETUP FUNCTION
# ============================================================================

def setup_euronet_alarm_panels(coordinator, config_entry: ConfigEntry, hass):
    """
    Setup alarm control panel per EuroNET.
    """
    entities = []
    
    panel = EuroNetAlarmPanel(
        coordinator=coordinator,
        config_entry=config_entry,
    )
    entities.append(panel)
    
    _LOGGER.info("Creato pannello allarme per EuroNET")
    return entities


# ============================================================================
# ALARM CONTROL PANEL
# ============================================================================

class EuroNetAlarmPanel(CoordinatorEntity, AlarmControlPanelEntity):
    """Pannello allarme per modalità locale."""
    
    _attr_code_format = CodeFormat.NUMBER
    _attr_code_arm_required = True
    
    def __init__(
        self,
        coordinator,
        config_entry: ConfigEntry,
    ):
        """Inizializza il pannello allarme."""
        super().__init__(coordinator)
        
        self._config_entry = config_entry
        
        # Host per unique_id
        host = coordinator.client.host
        
        self._attr_name = "Centrale Allarme"
        self._attr_unique_id = f"euronet_{host}_alarm_panel"
        self._attr_icon = "mdi:shield-home"
        
        # Determina le features in base ai profili ARM configurati
        arm_profiles = config_entry.options.get(CONF_ARM_PROFILES, {})
        
        features = 0
        # ARM_AWAY se il profilo "away" ha programmi configurati
        if arm_profiles.get("away"):
            features |= AlarmControlPanelEntityFeature.ARM_AWAY
        # ARM_HOME se il profilo "home" ha programmi configurati
        if arm_profiles.get("home"):
            features |= AlarmControlPanelEntityFeature.ARM_HOME
        # ARM_NIGHT se il profilo "night" ha programmi configurati
        if arm_profiles.get("night"):
            features |= AlarmControlPanelEntityFeature.ARM_NIGHT
        # ARM_VACATION se il profilo "vacation" ha programmi configurati
        if arm_profiles.get("vacation"):
            features |= AlarmControlPanelEntityFeature.ARM_VACATION
        
        self._attr_supported_features = features
        
        # Host per device_info
        self._host = host

    @property
    def device_info(self):
        """Device info dinamico per aggiornare sw_version."""
        sw_version = "N/A"
        if self.coordinator.data and len(self.coordinator.data) > 0:
            sw_version = str(self.coordinator.data[0].get("release_sw", "N/A"))
            
        return {
            "identifiers": {(DOMAIN, f"euronet_{self._host}")},
            "name": f"EuroNET ({self._host})",
            "manufacturer": MANUFACTURER,
            "model": "4124EURONET",
            "sw_version": sw_version,
        }

    def _get_system_data(self) -> dict | None:
        """Recupera i dati del sistema dal coordinator."""
        if self.coordinator.data and len(self.coordinator.data) > 0:
            return self.coordinator.data[0]
        return None

    def _get_active_programs(self, system: dict) -> set[str]:
        """Restituisce il set di programmi attualmente attivi."""
        active = set()
        if system.get("g1", False):
            active.add("G1")
        if system.get("g2", False):
            active.add("G2")
        if system.get("g3", False):
            active.add("G3")
        if system.get("gext", False):
            active.add("GEXT")
        return active
    
    def _get_configured_profiles(self) -> dict[str, set[str]]:
        """Restituisce i profili configurati con i loro programmi."""
        arm_profiles = self._config_entry.options.get(CONF_ARM_PROFILES, {})
        profiles = {}
        for mode in ["away", "home", "night", "vacation"]:
            programs = arm_profiles.get(mode, [])
            if programs:
                profiles[mode] = set(p.upper() for p in programs)
        return profiles

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Restituisce lo stato del pannello basato sui profili configurati."""
        system = self._get_system_data()
        if system:
            # Prima controlla se c'è un allarme in corso
            if system.get("allarme", False):
                return AlarmControlPanelState.TRIGGERED
            
            # Ottieni i programmi attivi
            active_programs = self._get_active_programs(system)
            
            # Se nessun programma attivo -> disarmato
            if not active_programs:
                return AlarmControlPanelState.DISARMED
            
            # Ottieni i profili configurati
            profiles = self._get_configured_profiles()
            
            # Cerca una corrispondenza esatta con i profili configurati
            # Ordine di priorità: away, home, night, vacation
            mode_mapping = {
                "away": AlarmControlPanelState.ARMED_AWAY,
                "home": AlarmControlPanelState.ARMED_HOME,
                "night": AlarmControlPanelState.ARMED_NIGHT,
                "vacation": AlarmControlPanelState.ARMED_VACATION,
            }
            
            for mode, state in mode_mapping.items():
                if mode in profiles and profiles[mode] == active_programs:
                    return state
            
            # Se non c'è corrispondenza esatta, usa una logica di fallback
            # basata sul numero di programmi attivi
            if len(active_programs) >= 2:
                return AlarmControlPanelState.ARMED_AWAY
            else:
                return AlarmControlPanelState.ARMED_HOME
        
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Attributi aggiuntivi."""
        attrs = {}
        system = self._get_system_data()
        if system:
            attrs["g1"] = system.get("g1", False)
            attrs["g2"] = system.get("g2", False)
            attrs["g3"] = system.get("g3", False)
            attrs["gext"] = system.get("gext", False)
            attrs["guasto"] = system.get("guasto", False)
            attrs["modo_servizio"] = system.get("modo_servizio", False)
        return attrs

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Disarma l'allarme."""
        if not code:
            _LOGGER.warning("Codice utente richiesto per disarmare")
            return
        
        _LOGGER.info("Disarmo allarme con codice utente")
        try:
            await self.coordinator.async_disarm(code)
        except Exception as e:
            _LOGGER.error(f"Errore durante il disarmo: {e}")
    
    def _get_programs_for_mode(self, mode: str) -> list[str]:
        """Recupera i programmi configurati per la modalità specificata."""
        arm_profiles = self._config_entry.options.get(CONF_ARM_PROFILES, {})
        programs = arm_profiles.get(mode, [])
        # Converti in maiuscolo (g1 -> G1, gext -> GEXT)
        return [p.upper() for p in programs]

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Arma l'allarme in modalità away."""
        if not code:
            _LOGGER.warning("Codice utente richiesto per armare")
            return
        
        programs = self._get_programs_for_mode("away")
        if not programs:
            _LOGGER.warning("Nessun programma configurato per modalità away")
            return
        
        _LOGGER.info("Armo allarme modalità away con programmi: %s", programs)
        try:
            await self.coordinator.async_arm(code, programs, arm_mode="away")
        except Exception as e:
            _LOGGER.error(f"Errore durante l'inserimento: {e}")

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Arma l'allarme in modalità home."""
        if not code:
            _LOGGER.warning("Codice utente richiesto per armare")
            return
        
        programs = self._get_programs_for_mode("home")
        if not programs:
            _LOGGER.warning("Nessun programma configurato per modalità home")
            return
        
        _LOGGER.info("Armo allarme modalità home con programmi: %s", programs)
        try:
            await self.coordinator.async_arm(code, programs, arm_mode="home")
        except Exception as e:
            _LOGGER.error(f"Errore durante l'inserimento: {e}")

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        """Arma l'allarme in modalità night."""
        if not code:
            _LOGGER.warning("Codice utente richiesto per armare")
            return
        
        programs = self._get_programs_for_mode("night")
        if not programs:
            _LOGGER.warning("Nessun programma configurato per modalità night")
            return
        
        _LOGGER.info("Armo allarme modalità night con programmi: %s", programs)
        try:
            await self.coordinator.async_arm(code, programs, arm_mode="night")
        except Exception as e:
            _LOGGER.error(f"Errore durante l'inserimento: {e}")

    async def async_alarm_arm_vacation(self, code: str | None = None) -> None:
        """Arma l'allarme in modalità vacation."""
        if not code:
            _LOGGER.warning("Codice utente richiesto per armare")
            return
        
        programs = self._get_programs_for_mode("vacation")
        if not programs:
            _LOGGER.warning("Nessun programma configurato per modalità vacation")
            return
        
        _LOGGER.info("Armo allarme modalità vacation con programmi: %s", programs)
        try:
            await self.coordinator.async_arm(code, programs, arm_mode="vacation")
        except Exception as e:
            _LOGGER.error(f"Errore durante l'inserimento: {e}")

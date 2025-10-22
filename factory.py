"""Factory per creare istanze brand-specific."""
from typing import Any, Dict, Type
import logging

_LOGGER = logging.getLogger(__name__)

class ComponentFactory:
    """Factory per creare componenti brand-specific."""
    
    @staticmethod
    def get_brand_from_system(system: dict) -> str:
        """Determina il brand dal sistema."""
        brand = system.get("brand", "lince-europlus")
        # Normalizza il brand
        if brand.lower() in ["lince-europlus", "europlus"]:
            return "lince-europlus"
        elif brand.lower() in ["lince-gold", "gold"]:
            return "lince-gold"
        else:
            _LOGGER.warning(f"Brand sconosciuto: {brand}, uso default europlus")
            return "lince-europlus"
    
    @staticmethod
    def get_coordinator(brand: str, hass, api, config_entry):
        """Ritorna il coordinator appropriato per il brand."""
        if brand == "lince-europlus":
            from .europlus.coordinator import EuroplusCoordinator
            return EuroplusCoordinator(hass, api, config_entry)
        elif brand == "lince-gold":
            from .gold.coordinator import GoldCoordinator
            return GoldCoordinator(hass, api, config_entry)
        else:
            from .europlus.coordinator import EuroplusCoordinator
            return EuroplusCoordinator(hass, api, config_entry)
    
    @staticmethod
    def get_api(brand: str, hass, email: str = None, password: str = None):
        """Ritorna l'API appropriata per il brand."""
        if brand == "lince-europlus":
            from .europlus.api import EuroplusAPI
            return EuroplusAPI(hass, email, password)
        elif brand == "lince-gold":
            from .gold.api import GoldAPI
            return GoldAPI(hass, email, password)
        else:
            from .europlus.api import EuroplusAPI
            return EuroplusAPI(hass, email, password)
    
    @staticmethod
    def get_parser(brand: str):
        """Ritorna il parser appropriato per il brand."""
        if brand == "lince-europlus":
            from .europlus.parser import europlusParser
            return europlusParser
        elif brand == "lince-gold":
            from .gold.parser import GoldParser
            return GoldParser
        else:
            from .europlus.parser import europlusParser
            return europlusParser
    
    @staticmethod
    def get_constants(brand: str) -> Dict[str, Any]:
        """Ritorna le costanti appropriate per il brand."""
        if brand == "lince-europlus":
            from .europlus import const
            return {
                "MAX_FILARI": const.MAX_FILARI,
                "MAX_RADIO": const.MAX_RADIO,
                "DEFAULT_FILARI": const.DEFAULT_FILARI,
                "DEFAULT_RADIO": const.DEFAULT_RADIO,
                "SUPPORTS_GEXT": const.SUPPORTS_GEXT,
                "PROGRAMS": const.PROGRAMS,
                "PROGRAM_BITS": const.PROGRAM_BITS,
                "SOCKET_MESSAGE_TYPE_PIN": const.SOCKET_MESSAGE_TYPE_PIN,
                "SOCKET_MESSAGE_TYPE_PROGRAMS": const.SOCKET_MESSAGE_TYPE_PROGRAMS,
            }
        elif brand == "lince-gold":
            from .gold import const
            return {
                "MAX_FILARI": const.MAX_FILARI,
                "MAX_RADIO": const.MAX_RADIO,
                "DEFAULT_FILARI": const.DEFAULT_FILARI,
                "DEFAULT_RADIO": const.DEFAULT_RADIO,
                "SUPPORTS_GEXT": const.SUPPORTS_GEXT,
                "PROGRAMS": const.PROGRAMS,
                "PROGRAM_BITS": const.PROGRAM_BITS,
                "SOCKET_MESSAGE_TYPE_PIN": const.SOCKET_MESSAGE_TYPE_PIN,
                "SOCKET_MESSAGE_TYPE_PROGRAMS": const.SOCKET_MESSAGE_TYPE_PROGRAMS,
            }
        else:
            # Default Europlus
            return {
                "MAX_FILARI": 35,
                "MAX_RADIO": 64,
                "DEFAULT_FILARI": 0,
                "DEFAULT_RADIO": 0,
                "SUPPORTS_GEXT": True,
                "PROGRAMS": ["g1", "g2", "g3", "gext"],
                "PROGRAM_BITS": {"g1": 1, "g2": 2, "g3": 4, "gext": 8},
                "SOCKET_MESSAGE_TYPE_PIN": 251,
                "SOCKET_MESSAGE_TYPE_PROGRAMS": 240,
            }
    
    @staticmethod
    def get_socket_client(brand: str, token, row_id: int, **callbacks):
        """Ritorna il socket client appropriato per il brand."""
        if brand == "lince-europlus":
            from .europlus.socket_client import EuroplusSocketClient
            return EuroplusSocketClient(token, row_id, **callbacks)
        elif brand == "lince-gold":
            from .gold.socket_client import GoldSocketClient
            return GoldSocketClient(token, row_id, **callbacks)
        else:
            from .europlus.socket_client import EuroplusSocketClient
            return EuroplusSocketClient(token, row_id, **callbacks)
    
    @staticmethod
    def get_alarm_panel(brand: str, name, unique_id, row_id, coordinator, api, config_entry):
        """Ritorna il pannello allarme appropriato per il brand."""
        if brand == "lince-europlus":
            from .europlus.alarm_control_panel import EuroplusAlarmPanel
            return EuroplusAlarmPanel(name, unique_id, row_id, coordinator, api, config_entry)
        elif brand == "lince-gold":
            from .gold.alarm_control_panel import GoldAlarmPanel
            return GoldAlarmPanel(name, unique_id, row_id, coordinator, api, config_entry)
        else:
            from .europlus.alarm_control_panel import EuroplusAlarmPanel
            return EuroplusAlarmPanel(name, unique_id, row_id, coordinator, api, config_entry)

    @staticmethod
    def get_binary_sensors_for_system(brand: str, system: dict, coordinator, api, config_entry, hass):
        """
        Ritorna TUTTE le entità binary sensor per un sistema specifico.
        DELEGA completamente al modulo del brand.
        """
        if brand == "lince-europlus":
            from .europlus.binary_sensor import setup_europlus_binary_sensors
            return setup_europlus_binary_sensors(system, coordinator, api, config_entry, hass)
        elif brand == "lince-gold":
            from .gold.binary_sensor import setup_gold_binary_sensors
            return setup_gold_binary_sensors(system, coordinator, api, config_entry, hass)
        else:
            # Default: usa Europlus
            from .europlus.binary_sensor import setup_europlus_binary_sensors
            return setup_europlus_binary_sensors(system, coordinator, api, config_entry, hass)
    
    @staticmethod
    def get_binary_sensor(brand: str, **kwargs):
        """Ritorna il binary sensor appropriato per il brand."""
        if brand == "lince-europlus":
            from .europlus.binary_sensor import EuroplusBinarySensor
            return EuroplusBinarySensor(**kwargs)
        elif brand == "lince-gold":
            from .gold.binary_sensor import GoldBinarySensor
            return GoldBinarySensor(**kwargs)
        else:
            from .europlus.binary_sensor import EuroplusBinarySensor
            return EuroplusBinarySensor(**kwargs)
    
    @staticmethod
    def get_sensor(brand: str, **kwargs):
        """Ritorna il sensor appropriato per il brand."""
        if brand == "lince-europlus":
            from .europlus.sensor import EuroplusSensor
            return EuroplusSensor(**kwargs)
        elif brand == "lince-gold":
            from .gold.sensor import GoldSensor
            return GoldSensor(**kwargs)
        else:
            from .europlus.sensor import EuroplusSensor
            return EuroplusSensor(**kwargs)
    
    @staticmethod
    def get_switch(brand: str, **kwargs):
        """Ritorna lo switch appropriato per il brand."""
        if brand == "lince-europlus":
            from .europlus.switch import EuroplusSwitch
            return EuroplusSwitch(**kwargs)
        elif brand == "lince-gold":
            from .gold.switch import GoldSwitch
            return GoldSwitch(**kwargs)
        else:
            from .europlus.switch import EuroplusSwitch
            return EuroplusSwitch(**kwargs)

    # Aggiungi questi metodi al ComponentFactory in factory.py

    @staticmethod
    def get_zone_sensor(brand: str, **kwargs):
        """Ritorna il zone sensor appropriato per il brand."""
        if brand == "lince-europlus":
            from .europlus.binary_sensor import EuroplusZoneBinarySensor
            return EuroplusZoneBinarySensor(**kwargs)
        elif brand == "lince-gold":
            from .gold.binary_sensor import GoldZoneBinarySensor
            return GoldZoneBinarySensor(**kwargs)
        else:
            from .europlus.binary_sensor import EuroplusZoneBinarySensor
            return EuroplusZoneBinarySensor(**kwargs)

    @staticmethod
    def get_buscomm_sensor(brand: str, **kwargs):
        """Ritorna il buscomm sensor appropriato per il brand."""
        if brand == "lince-europlus":
            from .europlus.binary_sensor import EuroplusBuscommBinarySensor
            return EuroplusBuscommBinarySensor(**kwargs)
        elif brand == "lince-gold":
            from .gold.binary_sensor import GoldBuscommBinarySensor
            return GoldBuscommBinarySensor(**kwargs)
        else:
            from .europlus.binary_sensor import EuroplusBuscommBinarySensor
            return EuroplusBuscommBinarySensor(**kwargs)
        
    # In factory.py aggiungi:

    @staticmethod
    def get_sensors_for_system(brand: str, system: dict, coordinator, api, config_entry, hass):
        """
        Ritorna TUTTE le entità sensor per un sistema specifico.
        DELEGA completamente al modulo del brand.
        """
        if brand == "lince-europlus":
            from .europlus.sensor import setup_europlus_sensors
            return setup_europlus_sensors(system, coordinator, api, config_entry, hass)
        elif brand == "lince-gold":
            from .gold.sensor import setup_gold_sensors
            return setup_gold_sensors(system, coordinator, api, config_entry, hass)
        else:
            # Default: usa Europlus
            from .europlus.sensor import setup_europlus_sensors
            return setup_europlus_sensors(system, coordinator, api, config_entry, hass)

    @staticmethod
    def get_alarm_panels_for_system(brand: str, system: dict, coordinator, api, config_entry, hass):
        """
        Ritorna TUTTE le entità alarm control panel per un sistema specifico.
        DELEGA completamente al modulo del brand.
        """
        if brand == "lince-europlus":
            from .europlus.alarm_control_panel import setup_europlus_alarm_panels
            return setup_europlus_alarm_panels(system, coordinator, api, config_entry, hass)
        elif brand == "lince-gold":
            from .gold.alarm_control_panel import setup_gold_alarm_panels
            return setup_gold_alarm_panels(system, coordinator, api, config_entry, hass)
        else:
            # Default: usa Europlus
            from .europlus.alarm_control_panel import setup_europlus_alarm_panels
            return setup_europlus_alarm_panels(system, coordinator, api, config_entry, hass)
"""Alarm control panel specifico per Lince Gold."""
import logging

_LOGGER = logging.getLogger(__name__)


def setup_gold_alarm_panels(system, coordinator, api, config_entry, hass):
    """
    Setup alarm control panel SPECIFICO Gold.
    Per ora ritorna lista vuota - DA IMPLEMENTARE.
    """
    entities = []
    row_id = system["id"]
    
    _LOGGER.warning(f"Gold alarm control panel per sistema {row_id} non implementato")
    
    # TODO: Implementare quando avremo le specifiche Gold
    # Gold probabilmente ha:
    # - Programmi diversi da G1, G2, G3, GEXT
    # - Comandi diversi per arm/disarm
    # - Stati diversi
    
    return entities


class GoldAlarmControlPanel:
    """
    TODO: Implementare quando avremo le specifiche Gold.
    Probabilmente completamente diverso da Europlus.
    """
    pass
"""Sensors specifici per Lince Gold."""
import logging
from ..common.sensors import CommonCentraleSensorEntity
from .entity_mapping import SENSOR_SYSTEM_KEYS, SENSOR_ACCESS_KEYS

_LOGGER = logging.getLogger(__name__)


def setup_gold_sensors(system, coordinator, api, config_entry, hass):
    """
    Setup COMPLETO dei sensors per Gold.
    Per ora implementazione minima, DA COMPLETARE quando avremo le specifiche Gold.
    """
    entities = []
    row_id = system["id"]
    centrale_id = system.get("id_centrale", row_id)
    centrale_name = system.get("name", "Sconosciuta")
    
    _LOGGER.info(f"Setup Gold sensors per sistema {row_id}")
    
    # Per ora Gold usa solo i sensori comuni dal sistema
    for key in SENSOR_SYSTEM_KEYS:
        if key in system:
            entities.append(
                GoldSensor(
                    coordinator, row_id, centrale_id, centrale_name, key, system.get(key)
                )
            )
    
    # Access data sensors
    access = system.get("access_data", {})
    for key in SENSOR_ACCESS_KEYS:
        if key in access:
            entities.append(
                GoldSensor(
                    coordinator, row_id, centrale_id, centrale_name, key, access.get(key)
                )
            )
    
    # TODO: Implementare quando avremo le specifiche Gold:
    # - Sensore ultima zona Gold (se le zone sono diverse)
    # - BUSComms Gold (se il protocollo è diverso)
    # - Altri sensori specifici Gold
    
    _LOGGER.warning(f"Gold sensors: implementazione parziale, solo sensori di sistema e access")
    
    return entities


def update_gold_buscomm_sensors(api, row_id, keys):
    """
    Aggiorna sensori buscomms GOLD - DA IMPLEMENTARE.
    Per ora non fa nulla.
    """
    _LOGGER.debug(f"update_gold_buscomm_sensors chiamato per {row_id} - non implementato")
    pass


class GoldSensor(CommonCentraleSensorEntity):
    """Sensor Gold per dati sistema/access (eredita da common)."""
    pass  # Per ora usa l'implementazione comune


# Placeholder per future implementazioni
class GoldBUSCommsSensor:
    """
    TODO: Implementare quando avremo le specifiche BUSComm Gold.
    Probabilmente il protocollo e i campi saranno diversi da Europlus.
    """
    pass


class GoldLastAlarmZoneSensor:
    """
    TODO: Implementare quando avremo le specifiche delle zone Gold.
    Probabilmente la struttura delle zone sarà diversa da Europlus.
    """
    pass

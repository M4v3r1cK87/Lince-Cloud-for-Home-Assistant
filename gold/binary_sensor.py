"""Binary sensors specifici per Lince Gold."""
import logging
from ..common.binary_sensors import CommonCentraleBinarySensorEntity
from .entity_mapping import BINARYSENSOR_SYSTEM_KEYS

_LOGGER = logging.getLogger(__name__)


def setup_gold_binary_sensors(system, coordinator, api, config_entry, hass):
    """
    Setup COMPLETO dei binary sensors per Gold.
    Per ora implementazione minima, DA COMPLETARE quando avremo le specifiche Gold.
    """
    entities = []
    row_id = system["id"]
    centrale_id = system.get("id_centrale", row_id)
    centrale_name = system.get("name", "Sconosciuta")
    
    _LOGGER.info(f"Setup Gold binary sensors per sistema {row_id}")
    
    # Per ora Gold usa solo i sensori comuni dal sistema
    # (questi sono condivisi tra tutti i brand)
    for key in BINARYSENSOR_SYSTEM_KEYS:
        if key in system:
            sensor = GoldBinarySensor(
                coordinator=coordinator,
                row_id=row_id,
                centrale_id=centrale_id,
                centrale_name=centrale_name,
                key=key,
                value=system.get(key),
                api=api
            )
            entities.append(sensor)
    
    # TODO: Implementare quando avremo le specifiche Gold:
    # - Zone Gold (se esistono e come sono strutturate)
    # - BUSComms Gold (se esiste e com'è diverso da Europlus)
    # - Altri sensori specifici Gold
    
    _LOGGER.warning(f"Gold binary sensors: implementazione parziale, solo sensori di sistema")
    
    return entities


class GoldBinarySensor(CommonCentraleBinarySensorEntity):
    """Binary sensor Gold per dati sistema (eredita da common)."""
    pass  # Per ora usa l'implementazione comune


# Placeholder per future implementazioni
class GoldZoneBinarySensor:
    """
    TODO: Implementare quando avremo le specifiche delle zone Gold.
    Probabilmente saranno completamente diverse da Europlus.
    """
    pass


class GoldBuscommBinarySensor:
    """
    TODO: Implementare quando avremo le specifiche BUSComm Gold.
    Probabilmente il protocollo e i campi saranno diversi da Europlus.
    """
    pass


def update_gold_buscomm_binarysensors(api, row_id, keys, isStepRecursive=False):
    """
    Aggiorna sensori buscomms GOLD - DA IMPLEMENTARE.
    Per ora non fa nulla.
    """
    _LOGGER.debug(f"update_gold_buscomm_binarysensors chiamato per {row_id} - non implementato")
    pass

"""Switch specifici per Lince Europlus."""
import logging

_LOGGER = logging.getLogger(__name__)


def setup_europlus_switches(system, coordinator, api, config_entry, hass):
    """
    Setup switch SPECIFICI Europlus.
    Per ora non ce ne sono, tutti gli switch sono comuni.
    """
    entities = []
    
    # TODO: Aggiungere qui eventuali switch specifici Europlus
    # Per esempio switch per attivare/disattivare singoli programmi G1, G2, G3, GEXT
    # se dovessero essere richiesti in futuro
    
    return entities


# Placeholder per eventuali switch specifici Europlus
class EuroplusProgramSwitch:
    """
    TODO: Eventuale switch per attivare/disattivare programmi Europlus.
    Da implementare se richiesto.
    """
    pass

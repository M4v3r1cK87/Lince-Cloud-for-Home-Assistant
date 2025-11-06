"""Binary sensors specifici per Lince Gold."""
import logging
from ..common.binary_sensors import CommonCentraleBinarySensorEntity
from .entity_mapping import BINARYSENSOR_SYSTEM_KEYS, STATUSCENTRALE_MAPPING
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from ..const import DOMAIN, MANUFACTURER_URL

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

    # Inizializza dizionari per Gold
    if not hasattr(api, 'buscomm_sensors'):
        api.buscomm_sensors = {}
    if row_id not in api.buscomm_sensors:
        api.buscomm_sensors[row_id] = {}
    
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

def _add_gold_buscomm_recursive(coordinator, system, api, row_id, centrale_id, centrale_name, mapping):
    """Helper ricorsivo per aggiungere sensori BUSComm."""
    entities = []
    
    for key, value in mapping.items():
        if isinstance(value, dict) and "entity_type" not in value:
            # Ricorsione per sotto-dizionari
            entities.extend(
                _add_gold_buscomm_recursive(coordinator, system, api, row_id, centrale_id, centrale_name, value)
            )
        elif isinstance(value, dict) and value.get("entity_type") == "binary_sensor":
            unique_id = f"lincebuscomms_{row_id}_{key}"
            if unique_id not in api.buscomm_sensors[row_id]:
                entity = GoldBuscommBinarySensor(
                    coordinator=coordinator,
                    system=system,
                    row_id=row_id,
                    centrale_id=centrale_id,
                    centrale_name=centrale_name,
                    key=key,
                    configs=value
                )
                entities.append(entity)
                api.buscomm_sensors[row_id][unique_id] = entity
    
    return entities

def get_entity_config(mapping, target_key):
    """Helper per ottenere configurazione entità dal mapping."""
    for key, value in mapping.items():
        if key == target_key and isinstance(value, dict) and "entity_type" in value:
            return value
        elif isinstance(value, dict):
            result = get_entity_config(value, target_key)
            if result:
                return result
    return None

def update_gold_buscomm_binarysensors(api, row_id, keys, isStepRecursive=False):
    """Aggiorna sensori buscomms GOLD - chiamabile dall'API."""
    global programma_g1, programma_g2, programma_g3, programma_gext
    global timer_uscita_g1_g2_g3, timer_uscita_gext
    
    if not hasattr(api, 'buscomm_sensors') or row_id not in api.buscomm_sensors:
        return
    
    if keys is None:
        # Reset tutti i sensori
        for key, value in api.buscomm_sensors[row_id].items():
            if value is not None and hasattr(value, 'update_values'):
                value.update_values(None)
    else:
        # Aggiorna i sensori con i valori forniti
        for key, value in keys.items():
            if isinstance(value, dict) and "entity_type" not in value:
                # Ricorsione
                update_europlus_buscomm_binarysensors(api, row_id, value, True)
                isStepRecursive = False
            else:
                config = get_entity_config(STATUSCENTRALE_MAPPING, key)
                if config and config.get("entity_type") == "binary_sensor":
                    unique_id = f"lincebuscomms_{row_id}_{key}"
                    entity = api.buscomm_sensors[row_id].get(unique_id)
                    if entity and hasattr(entity, 'update_values'):
                        entity.update_values(value)
                        # Traccia stato programmi
                        if key == "g1":
                            programma_g1 = value
                        elif key == "g2":
                            programma_g2 = value
                        elif key == "g3":
                            programma_g3 = value
        
        # Aggiorna centrale allarmata
        if not isStepRecursive:
            unique_id = f"lincebuscomms_{row_id}_centrale_allarmata"
            entity = api.buscomm_sensors[row_id].get(unique_id)
            if entity and hasattr(entity, 'update_values'):
                allarmata = programma_g1 or programma_g2 or programma_g3
                entity.update_values(allarmata)


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

class GoldBuscommBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor per dati BUS specifici per centrali Gold."""
    
    def __init__(self, coordinator, system, row_id, centrale_id, centrale_name, key, configs, value=None):
        super().__init__(coordinator)
        self._key = key
        self._row_id = row_id
        self._centrale_id = centrale_id
        self._centrale_name = centrale_name
        self._attr_unique_id = f"lincebuscomms_{self._row_id}_{self._key}"
        self._attr_device_class = configs.get("device_class", None)
        self._value = None
        self._state = None
        
        # Nome del sensore con customizzazione per programmi
        sensorName = configs.get("friendly_name", self._key)
        if system:
            accessKey = system.get("access_data", {})
            if self._key == "g1" and accessKey.get("g1"):
                sensorName = f"G1: {accessKey.get('g1')}"
            elif self._key == "g2" and accessKey.get("g2"):
                sensorName = f"G2: {accessKey.get('g2')}"
            elif self._key == "g3" and accessKey.get("g3"):
                sensorName = f"G3: {accessKey.get('g3')}"
        
        self._attr_name = sensorName
        self._friendly_name = sensorName
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self._row_id}_buscomms")},
            name="Comunicazioni Bus",
            model=f"{centrale_name} - {self._centrale_id}",
            configuration_url=MANUFACTURER_URL,
            via_device=(DOMAIN, self._row_id),
        )

    @property
    def should_poll(self):
        return False
    
    @property
    def is_on(self):
        if self._value is None:
            return None
        return bool(self._value)
    
    def safe_update(self):
        """Aggiorna lo stato dell'entità."""
        if getattr(self, "hass", None) is not None:
            self.async_write_ha_state()
        else:
            _LOGGER.debug(f"Entità {self._attr_unique_id} non registrata.")
    
    def update_values(self, value):
        """Aggiorna il valore del sensore."""
        _LOGGER.debug(f"Aggiornamento BUSComms {self._attr_name}: {value}")
        
        # Inversione per lock e battery
        #if self._attr_device_class in [BinarySensorDeviceClass.LOCK, BinarySensorDeviceClass.BATTERY]:
        #    self._value = not value
        #else:
        #    self._value = value
        
        self.safe_update()
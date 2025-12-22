"""Sensors specifici per Lince Gold."""
import logging
from ..common.sensors import CommonCentraleSensorEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from .entity_mapping import SENSOR_SYSTEM_KEYS, SENSOR_ACCESS_KEYS, STATUSCENTRALE_MAPPING
from ..const import DOMAIN, MANUFACTURER_URL
from ..utils import prima_lettera_maiuscola

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

    # Inizializza dizionari per Gold
    if not hasattr(api, 'buscomm_sensors'):
        api.buscomm_sensors = {}
    if row_id not in api.buscomm_sensors:
        api.buscomm_sensors[row_id] = {}
    
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

    # 5. Sensori BUSComms (SPECIFICI Gold)
    entities.extend(_setup_gold_buscomm_sensors(coordinator, api, row_id, centrale_id, centrale_name))

    return entities

def _setup_gold_buscomm_sensors(coordinator, api, row_id, centrale_id, centrale_name):
    """Setup sensori BUSComms SPECIFICI Gold con ricorsione."""
    entities = []

    # Inizializza il dizionario se non esiste
    if not hasattr(api, 'buscomm_sensors'):
        api.buscomm_sensors = {}
    if row_id not in api.buscomm_sensors:
        api.buscomm_sensors[row_id] = {}

    # Aggiungi sensori BUSComms ricorsivamente
    entities.extend(
        _add_gold_buscomm_recursive(coordinator, api, row_id, centrale_id, centrale_name, STATUSCENTRALE_MAPPING)
    )
    return entities

def _add_gold_buscomm_recursive(coordinator, api, row_id, centrale_id, centrale_name, mapping):
    """Helper ricorsivo per aggiungere sensori BUSComm."""
    entities = []
    
    for key, value in mapping.items():
        if isinstance(value, dict) and "entity_type" not in value:
            # Ricorsione per sotto-dizionari
            entities.extend(
                _add_gold_buscomm_recursive(coordinator, api, row_id, centrale_id, centrale_name, value)
            )
        elif isinstance(value, dict) and value.get("entity_type") == "sensor":
            entity = GoldBUSCommsSensor(
                coordinator, row_id, centrale_id, key, centrale_name, value
            )
            unique_id = f"lincebuscomms_{row_id}_{key}"
            entities.append(entity)
            api.buscomm_sensors[row_id][unique_id] = entity
    
    return entities     

def update_gold_buscomm_sensors(api, row_id, keys):
    """Aggiorna sensori buscomms GOLD - chiamabile dall'API."""
    _LOGGER.debug(f"update_gold_buscomm_sensors called for row_id={row_id}")
    
    if not hasattr(api, 'buscomm_sensors'):
        _LOGGER.debug(f"[{row_id}] api non ha buscomm_sensors")
        return
    if row_id not in api.buscomm_sensors:
        _LOGGER.debug(f"[{row_id}] row_id non presente in buscomm_sensors. Keys disponibili: {list(api.buscomm_sensors.keys())}")
        return
    
    if keys is None:
        # Reset tutti i sensori
        for key, value in api.buscomm_sensors[row_id].items():
            if value is not None and isinstance(value, GoldBUSCommsSensor):
                value.update_values(None)
    else:
        # Aggiorna i sensori con i valori forniti
        for key, value in keys.items():
            if isinstance(value, dict) and "entity_type" not in value:
                # Ricorsione
                _LOGGER.debug(f"[{row_id}] Ricorsione su chiave: {key}")
                update_gold_buscomm_sensors(api, row_id, value)
            else:
                # Aggiorna il sensore specifico
                config = get_entity_config(STATUSCENTRALE_MAPPING, key)
                if config and config.get("entity_type") == "sensor":
                    unique_id = f"lincebuscomms_{row_id}_{key}"
                    entity = api.buscomm_sensors[row_id].get(unique_id)
                    if entity:
                        _LOGGER.debug(f"[{row_id}] Aggiornamento sensore {key} con valore: {value}")
                        entity.update_values(value)
                    else:
                        _LOGGER.debug(f"[{row_id}] Entità non trovata per unique_id: {unique_id}")

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


class GoldSensor(CommonCentraleSensorEntity):
    """Sensor Gold per dati sistema/access (eredita da common)."""
    pass  # Per ora usa l'implementazione comune


# Placeholder per future implementazioni
class GoldBUSCommsSensor(CoordinatorEntity, SensorEntity):
    """Sensore BUSComms SPECIFICO GOLD."""
    
    def __init__(self, coordinator, row_id, centrale_id, key, centrale_name, configs, value=None):
        super().__init__(coordinator)
        _LOGGER.debug(f"Creazione Gold BUSComms Sensor: {key} per centrale {row_id}")
        self._row_id = row_id
        self._key = key
        self._centrale_id = centrale_id
        self._centrale_name = centrale_name
        self._attr_name = prima_lettera_maiuscola(configs["friendly_name"])
        self._attr_unique_id = f"lincebuscomms_{self._row_id}_{self._key}"
        self._attr_device_class = configs.get("device_class", None)
        self._attr_state_class = configs.get("state_class", None)
        self._unit_of_measurement = configs.get("unit_of_measurement", None)
        self._state = None

        if self._unit_of_measurement is not None:
            self._suggested_display_precision = 2
            self._attr_suggested_display_precision = 2

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
    def native_value(self):
        """Return the state of the sensor."""
        return self._state
    
    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement of the sensor."""
        return self._unit_of_measurement
    
    def safe_update(self):
        """Aggiorna lo stato dell'entità solo se è registrata in Home Assistant."""
        if getattr(self, "hass", None) is not None:
            self.async_write_ha_state()
        else:
            _LOGGER.debug(f"Entità {self._attr_unique_id} non registrata: aggiornamento ignorato.")
    
    def update_values(self, value):
        """Aggiorna il valore del sensore."""
        _LOGGER.debug(f"Aggiornamento Gold BUSComms Sensor {self._attr_unique_id}: {value}")
        try:
            self._state = float(value)
        except (TypeError, ValueError):
            self._state = value
        self.set_unit_of_measurement()
        self.safe_update()

    def set_unit_of_measurement(self):
        """Imposta l'unità di misura in base al device_class."""
        _LOGGER.debug(f"Aggiornamento unit_of_measurement per {self._attr_unique_id} (device_class: {self._attr_device_class})")
        if self._attr_device_class is not None:
            if self._attr_device_class == "temperature":
                self._unit_of_measurement = "°C"
            elif self._attr_device_class == "voltage":
                self._unit_of_measurement = "V"


class GoldLastAlarmZoneSensor:
    """
    TODO: Implementare quando avremo le specifiche delle zone Gold.
    Probabilmente la struttura delle zone sarà diversa da Europlus.
    """
    pass

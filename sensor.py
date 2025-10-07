from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import STATE_UNKNOWN
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, MANUFACTURER, MANUFACTURER_URL
from .utils import prima_lettera_maiuscola
from .entity_mapping import SENSOR_SYSTEM_KEYS, SENSOR_ACCESS_KEYS, STATUSCENTRALE_MAPPING

import logging
import asyncio
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    coordinator = hass.data[DOMAIN]["coordinator"]
    api = hass.data[DOMAIN]["api"]
    entities = []
    #_LOGGER.debug(f"In async_setup_entry, coordinator data: {coordinator.data}")

    for system in coordinator.data:
        #_LOGGER.debug(f"Lince Gold Cloud - System: {coordinator.data}")
        row_id = system["id"]
        centrale_id = system["id_centrale"]
        centrale_name = f'{system.get("name", "Sconosciuta")}'

        # System data
        for key in SENSOR_SYSTEM_KEYS:            
            #_LOGGER.debug(f"Append Sensor: {key}")
            if key in system:
                entities.append(GoldCloud_CentraleSensorEntities(coordinator, row_id, centrale_name, key, system.get(key)))

        # Access data
        access = system.get("access_data", {})
        for key in SENSOR_ACCESS_KEYS:
            if key in access:
                #_LOGGER.debug(f"Append Access: {key}")
                entities.append(GoldCloud_CentraleSensorEntities(coordinator, row_id, centrale_name, key, access.get(key)))

        # NUOVO: Sensore ultima zona in allarme
        entities.append(GoldCloud_LastAlarmZoneSensorEntity(coordinator, api, row_id))

        # Sensore socket
        #entities.append(GoldCloud_lastMessageSocketEntity(row_id, centrale_id, centrale_name, api))

        # Sensori dinamici da buscomms
        entities += add_buscomm_sensors(coordinator, api, row_id, centrale_id, centrale_name, STATUSCENTRALE_MAPPING)
    async_add_entities(entities)

def get_entity_config(mapping, target_key):
    for key, value in mapping.items():
        if key == target_key and isinstance(value, dict) and "entity_type" in value:
            return value
        elif isinstance(value, dict):
            result = get_entity_config(value, target_key)
            if result:
                return result
    return None

# Sensori dinamici da buscomms
def add_buscomm_sensors(coordinator, api, row_id, centrale_id, centrale_name, keys):
    entities = []

    for key, value in keys.items():
        # Se è un sotto-dict
        if isinstance(value, dict) and "entity_type" not in value:
            # Ricorsione sulle sottochiavi
            entities += add_buscomm_sensors(coordinator, api, row_id, centrale_id, centrale_name, value)
        else:
            # Qui istanzia la classe giusta
            if value.get("entity_type") == "sensor":
                entity = GoldCloud_BUSCommsSensorEntity(
                        coordinator, row_id, centrale_id, key, centrale_name, value
                    )
                unique_id = f"lincebuscomms_{row_id}_{key}"               
                entities.append(entity)
                if api.buscomm_sensors.get(row_id) is None:
                    api.buscomm_sensors[row_id] = {}
                api.buscomm_sensors[row_id][unique_id] = entity
    return entities

# Aggiornamento sensori buscomms
def update_buscomm_sensors(self, row_id, keys):
    if keys is None:
        for key, value in self.buscomm_sensors[row_id].items():
            if value is not None and isinstance(value, GoldCloud_BUSCommsSensorEntity):
                value.update_values(None)
    else:
        for key, value in keys.items():
            # Se è un sotto-dict
            if isinstance(value, dict) and "entity_type" not in value:
                # Ricorsione sulle sottochiavi
                update_buscomm_sensors(self, row_id, value)
            else:
                # Qui aggiorna la classe giusta, prendo solo i sensor
                config = get_entity_config(STATUSCENTRALE_MAPPING, key)
                if config and config.get("entity_type") == "sensor":
                    unique_id = f"lincebuscomms_{row_id}_{key}"
                    entity = self.buscomm_sensors[row_id].get(unique_id)
                    if entity:
                        entity.update_values(value)

class GoldCloud_CentraleSensorEntities(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, row_id, centrale_name, key, value):
        super().__init__(coordinator)
        self._row_id = row_id
        self._key = key
        self._centrale_name = centrale_name
        self._attr_name = prima_lettera_maiuscola(self._key)
        self._attr_unique_id = f"lince_{self._row_id}_{self._key}"
        self._attr_native_value = value

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(f"{DOMAIN}", self._row_id)}
        )

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def should_poll(self):
        return False

class GoldCloud_lastMessageSocketEntity(SensorEntity):
    """Sensore che mostra l'ultimo messaggio ricevuto dalla socket."""

    def __init__(self, row_id, centrale_name, api):
        self._attr_entity_registry_enabled_default = False
        self._row_id = row_id
        self._centrale_name = centrale_name
        self._api = api
        self._attr_native_value = None
        self._attr_name = f"Socket Last Message"
        self._attr_unique_id = f"lince_{self._row_id}_socket_message"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._row_id)}
        )

        # Registrazione nel dizionario dei sensori socket
        if not hasattr(self._api, "socket_message_sensor"):
            self._api.socket_message_sensor = {}
        self._api.socket_message_sensor[self._row_id] = self

    @property
    def entity_category(self):
        return EntityCategory.DIAGNOSTIC    
    
    def safe_update(self):
        """Aggiorna lo stato dell'entità solo se è registrata in Home Assistant."""
        if getattr(self, "hass", None) is not None and self.entity_id:
            self.async_write_ha_state()
        else:
            _LOGGER.debug(f"Entità {self._attr_unique_id} non registrata: aggiornamento ignorato.")

    def update_message(self, new_message):
        # Limita la lunghezza del sensore a 255 caratteri, ma scrive comunque tutto il messaggio all'interno di un attributo
        if self.hass is not None:
            if isinstance(new_message, str) and len(new_message) > 255:
                self._attr_extra_state_attributes = {"full_message": new_message}
                new_message = new_message[:255]
            else:
                self._attr_extra_state_attributes = {}

            self._attr_native_value = new_message
            self.safe_update()

    async def async_update(self):
        message = self._api.get_last_socket_message(self._row_id)
        self._attr_native_value = message if message is not None else STATE_UNKNOWN

class GoldCloud_BUSCommsSensorEntity(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, row_id, centrale_id, key, centrale_name, configs, value=None):
        super().__init__(coordinator)
        _LOGGER.debug(f"Creazione BUSComms Sensor: {key} per centrale {row_id} con configs: {configs} e valore iniziale: {value}")
        self._row_id = row_id
        self._key = key
        self._row_id = row_id
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
        _LOGGER.debug(f"Aggiornamento BUSComms Sensor : Update Values {self._attr_unique_id} con keys: {value}")
        try:
            self._state = float(value)
        except (TypeError, ValueError):
            self._state = value
        self.set_unit_of_measurement()
        self.safe_update()

    def set_unit_of_measurement(self):
        _LOGGER.debug(f"Aggiornamento unit_of_measurement per sensore {self._attr_unique_id} in base a device_class {self._attr_device_class}")
        if self._attr_device_class is not None:
            if self._attr_device_class == "temperature":
                self._unit_of_measurement = "°C"
            elif self._attr_device_class == "voltage":
                self._unit_of_measurement = "V"

class GoldCloud_LastAlarmZoneSensorEntity(CoordinatorEntity, SensorEntity):
    """Sensore che mostra l'ultima zona che ha generato un allarme."""
    
    def __init__(self, coordinator, api, row_id):
        _LOGGER.debug(f"Creazione LastAlarmZoneSensor per centrale {row_id}")
        super().__init__(coordinator)
        self._api = api
        self._row_id = row_id
        self._attr_name = "Ultima zona in allarme"
        self._attr_unique_id = f"lince_{self._row_id}_last_alarm_zone"
        self._attr_native_value = "Nessuna"
        self._last_alarm_zone = None
        self._last_alarm_attributes = {}
        
        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._row_id)}
        )
        
        # Registra il sensore nell'API per accesso facile
        if not hasattr(self._api, "last_alarm_zone_sensor"):
            self._api.last_alarm_zone_sensor = {}
        self._api.last_alarm_zone_sensor[self._row_id] = self
    
    @property
    def native_value(self):
        """Ritorna il valore del sensore."""
        return self._attr_native_value
    
    @property
    def extra_state_attributes(self):
        """Ritorna gli attributi della zona in allarme."""
        return self._last_alarm_attributes
    
    @property
    def should_poll(self):
        return False

    @property
    def icon(self):
        return "mdi:alert-circle-check" if self.native_value == "Nessuna" else "mdi:alert-circle"
    
    @property
    def available(self):
        """Il sensore è sempre disponibile."""
        return True
    
    async def async_added_to_hass(self):
        """Quando viene aggiunto a Home Assistant."""
        await super().async_added_to_hass()
        _LOGGER.info(f"Sensore ultima zona allarme aggiunto per centrale {self._row_id}")
        # Esegui un check iniziale dopo un breve delay
        self.hass.async_create_task(self._async_initial_check())
    
    async def _async_initial_check(self):
        """Check iniziale dopo l'aggiunta."""
        await asyncio.sleep(5)  # Aspetta che le zone siano caricate
        await self.hass.async_add_executor_job(self.check_and_update_alarm_zones)
    
    def safe_update(self):
        """Aggiorna lo stato dell'entità in modo thread-safe."""
        if getattr(self, "hass", None) is not None:
            # Usa call_soon_threadsafe per schedulare direttamente async_write_ha_state
            # senza creare una coroutine intermedia
            self.hass.loop.call_soon_threadsafe(
                self.async_schedule_update_ha_state
            )
    
    def check_and_update_alarm_zones(self):
        """Controlla tutte le zone e aggiorna se trova allarmi.
        
        Questo metodo può essere chiamato da thread diversi,
        quindi usa safe_update() invece di async_write_ha_state().
        """
        try:
            if not hasattr(self._api, 'zone_sensors'):
                _LOGGER.debug(f"[{self._row_id}] zone_sensors non ancora disponibile")
                return
            
            if self._row_id not in self._api.zone_sensors:
                _LOGGER.debug(f"[{self._row_id}] Nessuna zona per questa centrale")
                return
            
            zones_data = self._api.zone_sensors[self._row_id]
            alarm_found = False
            
            # Controlla prima le zone filari
            filare_zones = zones_data.get('filare', {})
            for zone_num, zone_entity in filare_zones.items():
                if zone_entity and hasattr(zone_entity, '_attr_extra_state_attributes'):
                    attrs = zone_entity._attr_extra_state_attributes
                    # Controlla se ha memoria allarme, allarme 24h o memoria 24h attivi
                    if (attrs.get('Memoria Allarme') or 
                        attrs.get('Allarme 24h') or 
                        attrs.get('Memoria 24h')):
                        
                        zone_name = attrs.get('Nome', f'Zona {zone_num}')
                        new_value = f"{str(zone_num).zfill(2)}: {zone_name}"
                        
                        # Aggiorna solo se è cambiato
                        if self._attr_native_value != new_value:
                            self._attr_native_value = new_value
                            self._last_alarm_zone = f"filare_{zone_num}"
                            self._last_alarm_attributes = dict(attrs)
                            alarm_found = True
                            _LOGGER.info(f"[{self._row_id}] Rilevato allarme zona filare {zone_num}: {zone_name}")
                            self.safe_update()
                        return
            
            # Poi controlla le zone radio
            radio_zones = zones_data.get('radio', {})
            for zone_num, zone_entity in radio_zones.items():
                if zone_entity and hasattr(zone_entity, '_attr_extra_state_attributes'):
                    attrs = zone_entity._attr_extra_state_attributes
                    # Controlla se ha memoria allarme, allarme 24h o memoria 24h attivi
                    if (attrs.get('Memoria Allarme') or 
                        attrs.get('Allarme 24h') or 
                        attrs.get('Memoria 24h')):
                        
                        zone_name = attrs.get('Nome', f'Zona Radio {zone_num}')
                        new_value = f"{str(zone_num).zfill(2)}: {zone_name}"
                        
                        # Aggiorna solo se è cambiato
                        if self._attr_native_value != new_value:
                            self._attr_native_value = new_value
                            self._last_alarm_zone = f"radio_{zone_num}"
                            self._last_alarm_attributes = dict(attrs)
                            alarm_found = True
                            _LOGGER.info(f"[{self._row_id}] Rilevato allarme zona radio {zone_num}: {zone_name}")
                            self.safe_update()
                        return
            
            # Se non ci sono più allarmi attivi, resetta il sensore
            if not alarm_found and self._attr_native_value != "Nessuna":
                _LOGGER.info(f"[{self._row_id}] Nessun allarme attivo, reset sensore ultima zona")
                self._attr_native_value = "Nessuna"
                self._last_alarm_zone = None
                self._last_alarm_attributes = {}
                self.safe_update()
                
        except Exception as e:
            _LOGGER.error(f"[{self._row_id}] Errore in check_and_update_alarm_zones: {e}", exc_info=True)

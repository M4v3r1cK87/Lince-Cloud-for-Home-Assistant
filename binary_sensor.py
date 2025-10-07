from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo, DeviceEntryType
from homeassistant.helpers import device_registry as dr  # per le costanti connections (es. MAC)


import logging

from .const import DOMAIN, MODEL_IMAGE_BASE, MANUFACTURER, MANUFACTURER_URL
from .utils import ensure_device_icon_exists, prima_lettera_maiuscola
from .entity_mapping import BINARYSENSOR_SYSTEM_KEYS, STATUSCENTRALE_MAPPING

_LOGGER = logging.getLogger(__name__)

programma_g1 = False
programma_g2 = False
programma_g3 = False
programma_gext = False
timer_uscita_g1_g2_g3 = False
timer_uscita_gext = False
centrale_allarmata = False

async def async_setup_entry(hass, config_entry, async_add_entities):
    api = hass.data[DOMAIN]["api"]
    coordinator = hass.data[DOMAIN]["coordinator"]
    entities = []
    buscomm_sensors = {}    

    for system in coordinator.data:
        row_id = system["id"]
        centrale_id = system["id_centrale"]
        centrale_name = f'{system.get("name", "Sconosciuta")}'
        modello = system.get("modello", "default")
        icon_url = f"{MODEL_IMAGE_BASE}/{modello}.png"
        image_path = await ensure_device_icon_exists(hass, modello, icon_url)
        buscomm_sensors[row_id] = {}
        _LOGGER.debug(f"Icon URL: {icon_url} - Image Path: {image_path}")

        # Sensore stato socket
        entities.append(GoldCloud_isSocketConnectedEntity(row_id, centrale_name, api))

         # System data
        for key in BINARYSENSOR_SYSTEM_KEYS:            
            #_LOGGER.debug(f"Append Sensor: {key}")
            if key in system:
                entities.append(GoldCloud_CentraleBinarySensorEntities(coordinator, row_id, centrale_id, centrale_name, key, system.get(key)))

        # Zone sensors
        if "zonesName" in system:
            zonesName = system["zonesName"]  # {'filare': [...], 'radio': [...]}
            _LOGGER.debug(f"Zones Name: {zonesName}")
            if "filare" in zonesName:
                _LOGGER.debug("In Zone filari")
                for idx, zone in enumerate(zonesName['filare']):
                    _LOGGER.debug(f"Zona filare {idx+1}: {zone}")
                    if zone:
                        attributes = {}
                        attributes['Tipo Zona'] = 'Filare'
                        attributes['Numero Zona'] = idx + 1

                        attributes['Ingresso Aperto'] = None
                        attributes['Ingresso Escluso'] = None
                        attributes['Memoria Allarme'] = None
                        attributes['Allarme 24h'] = None
                        attributes['Memoria 24h'] = None

                        attributes.update(zone)  # Aggiungo gli attributi specifici della zona
                        _LOGGER.debug(f"Attributes Zona filare {idx+1}: {attributes}")

                        entities.append(
                            GoldCloud_zoneSensorEntities(
                                coordinator,
                                api,
                                row_id,
                                centrale_id,
                                centrale_name,
                                attributes,
                                "motion"
                            )
                        )
            if "radio" in zonesName:
                for idx, zone in enumerate(zonesName['radio']):
                    if zone:
                        attributes = {}
                        attributes['Tipo Zona'] = 'Radio'
                        attributes['Numero Zona'] = idx + 1

                        attributes['Allarme 24h'] = None
                        attributes['Memoria 24h'] = None
                        attributes['Ingresso Allarme'] = None
                        attributes['Memoria Allarme'] = None
                        attributes['Supervisione'] = None
                        attributes['Batteria'] = None

                        attributes.update(zone)  # Aggiungo gli attributi specifici della zona
                        _LOGGER.debug(f"Attributes Zona Radio {idx+1}: {attributes}")

                        entities.append(
                            GoldCloud_zoneSensorEntities(
                                coordinator,
                                api,
                                row_id,
                                centrale_id,
                                centrale_name,
                                attributes,
                                "motion"
                            )
                        )
        # Sensori dinamici da buscomms
        entities += add_buscomm_sensors(coordinator, system, api, row_id, centrale_id, centrale_name, STATUSCENTRALE_MAPPING)

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
def add_buscomm_sensors(coordinator, system, api, row_id, centrale_id, centrale_name, keys):
    entities = []
    if api.buscomm_sensors.get(row_id) is None:
        api.buscomm_sensors[row_id] = {}

    # Creo sensore binario per lo stato della centrale
    # True --> Centrale allarmata
    # False --> Centrale disinserita
    centrale_allarmata_unique_id = f"lincebuscomms_{row_id}_centrale_allarmata"
    centrale_allarmata_sensor = api.buscomm_sensors[row_id].get(centrale_allarmata_unique_id, None)
    if centrale_allarmata_sensor is None:
        entity = GoldCloud_BUSCommsBinarySensorEntity(
            coordinator, None, row_id, centrale_id, centrale_name, "centrale_allarmata", {
                "entity_type": "binary_sensor",
                "friendly_name": "Centrale Allarmata",
                "device_class": "lock"
            }
        )
        entities.append(entity)
        api.buscomm_sensors[row_id][centrale_allarmata_unique_id] = entity

    for key, value in keys.items():
        # Se è un sotto-dict
        if isinstance(value, dict) and "entity_type" not in value:
            # Ricorsione sulle sottochiavi
            entities += add_buscomm_sensors(coordinator, system, api, row_id, centrale_id, centrale_name, value)
        else:
            # Qui istanzia la classe giusta
            if value.get("entity_type") == "binary_sensor":
                entity = GoldCloud_BUSCommsBinarySensorEntity(
                        coordinator, system, row_id, centrale_id, centrale_name, key, value
                    )
                unique_id = f"lincebuscomms_{row_id}_{key}"
                entities.append(entity)                
                api.buscomm_sensors[row_id][unique_id] = entity

    return entities

# Aggiornamento sensori buscomms
def update_buscomm_binarysensors(self, row_id, keys, isStepRecursive=False):
    global programma_g1, programma_g2, programma_g3, programma_gext, timer_uscita_g1_g2_g3, timer_uscita_gext
    if keys is None:
        for key, value in self.buscomm_sensors[row_id].items():
            if value is not None and isinstance(value, GoldCloud_BUSCommsBinarySensorEntity):
                value.update_values(None)
    else:
        for key, value in keys.items():
            # Se è un sotto-dict
            if isinstance(value, dict) and "entity_type" not in value:
                # Ricorsione sulle sottochiavi
                update_buscomm_binarysensors(self, row_id, value, True)
                isStepRecursive = False
            else:
                config = get_entity_config(STATUSCENTRALE_MAPPING, key)
                if config and config.get("entity_type") == "binary_sensor":
                    unique_id = f"lincebuscomms_{row_id}_{key}"
                    entity = self.buscomm_sensors[row_id].get(unique_id)
                    if entity:
                        entity.update_values(value)
                        if key == "attivo_g1":
                            programma_g1 = value
                        elif key == "attivo_g2":
                            programma_g2 = value
                        elif key == "attivo_g3":
                            programma_g3 = value
                        elif key == "attivo_gext":
                            programma_gext = value
                        elif key == "tempo_out_g1g2g3":
                            timer_uscita_g1_g2_g3 = value
                        elif key == "tempo_out_gext":
                            timer_uscita_gext = value

        if not isStepRecursive:
            unique_id = f"lincebuscomms_{row_id}_centrale_allarmata"
            entity = self.buscomm_sensors[row_id].get(unique_id)
            if entity:
                entity.update_values((programma_g1 or programma_g2 or programma_g3 or programma_gext) and not (timer_uscita_g1_g2_g3 or timer_uscita_gext))

class GoldCloud_isSocketConnectedEntity(BinarySensorEntity):
    def __init__(self, row_id, centrale_name, api):
        self._row_id = row_id
        self._centrale_name = centrale_name
        self._api = api
        self._attr_native_value = None
        self._attr_device_class = "connectivity"
        self._attr_name = f"Socket Connected"
        self._attr_unique_id = f"lince_{self._row_id}_socket_connected"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._row_id)}
        )

        # Registrazione nel dizionario dei sensori socket
        if not hasattr(self._api, "socket_connection_sensor"):
            self._api.socket_connection_sensor = {}
        self._api.socket_connection_sensor[self._row_id] = self

    def safe_update(self):
        """Aggiorna lo stato dell'entità solo se è registrata in Home Assistant."""
        if getattr(self, "hass", None) is not None:
            self.async_write_ha_state()
        else:
            _LOGGER.debug(f"Entità {self._attr_unique_id} non registrata: aggiornamento ignorato.")

    def update_status(self, is_connected: bool):
        self._attr_native_value = is_connected
        self.safe_update()

    @property
    def is_on(self):
        return self._api.is_socket_connected(self._row_id)

    #@property
    #def icon(self):
    #    return "mdi:lan-connect" if self.native_value else "mdi:lan-disconnect"

    @property
    def entity_category(self):
        return EntityCategory.DIAGNOSTIC

class GoldCloud_CentraleBinarySensorEntities(CoordinatorEntity, BinarySensorEntity):
    def __init__(self, coordinator, row_id, centrale_id, centrale_name, key, value, api = None):
        super().__init__(coordinator)
        self._centrale_id = centrale_id
        self._row_id = row_id
        self._value = value
        self._centrale_name = centrale_name
        self._key = key
        self._attr_name = prima_lettera_maiuscola(self._key)
        self._attr_unique_id = f"lince_{self._row_id}_{self._key}"
        self.api = api

    @property
    def device_info(self):
        # Recupera il sistema per ottenere dati del dispositivo
        system = next((s for s in self.coordinator.data if s["id"] == self._row_id), None)
        if system is None:
            return None

        image_path = f"/local/{DOMAIN}/icons/{system['modello']}.png" if system.get("modello") else None
        centrale_name = f'Centrale Lince {self._centrale_name} - {self._centrale_id}'
        
        # connections: usa la costante ufficiale per MAC; se non hai il MAC, passa set() oppure ometti il campo
        connections = {(dr.CONNECTION_NETWORK_MAC, system["mac"])} if system.get("mac") else set()
        
        return DeviceInfo(
            identifiers={(DOMAIN, self._row_id)},   # deve combaciare con via_device dei figli
            name=centrale_name,
            manufacturer=MANUFACTURER,
            model=self._get_model_id().strip(),
            configuration_url=MANUFACTURER_URL,
            entry_type=DeviceEntryType.SERVICE,
            connections=connections,
            # suggested_area="Quadro elettrico",              # opzionale
        )

    def _get_model(self):
        for system in self.coordinator.data:
            if system["id"] == self._row_id:
                return system.get("brand", "Unknown")
        return "Unknown"
    
    def _get_model_id(self):
        for system in self.coordinator.data:
            if system["id"] == self._row_id:
                return system.get("model", "Unknown")
        return "Unknown"

    @property
    def should_poll(self):
        return False
    
    @property
    def is_on(self):
        return bool(self._value)

class GoldCloud_zoneSensorEntities(CoordinatorEntity, BinarySensorEntity):
    def __init__(self, coordinator, api, row_id, centrale_id, centrale_name, attributes, device_class="motion"):
        super().__init__(coordinator)
        self._api = api
        self._row_id = row_id
        self._centrale_id = centrale_id
        self._centrale_name = centrale_name
        self._zone_type = attributes['Tipo Zona']
        self._zone_number = attributes['Numero Zona']
        self._zone_name = attributes['Nome']
        self._attr_name = f"Zona {str(self._zone_number).zfill(2)}: {self._zone_name}"
        self._attr_unique_id = f"{self._row_id}_{self._zone_type.lower()}_{self._zone_number}"
        self._attr_device_class = device_class
        self._attr_extra_state_attributes = attributes
        self._state = attributes.get('Ingresso Aperto', None)
        self._attr_suggested_object_id = f"Centrale Lince {self._centrale_id} - Zona_{self._zone_type.lower()}_{self._zone_number}"

        # Registrazione nel dizionario dei sensori zone
        if not hasattr(self._api, f"zone_sensors"):
            self._api.zone_sensors = {}
        if self._row_id not in self._api.zone_sensors:
            self._api.zone_sensors[self._row_id] = {'filare': {}, 'radio': {}}
        
        # Device info: collega la zona al device filari o radio
        if self._zone_type == "Filare":
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{self._row_id}_filari")},
                name="Zone Filari",
                model=f"{centrale_name} - {self._centrale_id}",
                configuration_url=MANUFACTURER_URL,
                via_device=(DOMAIN, self._row_id),
            )

            self._api.zone_sensors[self._row_id]['filare'][self._zone_number] = self
        elif self._zone_type == "Radio":
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{self._row_id}_radio")},
                name="Zone Radio",
                model=f"{centrale_name} - {self._centrale_id}",
                configuration_url=MANUFACTURER_URL,
                via_device=(DOMAIN, self._row_id),
            )
            self._api.zone_sensors[self._row_id]['radio'][self._zone_number] = self

    @property
    def is_on(self):
        # Per le zone filari, lo stato è quello di "Ingresso Aperto"
        if self._zone_type == "Filare":
            return bool(self._attr_extra_state_attributes.get('Ingresso Aperto'))
        elif self._zone_type == "Radio":
            # Per le radio, lo stato è "Ingresso Allarme"
            return bool(self._attr_extra_state_attributes.get('Ingresso Allarme'))
    
    #@property
    #def icon(self):
    #    return "mdi:motion-sensor" if self.is_on else "mdi:motion-sensor-off"

    def safe_update(self):
        """Aggiorna lo stato dell'entità solo se è registrata in Home Assistant."""
        if getattr(self, "hass", None) is not None:
            self.async_write_ha_state()
        else:
            _LOGGER.debug(f"Entità {self._attr_unique_id} non registrata: aggiornamento ignorato.")

    def update_attributes(self, zone_type, attributes):
        if not attributes:
            attributes = {}
        
        # Flag per verificare se c'è stato un cambio di allarme
        alarm_changed = False
        
        if zone_type == "filare":
            # Controlla se è cambiato uno stato di allarme
            old_memoria = self._attr_extra_state_attributes.get('Memoria Allarme')
            old_24h = self._attr_extra_state_attributes.get('Allarme 24h')
            old_mem24h = self._attr_extra_state_attributes.get('Memoria 24h')
            
            self._attr_extra_state_attributes['Ingresso Aperto'] = attributes.get('Ingresso Aperto', None)
            self._attr_extra_state_attributes['Ingresso Escluso'] = attributes.get('Ingresso Escluso', None)
            self._attr_extra_state_attributes['Memoria Allarme'] = attributes.get('Memoria Allarme', None)
            self._attr_extra_state_attributes['Allarme 24h'] = attributes.get('Allarme 24h', None)
            self._attr_extra_state_attributes['Memoria 24h'] = attributes.get('Memoria 24h', None)
            
            # Verifica se è cambiato qualcosa negli allarmi
            if (old_memoria != attributes.get('Memoria Allarme') or
                old_24h != attributes.get('Allarme 24h') or
                old_mem24h != attributes.get('Memoria 24h')):
                alarm_changed = True
                
        else:  # radio
            # Controlla se è cambiato uno stato di allarme
            old_memoria = self._attr_extra_state_attributes.get('Memoria Allarme')
            old_24h = self._attr_extra_state_attributes.get('Allarme 24h')
            old_mem24h = self._attr_extra_state_attributes.get('Memoria 24h')
            
            self._attr_extra_state_attributes['Allarme 24h'] = attributes.get('Allarme 24h', None)
            self._attr_extra_state_attributes['Memoria 24h'] = attributes.get('Memoria 24h', None)
            self._attr_extra_state_attributes['Ingresso Allarme'] = attributes.get('Ingresso Allarme', None)
            self._attr_extra_state_attributes['Memoria Allarme'] = attributes.get('Memoria Allarme', None)
            self._attr_extra_state_attributes['Supervisione'] = attributes.get('Supervisione', None)
            self._attr_extra_state_attributes['Batteria'] = attributes.get('Batteria', None)
            
            # Verifica se è cambiato qualcosa negli allarmi
            if (old_memoria != attributes.get('Memoria Allarme') or
                old_24h != attributes.get('Allarme 24h') or
                old_mem24h != attributes.get('Memoria 24h')):
                alarm_changed = True
        
        self.safe_update()  # Aggiorna lo stato in Home Assistant
        
        # Se è cambiato uno stato di allarme, aggiorna il sensore ultima zona
        if alarm_changed and hasattr(self._api, 'last_alarm_zone_sensor'):
            if self._row_id in self._api.last_alarm_zone_sensor:
                sensor = self._api.last_alarm_zone_sensor[self._row_id]
                if sensor:
                    try:
                        sensor.check_and_update_alarm_zones()
                    except Exception as e:
                        _LOGGER.error(f"Errore aggiornamento sensore ultima zona allarme: {e}")

class GoldCloud_BUSCommsBinarySensorEntity(CoordinatorEntity, BinarySensorEntity):
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
        self._attr_suggested_object_id = f"Centrale Lince {self._centrale_id} - {prima_lettera_maiuscola(configs.get("friendly_name", self._key))}"
        sensorName = configs.get("friendly_name", self._key)

        if system:
            accessKey = system.get("access_data", {})
            if self._key == "attivo_g1" and accessKey.get("g1", None):
                sensorName = f"G1: {accessKey.get("g1")}"
            elif self._key == "attivo_g2" and accessKey.get("g2", None):
                sensorName = f"G2: {accessKey.get("g2")}"
            elif self._key == "attivo_g3" and accessKey.get("g3", None):
                sensorName = f"G3: {accessKey.get("g3")}"
            elif self._key == "attivo_gext" and accessKey.get("gext", None):
                sensorName = f"GEXT: {accessKey.get("gext")}"

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
        """Aggiorna lo stato dell'entità solo se è registrata in Home Assistant."""
        if getattr(self, "hass", None) is not None:
            self.async_write_ha_state()
        else:
            _LOGGER.debug(f"Entità {self._attr_unique_id} non registrata: aggiornamento ignorato.")
    
    def update_values(self, value):
        _LOGGER.debug(f"Aggiornamento BUSComms Binary Sensor {self._attr_name} ({self._attr_unique_id}) con valore: {value}")
        if self._attr_device_class == BinarySensorDeviceClass.LOCK or self._attr_device_class == BinarySensorDeviceClass.BATTERY:
            # Inversione del valore per i sensori di tipo lock (G1, G2, G3, GEXT)
            # I sensori di tipo Lock segnano "Bloccato" quando il valore è True, viceversa segnano "Sbloccato"
            # I programmi G1-G2-G3-GEXT devono essere "Sbloccati" quando non sono attivi, ovvero quando non sono inseriti
            # Inversione del valore per i sensori di tipo Battery --> Home Assistant gestisce True quando batteria scarica, False quando batteria OK
            self._value = not value
        else:
            self._value = value
        self.safe_update()

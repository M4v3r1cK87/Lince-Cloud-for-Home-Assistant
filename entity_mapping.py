SENSOR_SYSTEM_KEYS = [
     "id"
    ,"id_centrale"
    ,"nome_impianto"
    ,"modello"
    ,"fw_ver"
    ,"ip"
    ,"profiles"
    ,"name"
    ,"mac"
    ,"state"
    ,"model"
    ,"brand"
    ,"owner"
    ,"goldstate"
]

SENSOR_ACCESS_KEYS = [
     "g1"
    ,"g2"
    ,"g3"
    ,"gext"
    ,"out1"
    ,"out2"
    ,"out3"
    ,"out4"
    ,"description"
    ,"notes"
    ,"todo"
    ,"create_time"
    ,"update_time"
]

BINARYSENSOR_SYSTEM_KEYS = [
     "connesso"
    ,"valid"
]

STATUSCENTRALE_MAPPING = {
    "firmwareVersion": {"entity_type": "sensor", "friendly_name": "Rel. SW Centrale"},
    "temperature": {"entity_type": "sensor", "friendly_name": "Temperatura", "device_class": "temperature", "state_class": "measurement", "unit_of_measurement": "°C"},
    "vBatt": {"entity_type": "sensor", "friendly_name": "Tensione Batteria", "device_class": "voltage", "state_class": "measurement", "unit_of_measurement": "V"},
    "vBus": {"entity_type": "sensor", "friendly_name": "Tensione Bus", "device_class": "voltage", "state_class": "measurement", "unit_of_measurement": "V"},
    "generali_1": {
        "rete_220V": {"entity_type": "binary_sensor", "friendly_name": "Rete 220V", "device_class": "power"},
        "batteria_in": {"entity_type": "binary_sensor", "friendly_name": "Stato di carica batteria di Centrale", "device_class": "battery"},
        "allarme": {"entity_type": "binary_sensor", "friendly_name": "Allarme", "device_class": "safety"},
        "servizio": {"entity_type": "binary_sensor", "friendly_name": "Servizio"},
        "guasto": {"entity_type": "binary_sensor", "friendly_name": "Guasto", "device_class": "problem"},
        "batteria_ex": {"entity_type": "binary_sensor", "friendly_name": "Stato di carica batteria esterna", "device_class": "battery"},
        "as24_in": {"entity_type": "binary_sensor", "friendly_name": "Sabotaggio Centrale", "device_class": "tamper"},
        "as": {"entity_type": "binary_sensor", "friendly_name": "Sabotaggio Allarme Ingresso", "device_class": "tamper"},
    },
    "generali_2": {
        "mem_as24_in": {"entity_type": "binary_sensor", "friendly_name": "Memoria Sabotaggio Centrale", "device_class": "tamper"},
        "mem_as_in": {"entity_type": "binary_sensor", "friendly_name": "Memoria Sabotaggio Allarme Ingresso", "device_class": "tamper"},
        "mem_24_inseritori": {"entity_type": "binary_sensor", "friendly_name": "Memoria Sabotaggio Dispositivi su BUS", "device_class": "tamper"},
        "mem_bus": {"entity_type": "binary_sensor", "friendly_name": "Memoria Sabotaggio Allarme integrità BUS", "device_class": "tamper"},
    },
    "generali_3": {
        "attivo_g1": {"entity_type": "binary_sensor", "friendly_name": "Programma G1", "device_class": "lock"},
        "attivo_g2": {"entity_type": "binary_sensor", "friendly_name": "Programma G2", "device_class": "lock"},
        "attivo_g3": {"entity_type": "binary_sensor", "friendly_name": "Programma G3", "device_class": "lock"},
        "attivo_gext": {"entity_type": "binary_sensor", "friendly_name": "Programma GEXT", "device_class": "lock"},
        "as24_remoto": {"entity_type": "binary_sensor", "friendly_name": "Sabotaggio Dispositivi su BUS", "device_class": "tamper"},
        "as24_remoto": {"entity_type": "binary_sensor", "friendly_name": "Sabotaggio Allarme integrità BUS", "device_class": "tamper"},
        "mem_chiavefalsa": {"entity_type": "binary_sensor", "friendly_name": "Memoria Inserimento Chiave Falsa", "device_class": "tamper"},
        "mem_24_attivazione": {"entity_type": "binary_sensor", "friendly_name": "Memoria Allarme 24h", "device_class": "safety"},
    },
    "generali_4": {
        "ingressi_esclusi": {"entity_type": "binary_sensor", "friendly_name": "Ingressi Esclusi", "device_class": "safety"},
        "ingressi_aperti": {"entity_type": "binary_sensor", "friendly_name": "Ingressi Aperti", "device_class": "motion"},
        "as24": {"entity_type": "binary_sensor", "friendly_name": "Sabotaggio Ingressi", "device_class": "tamper"},
        "silenzioso": {"entity_type": "binary_sensor", "friendly_name": "Allarme Silenzioso", "device_class": "safety"},
        "tempo_in_g1g2g3": {"entity_type": "binary_sensor", "friendly_name": "Timer in ingresso G1/G2/G3", "device_class": "safety"},
        "tempo_out_g1g2g3": {"entity_type": "binary_sensor", "friendly_name": "Timer in uscita G1/G2/G3", "device_class": "safety"},
        "mem_as24_allarme": {"entity_type": "binary_sensor", "friendly_name": "Memoria Sabotaggio Ingressi", "device_class": "tamper"},
    },
    "generali_5": {
        "pronto": {"entity_type": "binary_sensor", "friendly_name": "Stato Impianto"},
        "fusibile_ven": {"entity_type": "binary_sensor", "friendly_name": "Fusibile Uscite", "device_class": "problem"},
        "pin_servizio": {"entity_type": "binary_sensor", "friendly_name": "PIN di Servizio"},
        "tempo_in_gext": {"entity_type": "binary_sensor", "friendly_name": "Timer in ingresso GEXT", "device_class": "safety"},
        "tempo_out_gext": {"entity_type": "binary_sensor", "friendly_name": "Timer in uscita GEXT", "device_class": "safety"},
    },
    "espansioni": {
        "presente0": {"entity_type": "binary_sensor", "friendly_name": "Espansione 1"},
        "presente1": {"entity_type": "binary_sensor", "friendly_name": "Espansione 2"},
        "presente2": {"entity_type": "binary_sensor", "friendly_name": "Espansione 3"},
        "presente3": {"entity_type": "binary_sensor", "friendly_name": "Espansione 4"},
        "presente4": {"entity_type": "binary_sensor", "friendly_name": "Espansione 5"},
        "tastiera_radio": {"entity_type": "binary_sensor", "friendly_name": "Espansione Radio"},
        "conflitto": {"entity_type": "binary_sensor", "friendly_name": "Conflitto Espansione Radio"},
    },
}
"""Entity mapping per Lince Europlus.

Definisce le entità da creare e come mapparle ai dati del coordinator.
Segue lo stesso pattern di euronet/entity_mapping.py per consistenza.
"""

# System keys specifiche Europlus
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
]

# Access keys Europlus
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

# Binary sensor keys Europlus
BINARYSENSOR_SYSTEM_KEYS = [
     "connesso"
    ,"valid"
]

# Status centrale mapping SPECIFICO Europlus
# Ogni entità può avere:
# - entity_type: "sensor" o "binary_sensor"
# - friendly_name: nome da visualizzare
# - device_class: classe del dispositivo (temperature, voltage, power, battery, etc.)
# - state_class: per sensori numerici (measurement)
# - unit_of_measurement: unità di misura
# - icon: icona statica
# - icon_on / icon_off: icone dinamiche per binary_sensor
# - inverted: True per invertire la logica on/off
# - entity_category: "diagnostic" o "config" per entità secondarie
STATUSCENTRALE_MAPPING = {
    "firmwareVersion": {
        "entity_type": "sensor",
        "friendly_name": "Rel. SW Centrale",
        "icon": "mdi:chip",
    },
    "temperature": {
        "entity_type": "sensor",
        "friendly_name": "Temperatura",
        "device_class": "temperature",
        "state_class": "measurement",
        "unit_of_measurement": "°C",
        "icon": "mdi:thermometer",
    },
    "vBatt": {
        "entity_type": "sensor",
        "friendly_name": "Tensione Batteria",
        "device_class": "voltage",
        "state_class": "measurement",
        "unit_of_measurement": "V",
        "icon": "mdi:current-dc",
    },
    "vBus": {
        "entity_type": "sensor",
        "friendly_name": "Tensione Bus",
        "device_class": "voltage",
        "state_class": "measurement",
        "unit_of_measurement": "V",
        "icon": "mdi:current-dc",
    },
    "generali_1": {
        "rete_220V": {
            "entity_type": "binary_sensor",
            "friendly_name": "Rete 220V",
            "device_class": "power",
            "icon_on": "mdi:power-plug",
            "icon_off": "mdi:power-plug-off",
        },
        "batteria_in": {
            "entity_type": "binary_sensor",
            "friendly_name": "Stato di carica batteria di Centrale",
            "device_class": "battery",
            "inverted": True,  # is_on=True se batteria OK (problema=False)
        },
        "allarme": {
            "entity_type": "binary_sensor",
            "friendly_name": "Allarme",
            "device_class": "safety",
            "icon_on": "mdi:alarm-light",
            "icon_off": "mdi:alarm-light-outline",
        },
        "servizio": {
            "entity_type": "binary_sensor",
            "friendly_name": "Servizio",
            "icon_on": "mdi:wrench",
            "icon_off": "mdi:wrench-outline",
        },
        "guasto": {
            "entity_type": "binary_sensor",
            "friendly_name": "Guasto",
            "device_class": "problem",
        },
        "batteria_ex": {
            "entity_type": "binary_sensor",
            "friendly_name": "Stato di carica batteria esterna",
            "device_class": "battery",
            "inverted": True,
        },
        "as24_in": {
            "entity_type": "binary_sensor",
            "friendly_name": "Sabotaggio Centrale",
            "device_class": "tamper",
        },
        "as": {
            "entity_type": "binary_sensor",
            "friendly_name": "Sabotaggio Allarme Ingresso",
            "device_class": "tamper",
        },
    },
    "generali_2": {
        "mem_as24_in": {
            "entity_type": "binary_sensor",
            "friendly_name": "Memoria Sabotaggio Centrale",
            "device_class": "tamper",
            "entity_category": "diagnostic",
        },
        "mem_as_in": {
            "entity_type": "binary_sensor",
            "friendly_name": "Memoria Sabotaggio Allarme Ingresso",
            "device_class": "tamper",
            "entity_category": "diagnostic",
        },
        "mem_24_inseritori": {
            "entity_type": "binary_sensor",
            "friendly_name": "Memoria Sabotaggio Dispositivi su BUS",
            "device_class": "tamper",
            "entity_category": "diagnostic",
        },
        "mem_bus": {
            "entity_type": "binary_sensor",
            "friendly_name": "Memoria Sabotaggio Allarme integrità BUS",
            "device_class": "tamper",
            "entity_category": "diagnostic",
        },
    },
    "generali_3": {
        "attivo_g1": {
            "entity_type": "binary_sensor",
            "friendly_name": "Programma G1",
            "device_class": "lock",
            "inverted": True,  # Programma attivo → is_on=False → "Locked"
            "icon_on": "mdi:shield-lock-open-outline",  # Invertite perché stato invertito
            "icon_off": "mdi:shield-lock",
        },
        "attivo_g2": {
            "entity_type": "binary_sensor",
            "friendly_name": "Programma G2",
            "device_class": "lock",
            "inverted": True,
            "icon_on": "mdi:shield-lock-open-outline",
            "icon_off": "mdi:shield-lock",
        },
        "attivo_g3": {
            "entity_type": "binary_sensor",
            "friendly_name": "Programma G3",
            "device_class": "lock",
            "inverted": True,
            "icon_on": "mdi:shield-lock-open-outline",
            "icon_off": "mdi:shield-lock",
        },
        "attivo_gext": {
            "entity_type": "binary_sensor",
            "friendly_name": "Programma GEXT",
            "device_class": "lock",
            "inverted": True,
            "icon_on": "mdi:shield-lock-open-outline",
            "icon_off": "mdi:shield-lock",
        },
        "as24_remoto": {
            "entity_type": "binary_sensor",
            "friendly_name": "Sabotaggio Dispositivi su BUS",
            "device_class": "tamper",
        },
        "bus_integrità": {
            "entity_type": "binary_sensor",
            "friendly_name": "Sabotaggio Allarme integrità BUS",
            "device_class": "tamper",
        },
        "mem_chiavefalsa": {
            "entity_type": "binary_sensor",
            "friendly_name": "Memoria Inserimento Chiave Falsa",
            "device_class": "tamper",
            "entity_category": "diagnostic",
        },
        "mem_24_attivazione": {
            "entity_type": "binary_sensor",
            "friendly_name": "Memoria Allarme 24h",
            "device_class": "safety",
            "entity_category": "diagnostic",
        },
    },
    "generali_4": {
        "ingressi_esclusi": {
            "entity_type": "binary_sensor",
            "friendly_name": "Ingressi Esclusi",
            "icon": "mdi:cancel",
        },
        "ingressi_aperti": {
            "entity_type": "binary_sensor",
            "friendly_name": "Ingressi Aperti",
            "device_class": "opening",
        },
        "as24": {
            "entity_type": "binary_sensor",
            "friendly_name": "Sabotaggio Ingressi",
            "device_class": "tamper",
        },
        "silenzioso": {
            "entity_type": "binary_sensor",
            "friendly_name": "Allarme Silenzioso",
            "device_class": "safety",
            "icon_on": "mdi:volume-off",
            "icon_off": "mdi:volume-high",
        },
        "tempo_in_g1g2g3": {
            "entity_type": "binary_sensor",
            "friendly_name": "Timer in ingresso G1/G2/G3",
            "icon_on": "mdi:timer-sand",
            "icon_off": "mdi:timer-sand-empty",
        },
        "tempo_out_g1g2g3": {
            "entity_type": "binary_sensor",
            "friendly_name": "Timer in uscita G1/G2/G3",
            "icon_on": "mdi:timer-sand",
            "icon_off": "mdi:timer-sand-empty",
        },
        "mem_as24_allarme": {
            "entity_type": "binary_sensor",
            "friendly_name": "Memoria Sabotaggio Ingressi",
            "device_class": "tamper",
            "entity_category": "diagnostic",
        },
    },
    "generali_5": {
        "pronto": {
            "entity_type": "binary_sensor",
            "friendly_name": "Stato Impianto",
            "icon_on": "mdi:check-circle",
            "icon_off": "mdi:alert-circle-outline",
        },
        "fusibile_ven": {
            "entity_type": "binary_sensor",
            "friendly_name": "Fusibile Uscite",
            "device_class": "problem",
        },
        "pin_servizio": {
            "entity_type": "binary_sensor",
            "friendly_name": "PIN di Servizio",
            "icon_on": "mdi:key",
            "icon_off": "mdi:key-outline",
        },
        "tempo_in_gext": {
            "entity_type": "binary_sensor",
            "friendly_name": "Timer in ingresso GEXT",
            "icon_on": "mdi:timer-sand",
            "icon_off": "mdi:timer-sand-empty",
        },
        "tempo_out_gext": {
            "entity_type": "binary_sensor",
            "friendly_name": "Timer in uscita GEXT",
            "icon_on": "mdi:timer-sand",
            "icon_off": "mdi:timer-sand-empty",
        },
    },
    "espansioni": {
        "presente0": {
            "entity_type": "binary_sensor",
            "friendly_name": "Espansione 1",
            "entity_category": "diagnostic",
            "icon": "mdi:expansion-card",
        },
        "presente1": {
            "entity_type": "binary_sensor",
            "friendly_name": "Espansione 2",
            "entity_category": "diagnostic",
            "icon": "mdi:expansion-card",
        },
        "presente2": {
            "entity_type": "binary_sensor",
            "friendly_name": "Espansione 3",
            "entity_category": "diagnostic",
            "icon": "mdi:expansion-card",
        },
        "presente3": {
            "entity_type": "binary_sensor",
            "friendly_name": "Espansione 4",
            "entity_category": "diagnostic",
            "icon": "mdi:expansion-card",
        },
        "presente4": {
            "entity_type": "binary_sensor",
            "friendly_name": "Espansione 5",
            "entity_category": "diagnostic",
            "icon": "mdi:expansion-card",
        },
        "tastiera_radio": {
            "entity_type": "binary_sensor",
            "friendly_name": "Espansione Radio",
            "entity_category": "diagnostic",
            "icon": "mdi:radio-tower",
        },
        "conflitto": {
            "entity_type": "binary_sensor",
            "friendly_name": "Conflitto Espansione Radio",
            "device_class": "problem",
            "entity_category": "diagnostic",
        },
    },
}


# ============================================================================
# ZONE CONFIGURATION
# ============================================================================

# Configurazione default per zone filari
ZONE_FILARE_CONFIG = {
    "device_class": "door",
    "icon_on": "mdi:door-open",
    "icon_off": "mdi:door-closed",
}

# Configurazione default per zone radio
ZONE_RADIO_CONFIG = {
    "device_class": "door",
    "icon_on": "mdi:door-open",
    "icon_off": "mdi:door-closed",
    # Attributi extra per zone radio
    "extra_attributes": [
        "supervisione",
        "batteria",
    ],
}
"""Entity mapping per Lince Gold.

Definisce le entità da creare e come mapparle ai dati del coordinator.
Segue lo stesso pattern di euronet/entity_mapping.py per consistenza.
"""

# System keys specifiche Gold
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

# Access keys Gold (potrebbe non avere GEXT!)
SENSOR_ACCESS_KEYS = [
     "g1"
    ,"g2"
    ,"g3"
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

# Binary sensor keys Gold
BINARYSENSOR_SYSTEM_KEYS = [
     "connesso"
    ,"valid"
]

# Status centrale mapping SPECIFICO Gold
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
    "fw_ver": {
        "entity_type": "sensor",
        "friendly_name": "Rel. SW Centrale",
        "icon": "mdi:chip",
    },
    "conn_type": {
        "entity_type": "sensor",
        "friendly_name": "Tipo di connessione",
        "icon": "mdi:connection",
    },
    "vbatt": {
        "entity_type": "sensor",
        "friendly_name": "Tensione Batteria",
        "device_class": "voltage",
        "state_class": "measurement",
        "unit_of_measurement": "V",
        "icon": "mdi:current-dc",
    }
    "corrente": {
        "entity_type": "sensor",
        "friendly_name": "Corrente",
        "device_class": "current",
        "state_class": "measurement",
        "unit_of_measurement": "A",
        "icon": "mdi:current-dc",
    },
    "stato": {
        "sabotaggio_centrale": {
            "entity_type": "binary_sensor",
            "friendly_name": "Sabotaggio Centrale",
            "device_class": "tamper",
        },
        "sabotaggio_as_esterno": {
            "entity_type": "binary_sensor",
            "friendly_name": "Sabotaggio AS Esterno",
            "device_class": "tamper",
        },
        "memoria_sabotaggio": {
            "entity_type": "binary_sensor",
            "friendly_name": "Memoria Sabotaggio",
            "device_class": "tamper",
            "entity_category": "diagnostic",
        },
        "memoria_sabotaggio_as": {
            "entity_type": "binary_sensor",
            "friendly_name": "Memoria Sabotaggio AS",
            "device_class": "tamper",
            "entity_category": "diagnostic",
        },
        "memoria_allarme_ingressi": {
            "entity_type": "binary_sensor",
            "friendly_name": "Memoria Allarme Ingressi",
            "device_class": "tamper",
            "entity_category": "diagnostic",
        },
        "memoria_sabotaggio_ingresso": {
            "entity_type": "binary_sensor",
            "friendly_name": "Memoria Sabotaggio Ingressi",
            "device_class": "tamper",
            "entity_category": "diagnostic",
        },
        "allarme_inserito": {
            "entity_type": "binary_sensor",
            "friendly_name": "Allarme inserito",
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
    },
    "alim": {
        # Questi sensori ora hanno logica corretta: TRUE = OK, FALSE = problema
        # (l'inversione avviene nel parser state_parser.py)
        "rete_220_vca": {
            "entity_type": "binary_sensor",
            "friendly_name": "Rete 220V Presente",
            "device_class": "plug",
            "icon_on": "mdi:power-plug",
            "icon_off": "mdi:power-plug-off",
        },
        "stato_batteria_interna": {
            "entity_type": "binary_sensor",
            "friendly_name": "Batteria Interna OK",
            "device_class": "battery",
            "inverted": True,  # is_on=True se batteria OK (problema=False)
        },
        "fusibile": {
            "entity_type": "binary_sensor",
            "friendly_name": "Fusibile Uscite OK",
            "device_class": "plug",
        },
        "stato_batteria_esterna": {
            "entity_type": "binary_sensor",
            "friendly_name": "Batteria Esterna OK",
            "device_class": "battery",
            "inverted": True,
        },
        "presenza_batteria_interna": {
            "entity_type": "binary_sensor",
            "friendly_name": "Batteria Interna Presente",
            "device_class": "battery",
        },
        # Gli allarmi hanno logica normale: TRUE = allarme attivo
        "allarme_a": {
            "entity_type": "binary_sensor",
            "friendly_name": "Allarme A",
            "device_class": "safety",
            "icon_on": "mdi:alarm-light",
            "icon_off": "mdi:alarm-light-outline",
        },
        "allarme_k": {
            "entity_type": "binary_sensor",
            "friendly_name": "Allarme K",
            "device_class": "safety",
            "icon_on": "mdi:alarm-light",
            "icon_off": "mdi:alarm-light-outline",
        },
        "allarme_tecnologico": {
            "entity_type": "binary_sensor",
            "friendly_name": "Allarme Tecnologico",
            "device_class": "safety",
            "icon_on": "mdi:alarm-light",
            "icon_off": "mdi:alarm-light-outline",
        },
    },
    "uscite": {
        "uscita1": {
            "entity_type": "binary_sensor",
            "friendly_name": "Uscita 1",
            "icon_on": "mdi:toggle-switch",
            "icon_off": "mdi:toggle-switch-off-outline",
        },
        "uscita2": {
            "entity_type": "binary_sensor",
            "friendly_name": "Uscita 2",
            "icon_on": "mdi:toggle-switch",
            "icon_off": "mdi:toggle-switch-off-outline",
        },
        "uscita3": {
            "entity_type": "binary_sensor",
            "friendly_name": "Uscita 3",
            "icon_on": "mdi:toggle-switch",
            "icon_off": "mdi:toggle-switch-off-outline",
        },
        "uscita4": {
            "entity_type": "binary_sensor",
            "friendly_name": "Uscita 4",
            "icon_on": "mdi:toggle-switch",
            "icon_off": "mdi:toggle-switch-off-outline",
        },
        "uscita5": {
            "entity_type": "binary_sensor",
            "friendly_name": "Uscita 5",
            "icon_on": "mdi:toggle-switch",
            "icon_off": "mdi:toggle-switch-off-outline",
        },
        "elettroserratura": {
            "entity_type": "binary_sensor",
            "friendly_name": "Elettroserratura",
            "icon_on": "mdi:lock-open",
            "icon_off": "mdi:lock",
        },
        "sirena_interna": {
            "entity_type": "binary_sensor",
            "friendly_name": "Sirena Interna",
            "device_class": "tamper",
            "icon_on": "mdi:bell-ring",
            "icon_off": "mdi:bell-outline",
        },
        "sirena_esterna": {
            "entity_type": "binary_sensor",
            "friendly_name": "Sirena Esterna",
            "device_class": "tamper",
            "icon_on": "mdi:bell-ring",
            "icon_off": "mdi:bell-outline",
        },
    },
    "wifi": {
        "connesso": {
            "entity_type": "binary_sensor",
            "friendly_name": "Wifi connesso",
            "device_class": "connectivity",
            "icon_on": "mdi:wifi",
            "icon_off": "mdi:wifi-off",
        },
        "configurato": {
            "entity_type": "binary_sensor",
            "friendly_name": "Wifi configurato",
            "icon_on": "mdi:wifi-check",
            "icon_off": "mdi:wifi-cancel",
        },
        "errore": {
            "entity_type": "binary_sensor",
            "friendly_name": "Wifi errore",
            "device_class": "problem",
        },
    },
    "prog": {
        "g1": {
            "entity_type": "binary_sensor",
            "friendly_name": "Programma G1",
            "device_class": "lock",
            "inverted": True,  # Programma attivo → is_on=False → "Locked"
            "icon_on": "mdi:shield-lock-open-outline",  # Invertite perché stato invertito
            "icon_off": "mdi:shield-lock",
        },
        "g2": {
            "entity_type": "binary_sensor",
            "friendly_name": "Programma G2",
            "device_class": "lock",
            "inverted": True,
            "icon_on": "mdi:shield-lock-open-outline",
            "icon_off": "mdi:shield-lock",
        },
        "g3": {
            "entity_type": "binary_sensor",
            "friendly_name": "Programma G3",
            "device_class": "lock",
            "inverted": True,
            "icon_on": "mdi:shield-lock-open-outline",
            "icon_off": "mdi:shield-lock",
        },
    },
    "ingr": {
        "g1_aperto": {
            "entity_type": "binary_sensor",
            "friendly_name": "Programma G1 Aperto",
            "device_class": "opening",
        },
        "g2_aperto": {
            "entity_type": "binary_sensor",
            "friendly_name": "Programma G2 Aperto",
            "device_class": "opening",
        },
        "g3_aperto": {
            "entity_type": "binary_sensor",
            "friendly_name": "Programma G3 Aperto",
            "device_class": "opening",
        },
        "supervisione_ingressi": {
            "entity_type": "binary_sensor",
            "friendly_name": "Supervisione Ingressi",
            "entity_category": "diagnostic",
            "icon": "mdi:eye",
        },
        "guasto_ingressi_radio": {
            "entity_type": "binary_sensor",
            "friendly_name": "Guasto Ingressi Radio",
            "device_class": "problem",
        },
        "sabotaggio_ingressi": {
            "entity_type": "binary_sensor",
            "friendly_name": "Sabotaggio Ingressi",
            "device_class": "tamper",
        },
    },
    "bus": {
        "tamper_bus": {
            "entity_type": "binary_sensor",
            "friendly_name": "Tamper BUS",
            "device_class": "tamper",
        },
        "dispositivo_bus_intruso": {
            "entity_type": "binary_sensor",
            "friendly_name": "Dispositivo BUS Intruso",
            "device_class": "tamper",
        },
        "sabotaggio_hw_bus": {
            "entity_type": "binary_sensor",
            "friendly_name": "Sabotaggio HW BUS",
            "device_class": "tamper",
        },
        "guasto_bus": {
            "entity_type": "binary_sensor",
            "friendly_name": "Guasto BUS",
            "device_class": "problem",
        },
    },
}
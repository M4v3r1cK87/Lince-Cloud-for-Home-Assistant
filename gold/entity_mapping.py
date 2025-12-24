"""Entity mapping per Lince Gold."""

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
STATUSCENTRALE_MAPPING = {
    "fw_ver": {"entity_type": "sensor", "friendly_name": "Rel. SW Centrale"},
    "conn_type": {"entity_type": "sensor", "friendly_name": "Tipo di connessione"},
    "vbatt": {"entity_type": "sensor", "friendly_name": "Tensione Batteria", "device_class": "voltage", "state_class": "measurement", "unit_of_measurement": "V"},
    "corrente": {"entity_type": "sensor", "friendly_name": "Corrente", "device_class": "current", "state_class": "measurement", "unit_of_measurement": "A"},
    "stato": {
        "sabotaggio_centrale": {"entity_type": "binary_sensor", "friendly_name": "Sabotaggio Centrale", "device_class": "tamper"},
        "sabotaggio_as_esterno": {"entity_type": "binary_sensor", "friendly_name": "Sabotaggio AS Esterno", "device_class": "tamper"},
        "memoria_sabotaggio": {"entity_type": "binary_sensor", "friendly_name": "Memoria Sabotaggio", "device_class": "tamper"},
        "memoria_sabotaggio_as": {"entity_type": "binary_sensor", "friendly_name": "Memoria Sabotaggio AS", "device_class": "tamper"},
        "memoria_allarme_ingressi": {"entity_type": "binary_sensor", "friendly_name": "Memoria Allarme Ingressi", "device_class": "tamper"},
        "memoria_sabotaggio_ingresso": {"entity_type": "binary_sensor", "friendly_name": "Memoria Sabotaggio Ingressi", "device_class": "tamper"},
        "allarme_inserito": {"entity_type": "binary_sensor", "friendly_name": "Allarme inserito", "device_class": "safety"},
        "servizio": {"entity_type": "binary_sensor", "friendly_name": "Servizio"},
    },
    "alim": {
        # Questi sensori ora hanno logica corretta: TRUE = OK, FALSE = problema
        # (l'inversione avviene nel parser state_parser.py)
        "rete_220_vca": {"entity_type": "binary_sensor", "friendly_name": "Rete 220V Presente", "device_class": "plug"},
        "stato_batteria_interna": {"entity_type": "binary_sensor", "friendly_name": "Batteria Interna OK", "device_class": "battery"},
        "fusibile": {"entity_type": "binary_sensor", "friendly_name": "Fusibile Uscite OK", "device_class": "plug"},
        "stato_batteria_esterna": {"entity_type": "binary_sensor", "friendly_name": "Batteria Esterna OK", "device_class": "battery"},
        "presenza_batteria_interna": {"entity_type": "binary_sensor", "friendly_name": "Batteria Interna Presente", "device_class": "battery"},
        # Gli allarmi hanno logica normale: TRUE = allarme attivo
        "allarme_a": {"entity_type": "binary_sensor", "friendly_name": "Allarme A", "device_class": "safety"},
        "allarme_k": {"entity_type": "binary_sensor", "friendly_name": "Allarme K", "device_class": "safety"},
        "allarme_tecnologico": {"entity_type": "binary_sensor", "friendly_name": "Allarme Tecnologico", "device_class": "safety"},
    },
    "uscite": {
        "uscita1": {"entity_type": "binary_sensor", "friendly_name": "Uscita 1"},
        "uscita2": {"entity_type": "binary_sensor", "friendly_name": "Uscita 2"},
        "uscita3": {"entity_type": "binary_sensor", "friendly_name": "Uscita 3"},
        "uscita4": {"entity_type": "binary_sensor", "friendly_name": "Uscita 4"},
        "uscita5": {"entity_type": "binary_sensor", "friendly_name": "Uscita 5"},
        "elettroserratura": {"entity_type": "binary_sensor", "friendly_name": "Elettroserratura"},
        "sirena_interna": {"entity_type": "binary_sensor", "friendly_name": "Sirena Interna", "device_class": "tamper"},
        "sirena_esterna": {"entity_type": "binary_sensor", "friendly_name": "Sirena Esterna", "device_class": "tamper"},
    },
    "wifi": {
        "connesso": {"entity_type": "binary_sensor", "friendly_name": "Wifi connesso", "device_class": "connectivity"},
        "configurato": {"entity_type": "binary_sensor", "friendly_name": "Wifi configurato"},
        "errore": {"entity_type": "binary_sensor", "friendly_name": "Wifi errore", "device_class": "problem"},
    },
    "prog": {
        "g1": {"entity_type": "binary_sensor", "friendly_name": "Programma G1", "device_class": "lock"},
        "g2": {"entity_type": "binary_sensor", "friendly_name": "Programma G2", "device_class": "lock"},
        "g3": {"entity_type": "binary_sensor", "friendly_name": "Programma G3", "device_class": "lock"},
    },
    "ingr": {
        "g1_aperto": {"entity_type": "binary_sensor", "friendly_name": "Programma G1 Aperto", "device_class": "safety"},
        "g2_aperto": {"entity_type": "binary_sensor", "friendly_name": "Programma G2 Aperto", "device_class": "safety"},
        "g3_aperto": {"entity_type": "binary_sensor", "friendly_name": "Programma G3 Aperto", "device_class": "safety"},
        "supervisione_ingressi": {"entity_type": "binary_sensor", "friendly_name": "Supervisione Ingressi"},
        "guasto_ingressi_radio": {"entity_type": "binary_sensor", "friendly_name": "Guasto Ingressi Radio", "device_class": "problem"},
        "sabotaggio_ingressi": {"entity_type": "binary_sensor", "friendly_name": "Sabotaggio Ingressi", "device_class": "tamper"},
    },
    "bus": {
        "tamper_bus": {"entity_type": "binary_sensor", "friendly_name": "Tamper BUS", "device_class": "tamper"},
        "dispositivo_bus_intruso": {"entity_type": "binary_sensor", "friendly_name": "Dispositivo BUS Intruso", "device_class": "tamper"},
        "sabotaggio_hw_bus": {"entity_type": "binary_sensor", "friendly_name": "Sabotaggio HW BUS", "device_class": "tamper"},
        "guasto_bus": {"entity_type": "binary_sensor", "friendly_name": "Guasto BUS", "device_class": "problem"},
    },
}
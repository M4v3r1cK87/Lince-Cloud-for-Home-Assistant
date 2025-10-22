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
    # TODO: Da implementare con le specifiche Gold
    # Per ora vuoto o minimo
}
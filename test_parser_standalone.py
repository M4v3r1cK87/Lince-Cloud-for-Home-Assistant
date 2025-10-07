
from europlusParser_standalone import europlusParser
from byte_utils import ByteUtils
import json

def extract_payload(raw_input):
    """
    Estrae la parte numerica da una stringa socket.io come:
    '42/socket,["onStatus","2,35,0,..."]'
    """
    try:
        start = raw_input.find('"onStatus","') + len('"onStatus","')
        end = raw_input.find('"]', start)
        payload_str = raw_input[start:end]
        payload = [int(x) for x in payload_str.split(',') if x.strip().isdigit()]
        return payload
    except Exception as e:
        print(f"Errore nell'estrazione del payload: {e}")
        return []

def parse_store_zone_names(store_dict):
    """
    Prende in input il dict 'store' (chiavi stringa, valori stringa di numeri separati da virgola)
    Restituisce il dict {'filare': [...], 'radio': [...]}
    """
    # Ordina le chiavi numeriche e crea la lista di array di int
    store_payloads = []
    try:
        for i in range(0, 99):  # Solo le posizioni 0-98 sono zone
            arr_str = store_dict.get(str(i), None)
            if arr_str is not None:
                arr = [int(x) for x in arr_str.split(',')]
            else:
                arr = [0] * 19
            store_payloads.append(arr)
        return store_payloads
    except Exception as e:
        print(f"Errore nell'estrazione dello store payload: {e}")
        return []


def print_table(title, data_dict):
    print(f"\
--- {title} ---")
    for key, value in data_dict.items():
        print(f"{key:<25}: {value}")

def print_ingressi_filari_table(ingressi, zoneNames):
    print("\
--- Stato Ingressi Filari ---")
    print("Num | Ingresso Aperto | Ingresso Escluso | Memoria Allarme | Allarme 24h | Memoria 24h")
    for ingresso in ingressi:
        zoneName = f"Zona {ingresso['numero']}"
        if zoneNames and 'filare' in zoneNames and len(zoneNames['filare']) >= ingresso['numero']:
            zoneName = zoneNames['filare'][ingresso['numero'] - 1]
        print(f"{zoneName} | {'A' if ingresso['filari_oi'] else '-'} | {'E' if ingresso['filari_esclusioni'] else '-'} | {'M' if ingresso['filari_memorie'] else '-'} | {'A' if ingresso['filari_oi24'] else '-'} | {'M' if ingresso['filari_memorie24'] else '-'}")

def print_ingressi_radio_table(ingressi, zoneNames):
    print("\
--- Stato Ingressi Radio ---")
    print("Num | Allarme 24h | Memoria 24h | Ingresso Allarme | Memoria Allarme | Supervisione | Batteria")
    i = 0
    for ingresso in ingressi:
        zoneName = f"Zona {ingresso['numero']}"
        if zoneNames and 'radio' in zoneNames and len(zoneNames['radio']) >= ingresso['numero']:
            zoneName = zoneNames['radio'][ingresso['numero'] - 1]
        print(f"{zoneName} | {'A' if ingresso['as_radio'] else '-'} | {'M' if ingresso['mem_as_radio'] else '-'} | {'A' if ingresso['oi_radio'] else '-'} | {'M' if ingresso['mem_oi_radio'] else '-'} | {'S' if ingresso['supervisioni_radio'] else '-'} | {'S' if ingresso['lo_batt_radio'] else '-'}")
        i += 1

def print_espansioni_table(espansioni):
    print("\
--- Espansioni ---")
    for key, value in espansioni.items():
        print(f"{key:<20}: {'SI' if value else 'NO'}")

if __name__ == "__main__":
    parser = europlusParser()
    store_dict = None
    zoneNames = None
    print("Inserisci il messaggio socket.io con il byte array:")
    raw_input_str = input().strip()

    payload = extract_payload(raw_input_str)
    if not payload:
        print("Payload non valido o vuoto.")
        exit()

    print("Inserisci il dictionary store:")
    raw_input_str = input().strip()
    if raw_input_str:
        store_dict = json.loads(raw_input_str)
        #payload_store = parse_store_zone_names(store_dict)
        if not store_dict:
            print("Payload store non valido o vuoto.")
            exit()

    if payload:
        parser.parse(payload)

    if store_dict:
        zoneNames = parser.parse_store_zone(store_dict)
        #keysName = parser.parse_store_keys(payload_store)

    print_table("Stato Centrale", {
        "Modello centrale": parser.get_value('modello_centrale'),
        "Sub modello centrale": parser.get_value('submodellocentrale'),
        "Firmware Centrale": parser.get_firmware_version(),
        "Tensione batteria (V)": parser.get_vbatt(),
        "Tensione BUS (V)": parser.get_vbus(),
        "Temperatura (°C)": parser.get_temperature(),
        "N. Chiavi": parser.get_value('nchiavi'),
        "N. Radio": parser.get_value('nradio'),
        "Data e ora": parser.get_datetime(),
        "ID Tastiera": parser.get_idtastiera()
    })

    # Stampa tutte le sezioni implementate nel parser
    #if hasattr(parser, 'generali_2'):
    print_table("Generali 1", parser.get_generali_1())
    #if hasattr(parser, 'generali_2'):
    print_table("Generali 2", parser.get_generali_2())
    #if hasattr(parser, 'generali_3'):
    print_table("Generali 3", parser.get_generali_3())
    #if hasattr(parser, 'generali_4'):
    print_table("Generali 4", parser.get_generali_4())
    #if hasattr(parser, 'generali_5'):
    print_table("Generali 5", parser.get_generali_5())
    #if hasattr(parser, 'attivazioni'):
    print_table("Attivazioni", parser.get_attivazioni())
    #if hasattr(parser, 'impedimenti'):
    print_table("Pag0 Impedimenti", parser.get_pag0_impedimenti_1())
    #if hasattr(parser, 'pag0_impedimenti_2'):
    print_table("pag0_impedimenti_2", parser.get_pag0_impedimenti_2())
    #if hasattr(parser, 'isTeknoxAuthorized'):
    print_table("Teknox Authorized", parser.get_isTeknoxAuthorized())
    #if hasattr(parser, 'comandicentrale'):
    print_table("Comandi Centrale", parser.get_comandi_centrale())
    print_espansioni_table(parser.get_espansioni())

    print_ingressi_filari_table(parser.get_ingressi_filari(), zoneNames)
    print_ingressi_radio_table(parser.get_ingressi_radio(), zoneNames)

    if store_dict and zoneNames:
        print_table("Keys", {
            "Zona 1": zoneNames['filare'][0] if len(zoneNames['filare'][0]) > 0 else 'N/A',
            "Zona 2": zoneNames['filare'][1] if len(zoneNames['filare'][1]) > 0 else 'N/A',
            "Zona 3": zoneNames['filare'][2] if len(zoneNames['filare'][2]) > 0 else 'N/A',
            "Zona 4": zoneNames['filare'][3] if len(zoneNames['filare'][3]) > 0 else 'N/A',
            "Zona 5": zoneNames['filare'][4] if len(zoneNames['filare'][4]) > 0 else 'N/A',
            "Zona 6": zoneNames['filare'][5] if len(zoneNames['filare'][5]) > 0 else 'N/A',
            "Zona 7": zoneNames['filare'][6] if len(zoneNames['filare'][6]) > 0 else 'N/A',

            "Zona 8": zoneNames['filare'][7] if len(zoneNames['filare'][7]) > 0 else 'N/A',
            "Zona 9": zoneNames['filare'][8] if len(zoneNames['filare'][8]) > 0 else 'N/A',
            "Zona 10": zoneNames['filare'][9] if len(zoneNames['filare'][9]) > 0 else 'N/A',
            "Zona 11": zoneNames['filare'][10] if len(zoneNames['filare'][10]) > 0 else 'N/A',
            "Zona 12": zoneNames['filare'][11] if len(zoneNames['filare'][11]) > 0 else 'N/A',
            "Zona 13": zoneNames['filare'][12] if len(zoneNames['filare'][12]) > 0 else 'N/A',
            "Zona 14": zoneNames['filare'][13] if len(zoneNames['filare'][13]) > 0 else 'N/A',
        })
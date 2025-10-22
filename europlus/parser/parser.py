"""
Parser principale per il byte array della centrale Lince Cloud.
Tutte le chiavi sono gestite in array, ogni metodo controlla la presenza della chiave e restituisce None se non presente.

Il protocollo BUS funziona con degli array di byte posizionali (le posizioni vengono distinte con la ",").
Ad ogni posizione corrisponde un numero intero in base 10
"10,20,30,40" --> byte 1 = 10, byte 2 = 20, byte 3 = 30, byte 4 = 40
A seconda dell'informazione contenuta all'interno del byte, si può prendere il valore RAW o convertire il byte in un numero binario con la funzione get_bits
In altri casi, invece, si deve convertire il numero in stringa (nomi zona o nomi chiavi)
"""
from .byte_utils import ByteUtils
import calendar, locale

class europlusParser:
    # Lista delle chiavi, l'ordine non va assolutamente modificato, altrimenti il posizionamento dei byte darà un valore diverso
    KEYS = [
        "modello_centrale",
        "generali_1",
        "generali_2",
        "generali_3",
        "pag0_impedimenti_1",
        "pag0_impedimenti_2",
        "generali_4",
        "generali_5",
        "vbatt_L",
        "vbatt_H",
        "filari_esclusioni_0",
        "filari_esclusioni_1",
        "filari_esclusioni_2",
        "filari_esclusioni_3",
        "filari_esclusioni_4",
        "filari_oi_0",
        "filari_oi_1",
        "filari_oi_2",
        "filari_oi_3",
        "filari_oi_4",
        "filari_memorie_0",
        "filari_memorie_1",
        "filari_memorie_2",
        "filari_memorie_3",
        "filari_memorie_4",
        "filari_oi24_0",
        "filari_oi24_1",
        "filari_oi24_2",
        "filari_oi24_3",
        "filari_oi24_4",
        "filari_memorie24_0",
        "filari_memorie24_1",
        "filari_memorie24_2",
        "filari_memorie24_3",
        "filari_memorie24_4",
        "minuti",
        "ore",
        "giorno",
        "mese",
        "anno",
        "secondi",
        "nome_giorno",
        "idtastiera_L",
        "idtastiera_H",
        "pag9_impedimento_1",
        "pag9_impedimento_2",
        "pag9_impedimento_3",
        "pag9_impedimento_4",
        "pag9_impedimento_5",
        "firmware_ver_L",
        "firmware_ver_H",
        "pag10_impedimento1_1",
        "pag10_impedimento2_2",
        "pag10_impedimento3_3",
        "pag10_impedimento4_4",
        "pag10_impedimento5_5",
        "pag11_impedimento11_1",
        "pag11_impedimento11_2",
        "pag11_impedimento11_3",
        "pag11_impedimento11_4",
        "pag11_impedimento11_5",
        "attivazione",
        "oi_radio_0",
        "oi_radio_1",
        "oi_radio_2",
        "oi_radio_3",
        "oi_radio_4",
        "oi_radio_5",
        "oi_radio_6",
        "oi_radio_7",
        "as_radio_0",
        "as_radio_1",
        "as_radio_2",
        "as_radio_3",
        "as_radio_4",
        "as_radio_5",
        "as_radio_6",
        "as_radio_7",
        "mem_oi_radio_0",
        "mem_oi_radio_1",
        "mem_oi_radio_2",
        "mem_oi_radio_3",
        "mem_oi_radio_4",
        "mem_oi_radio_5",
        "mem_oi_radio_6",
        "mem_oi_radio_7",
        "mem_as_radio_0",
        "mem_as_radio_1",
        "mem_as_radio_2",
        "mem_as_radio_3",
        "mem_as_radio_4",
        "mem_as_radio_5",
        "mem_as_radio_6",
        "mem_as_radio_7",
        "lo_batt_radio_0",
        "lo_batt_radio_1",
        "lo_batt_radio_2",
        "lo_batt_radio_3",
        "lo_batt_radio_4",
        "lo_batt_radio_5",
        "lo_batt_radio_6",
        "lo_batt_radio_7",
        "supervisioni_radio_0",
        "supervisioni_radio_1",
        "supervisioni_radio_2",
        "supervisioni_radio_3",
        "supervisioni_radio_4",
        "supervisioni_radio_5",
        "supervisioni_radio_6",
        "supervisioni_radio_7",
        "isTeknoxAuthorized",
        "comandicentrale",
        "celsius_H",
        "celsius_L",
        "vbus_H",
        "vbus_L",
        "checksum1",
        "checksum2",
        "espansioni",
        "submodellocentrale",
        "nchiavi",
        "nradio"
    ]

    def __init__(self, payload):
        self.utils = ByteUtils()
        self.data = {}
        if payload is not None:
            self.parse(payload)

    def parse(self, payload):
        self.data = {}
        self._payload = [int(x) for x in payload.split(',') if x.strip().isdigit()]
        for i, key in enumerate(self.KEYS):
            self.data[key] = self._payload[i] if i < len(self._payload) else None
        return self.data

    def __get_value(self, key):
        return self.data.get(key, None)

    def get_temperature(self):
        if self.data.get('celsius_H') is None or self.data.get('celsius_L') is None:
            return None
        return round((((self.data['celsius_H'] << 8) + self.data['celsius_L']) - 2000) / 12, 2)

    def get_vbus(self):
        if self.data.get('vbus_H') is None or self.data.get('vbus_L') is None:
            return None
        return round(((self.data['vbus_H'] << 8) + self.data['vbus_L']) / 183, 2)

    def get_vbatt(self):
        if self.data.get('vbatt_H') is None or self.data.get('vbatt_L') is None:
            return None
        return round(((self.data['vbatt_H'] << 8) + self.data['vbatt_L']) / 46.4, 2)

    def get_firmware_version(self):
        if self.data.get('firmware_ver_L') is None or self.data.get('firmware_ver_H') is None:
            return None
        return f"{self.data['firmware_ver_L']}.{str(self.data['firmware_ver_H']).zfill(2)}"

    def get_datetime(self):
        if  self.data.get('nome_giorno') is None or self.data.get('giorno') is None or self.data.get('mese') is None or self.data.get('anno') is None or self.data.get('ore') is None or self.data.get('minuti') is None or self.data.get('secondi') is None:
            return None
        locale.setlocale(locale.LC_TIME, '')
        calendar.setfirstweekday(calendar.MONDAY)
        nome_giorno = calendar.day_name[self.data['nome_giorno']]
        return f"{nome_giorno} {str(self.data['giorno']).zfill(2)}/{str(self.data['mese']).zfill(2)}/20{str(self.data['anno']).zfill(2)}", f"{str(self.data['ore']).zfill(2)}:{str(self.data['minuti']).zfill(2)}:{str(self.data['secondi']).zfill(2)}"

    def get_idtastiera(self):
        if self.data.get('idtastiera_L') is None or self.data.get('idtastiera_H') is None:
            return None
        return f"{self.data['idtastiera_L']}.{str(self.data['idtastiera_H']).zfill(2)}"
    
    def __parseZoneDetails(self, zoneType, arr):
        """
        Parser compatto per un frame 'ingresso filare' (22 byte attesi).
        - Decodifica anche il NOME ZONA dai byte 4..19 (ASCII con padding)
        - Usa ByteUtils.get_bits(n, p[, q]) del tuo progetto:
          - bit singolo: get_bits(n, pos)            -> int(0|1)
          - campo di N bit: get_bits(n, start, N)    -> int
        Mapping:
          Byte 0:  allarmi(bits 0..3), escluso(b4), parzializzabile(b5), ronda(b6)
          Byte 1:  ritardato(b0), flag bilanciato(b1), test(b2), percorso(b3),
                   a_all_uno(b4), fuoco(b5), campanello(b6), silenzioso(b7)
          Byte 2:  g1(b0), g2(b1), g3(b2), gext(b3), tempo_trigger(b4:0=300/1=500),
                   h24(b5), doppio_bilanciato_bit(b6), elettroserratura(b7)
          Byte 3:  k_all_due(b0), logica(b1:0=AND/1=OR)
          Byte 4..19: NOME ZONA (16 char, padding spazi/eventuali caratteri)
          Byte 20: tempo_ingresso (s)
          Byte 21: tempo_uscita  (s)
        """
        utils = self.utils

        # --- Nome zona (ASCII dai byte 4..19) ---
        nome_zona = utils.array_int_to_string(arr[4:20]).replace('-', '').strip()

        if zoneType == "filare":
            gv = lambda i: arr[i] if i < len(arr) else 0
            b0, b1, b2, b3 = gv(0), gv(1), gv(2), gv(3)

            # Allarmi: 0 => "Infinito", 1..15 => numero (nibble 0..3 del byte 0)
            numero_allarmi = utils.get_bits(b0, 0, 4)  # attenzione: qui q=4 è la LUNGHEZZA
            if numero_allarmi == 0:
                numero_allarmi = "Infiniti"

            # Tipo di ingresso
            if utils.get_bits(b1, 1) == 0:
                tipo_ingresso = "NC"
            else:
                tipo_ingresso = "Doppio Bilanciato" if utils.get_bits(b2, 6) else "Bilanciato"

            # Tempo trigger e logica
            tempo_trigger_ms = 500 if utils.get_bits(b2, 4) else 300
            logica = "OR" if utils.get_bits(b3, 1) else "AND"

            return {
                "Nome": nome_zona,
                "Tipo Ingresso": tipo_ingresso,          # "NC" | "Bilanciato" | "Doppio bilanciato"
                "Tempo di Trigger (msec)": tempo_trigger_ms,    # 300 | 500
                "Logica": logica,                        # "AND" | "OR"
                "Numero Allarmi": numero_allarmi,        # 0..15 (0 = Infinito)

                "Tempo Ingresso (sec)": gv(20) if len(arr) > 20 else None,
                "Tempo Uscita (sec)":  gv(21) if len(arr) > 21 else None,

                # Programmi
                "Programma G1": bool(utils.get_bits(b2, 0)),      # Zona associata al programma G1
                "Programma G2": bool(utils.get_bits(b2, 1)),      # Zona associata al programma G2
                "Programma G3": bool(utils.get_bits(b2, 2)),      # Zona associata al programma G3
                "Programma GEXT": bool(utils.get_bits(b2, 3)),    # Zona associata al programma GEXT

                # Flag vari
                "Escluso": bool(utils.get_bits(b0, 4)), 
                "Parzializzabile": bool(utils.get_bits(b0, 5)),
                "Ronda": bool(utils.get_bits(b0, 6)),

                "Ritardato": bool(utils.get_bits(b1, 0)),
                "Test": bool(utils.get_bits(b1, 2)),
                "Percorso": bool(utils.get_bits(b1, 3)),
                "A (all. 1)": bool(utils.get_bits(b1, 4)),
                "Fuoco": bool(utils.get_bits(b1, 5)),
                "Campanello": bool(utils.get_bits(b1, 6)),
                "Silenzioso": bool(utils.get_bits(b1, 7)),

                "24h": bool(utils.get_bits(b2, 5)),
                "Elettroserratura": bool(utils.get_bits(b2, 7)),
                "K (all. 2)": bool(utils.get_bits(b3, 0)),
            }
        else:
            return {"Nome": nome_zona}

    def parseZones(self, zone_payloads, num_filari=35, num_radio=64):
        """
        zone_payloads: lista di array di byte, uno per ogni zona (come ricevuto dalla centrale)
        Ritorna: dict con 'filare' (0-34) e 'radio' (35-98)
        """
        filare = []
        radio = []

        # Filari (35 Zone totali): posizioni 0-34
        for i in range(0, num_filari):
            arr_str = zone_payloads.get(str(i), None)
            if arr_str is not None:
                arr = [int(x) for x in arr_str.split(',')]
            else:
                arr = [0] * 19
            
            filare.append(self.__parseZoneDetails("filare", arr))

        # Radio (64 zone totali): posizioni 35-98
        for i in range(35, num_radio-1):            
            arr_str = zone_payloads.get(str(i), None)
            if arr_str is not None:
                arr = [int(x) for x in arr_str.split(',')]
            else:
                arr = [0] * 19

            radio.append(self.__parseZoneDetails("radio", arr))

        return {'filare': filare, 'radio': radio}
    
    def parse_keysName(self, zone_payloads):
        """
        zone_payloads: lista di array di byte, uno per ogni zona (come ricevuto dalla centrale)
        Ritorna: dict con i nomi delle chiavi registrate
        """
        keys = []
        # Chiavi (128 chiavi/codici totali): posizioni 99-227
        for i in range(99, 227):
            arr_str = zone_payloads.get(str(i), None)
            if arr_str is not None:
                arr = [int(x) for x in arr_str.split(',')]
            else:
                arr = [0] * 19
            name = self.utils.array_int_to_string(arr[4:])
            name = name.replace('-', '').strip()
            keys.append(f"{name}")

        return keys

    def get_generali_1(self):
        data = self.data.get('generali_1', 0)
        return {
            'rete_220V': bool(self.utils.get_bits(data, 0)),                # Rete 220V - 1: Presente, 0: Assente
            'batteria_in': bool(self.utils.get_bits(data, 1)),              # Batteria interna - 1: Assente, 0: Presente
            'allarme': bool(self.utils.get_bits(data, 2)),
            'servizio': bool(self.utils.get_bits(data, 3)),
            'guasto': bool(self.utils.get_bits(data, 4)),
            'batteria_ex': bool(self.utils.get_bits(data, 5)),              # Batteria esterna - 1: Presente, 0: Assente
            'as24_in': bool(self.utils.get_bits(data, 6)),                  # Tamper interno - 1: Aperto, 0: Chiuso
            'as': bool(self.utils.get_bits(data, 7)),                       # Sabotaggio allarme Ingresso - 1: Presente, 0: Assente
        }

    def get_generali_2(self):
        data = self.data.get('generali_2', 0)
        return {
            'mem_as24_in': bool(self.utils.get_bits(data, 0)),              # Memoria sabotaggio centrale
            'mem_as_in': bool(self.utils.get_bits(data, 1)),                # Mamoria sabotaggio allarme ingresso
            'mem_24_inseritori': bool(self.utils.get_bits(data, 2)),        # Memoria sabotaggio dispositivi su BUS
            'mem_bus': bool(self.utils.get_bits(data, 3)),                  # Memoria allarme integrità BUS
            'status': bool(self.utils.get_bits(data, 4, 4)),
        }

    def get_generali_3(self):
        data = self.data.get('generali_3', 0)
        return {
            'attivo_g1': bool(self.utils.get_bits(data, 0)),                # Attivazione programma G1 - 1: Attivo, 0: Non attivo
            'attivo_g2': bool(self.utils.get_bits(data, 1)),                # Attivazione programma G2 - 1: Attivo, 0: Non attivo
            'attivo_g3': bool(self.utils.get_bits(data, 2)),                # Attivazione programma G3 - 1: Attivo, 0: Non attivo
            'attivo_gext': bool(self.utils.get_bits(data, 3)),              # Attivazione programma GEXT - 1: Attivo, 0: Non attivo
            'as24_remoto': bool(self.utils.get_bits(data, 4)),              # Sabotaggio dispositivi su BUS
            'bus': bool(self.utils.get_bits(data, 5)),                      # Allarme integrità BUS
            'mem_chiavefalsa': bool(self.utils.get_bits(data, 6)),
            'mem_24_attivazione': bool(self.utils.get_bits(data, 7)),
        }

    def get_generali_4(self):
        data = self.data.get('generali_4', 0)
        return {
            'ingressi_esclusi': bool(self.utils.get_bits(data, 0)),         # Ingressi esclusi
            'ingressi_aperti': bool(self.utils.get_bits(data, 1)),          # Ingressi aperti
            'as24': bool(self.utils.get_bits(data, 2)),                     # Sabotaggio ingressi
            'silenzioso': bool(self.utils.get_bits(data, 3)),
            'tempo_in_g1g2g3': bool(self.utils.get_bits(data, 4)),          # Attivazione timer in ingresso programmi G1/G2/G3 - 1: Presente quando è scattato il timer in ingresso (zona allarmata e aperta), 0: Assente
            'led_on': bool(self.utils.get_bits(data, 5)),
            'tempo_out_g1g2g3': bool(self.utils.get_bits(data, 6)),         # Attivazione timer in uscita programmi G1/G2/G3- 1: Presente quando è stato inserito l'allarme ed è partito il temporizzatore in uscita, 0: Assente
            'mem_as24_allarme': bool(self.utils.get_bits(data, 7)),         # Memoria sabotaggio ingressi
        }

    def get_generali_5(self):
        data = self.data.get('generali_5', 0)
        return {
            'chiave_base': bool(self.utils.get_bits(data, 0)),
            'red_on': bool(self.utils.get_bits(data, 1)),
            'at_on': bool(self.utils.get_bits(data, 2)),
            'pronto': bool(self.utils.get_bits(data, 3)),                   # Stato impianto - 1: Nessun guasto di centrale, 0: Presenza di guasto 
            'fusibile_ven': bool(self.utils.get_bits(data, 4)),             # Fusibile Uscite
            'pin_servizio': bool(self.utils.get_bits(data, 5)),
            'tempo_in_gext': bool(self.utils.get_bits(data, 6)),            # Attivazione timer in ingresso programma GEXT - 1: Presente quando è scattato il timer in ingresso (zona allarmata e aperta), 0: Assente
            'tempo_out_gext': bool(self.utils.get_bits(data, 7)),           # Attivazione timer in uscita programma GEXT- 1: Presente quando è stato inserito l'allarme ed è partito il temporizzatore in uscita, 0: Assente
        }

    def get_pag0_impedimenti_1(self):
        data = self.data.get('pag0_impedimenti_1', 0)
        return {
            'g1': bool(self.utils.get_bits(data, 0)),
            'g2': bool(self.utils.get_bits(data, 1)),
            'g3': bool(self.utils.get_bits(data, 2)),
            'gext': bool(self.utils.get_bits(data, 3)),
            'g1_esclusi': bool(self.utils.get_bits(data, 4)),
            'g2_esclusi': bool(self.utils.get_bits(data, 5)),
            'g3_esclusi': bool(self.utils.get_bits(data, 6)),
            'gext_esclusi': bool(self.utils.get_bits(data, 7)),
        }

    def get_pag0_impedimenti_2(self):
        data = self.data.get('pag0_impedimenti_2', 0)
        return {
            'blocco_g1': bool(self.utils.get_bits(data, 0)),
            'blocco_g2': bool(self.utils.get_bits(data, 1)),
            'blocco_g3': bool(self.utils.get_bits(data, 2)),
            'blocco_gext': bool(self.utils.get_bits(data, 3)),
            'stato_na': bool(self.utils.get_bits(data, 4)),
            'eeprom_radio_ok': bool(self.utils.get_bits(data, 5)),
            'manomissione': bool(self.utils.get_bits(data, 6)),
            'ingressi_immediati': bool(self.utils.get_bits(data, 7)),       # Quando si preme il tasto "R" sulla tastiera --> Gli ingressi ritardati diventano immediati
        }

    def get_espansioni(self):
        data = self.data.get('espansioni', 0)
        result = {
            'presente0': bool(self.utils.get_bits(data, 0)),
            'presente1': bool(self.utils.get_bits(data, 1)),
            'presente2': bool(self.utils.get_bits(data, 2)),
            'presente3': bool(self.utils.get_bits(data, 3)),
            'presente4': bool(self.utils.get_bits(data, 4)),
            'tastiera_radio': bool(self.utils.get_bits(data, 5)),
            'conflitto': bool(self.utils.get_bits(data, 6)),
        }

        if result['tastiera_radio'] == 1:
            result['presente4'] = 0                                         # Se espansione radio è on, presente4 va a 0

        return result

    def get_attivazioni(self):
        data = self.data.get('attivazione', 0)
        return {
            'go1': bool(self.utils.get_bits(data, 0)),
            'go2': bool(self.utils.get_bits(data, 1)),
            'go3': bool(self.utils.get_bits(data, 2)),
            'goext': bool(self.utils.get_bits(data, 3)),
        }

    def get_isTeknoxAuthorized(self):
        data = self.data.get('isTeknoxAuthorized', 0)
        return {
            'auth_level': self.utils.get_bits(data, 0, 2),                  # 3 --> Installatore, 2 --> Amministratore, 1 --> Utente, 0 --> Nessuno
            'g1': bool(self.utils.get_bits(data, 2)),                       # True se programma G1 è attivabile
            'g2': bool(self.utils.get_bits(data, 3)),                       # True se programma G2 è attivabile
            'g3': bool(self.utils.get_bits(data, 4)),                       # True se programma G3 è attivabile
            'gext': bool(self.utils.get_bits(data, 5)),                     # True se programma GEXT è attivabile
            'authorized': bool(self.utils.get_bits(data, 7)),               # True se l'utente è stato autenticato tramite codice pin    
        }

    def get_comandi_centrale(self):
        data = self.data.get('comandicentrale', 0)
        return {
            'ccsi': bool(self.utils.get_bits(data, 0)),                     # Stato impianto
            'ccvt': bool(self.utils.get_bits(data, 1)),                     # Visualizzazione tamper
            'ccmc': bool(self.utils.get_bits(data, 2)),                     # Memorizzazioni chiavi
            'sync_euronet_cloud': bool(self.utils.get_bits(data, 3)),       # sync centrale -> cloud vBuffer[123] i |= 8, aggiunta nell'ultimo fw
        }

    def get_ingressi_filari(self, max_zones=35):
        ingressi = []
        for i in range(max_zones):  # Da 0 a 34 ci sono le posizioni degli ingressi filari, da 35 a 99 ci sono gli ingressi radio (64)
            group = i // 8
            bit = i % 8
            ingresso = {
                'numero': i + 1,
                'filari_oi': bool(self.utils.get_bits(self.data.get(f'filari_oi_{group}', 0), bit)),
                'filari_esclusioni': bool(self.utils.get_bits(self.data.get(f'filari_esclusioni_{group}', 0), bit)),
                'filari_memorie': bool(self.utils.get_bits(self.data.get(f'filari_memorie_{group}', 0), bit)),
                'filari_oi24': bool(self.utils.get_bits(self.data.get(f'filari_oi24_{group}', 0), bit)),
                'filari_memorie24': bool(self.utils.get_bits(self.data.get(f'filari_memorie24_{group}', 0), bit)),
            }
            ingressi.append(ingresso)
        return ingressi

    def get_ingressi_radio(self, max_zones=64):
        ingressi = []
        maxRange = 35 + max_zones   # Da 0 a 34 ci sono le posizioni degli ingressi filari, da 35 a 99 ci sono gli ingressi radio (64)
        for i in range(35, maxRange):
            group = i // 8
            bit = i % 8
            ingresso = {
                'numero': i - 34,
                'as_radio': bool(self.utils.get_bits(self.data.get(f'as_radio_{group}', 0), bit)),
                'mem_as_radio': bool(self.utils.get_bits(self.data.get(f'mem_as_radio_{group}', 0), bit)),
                'oi_radio': bool(self.utils.get_bits(self.data.get(f'oi_radio_{group}', 0), bit)),
                'mem_oi_radio': bool(self.utils.get_bits(self.data.get(f'mem_oi_radio_{group}', 0), bit)),
                'supervisioni_radio': bool(self.utils.get_bits(self.data.get(f'supervisioni_radio_{group}', 0), bit)),
                'lo_batt_radio': bool(self.utils.get_bits(self.data.get(f'lo_batt_radio_{group}', 0), bit)),
            }
            ingressi.append(ingresso)
        return ingressi


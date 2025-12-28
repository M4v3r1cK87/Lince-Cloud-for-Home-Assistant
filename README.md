# Lince Alarm - Integrazione Home Assistant per Centrali Lince

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

Integrazione personalizzata per Home Assistant che permette il controllo e monitoraggio completo delle centrali d'allarme Lince attraverso il servizio cloud.

> ⚠️ **IMPORTANTE**: Questa integrazione richiede l'installazione di un certificato SSL per funzionare correttamente. Vedi la sezione [Configurazione Certificato SSL](#️-pre-requisito-configurazione-certificato-ssl).
> 
> ⚠️ **IMPORTANTE**: Questa integrazione utilizza il protocollo di comunicazione WebSocket per tutte le funzioni di comunicazioni, aggiornamento sensori e gestione del pannello di allarme. Quando la comunicazione WebSocket è attiva, il servizio Lince Cloud non potrà essere utilizzato, in quanto è possibile una sola connessione WebSocket alla volta. Stessa cosa per il servizio cloud web, se la comunicazione è attiva con il servizio, i messaggi in Home Assistant da/verso la centrale non funzioneranno.
> 
> ⚠️ **IMPORTANTE**: Questa integrazione funziona solo con centrali Lince EuroPlus. 
Al momento non sono supportate le centrali Gold/Tosca (si ricercano beta tester).

## 🌟 Caratteristiche Principali

### 🔐 Controllo Allarme Completo
- **Gestione multi-profilo**: Supporto per tutti i profili di attivazione (Home, Away, Night, Vacation, Custom)
- **Attivazione/Disattivazione**: Controllo completo con supporto PIN utente
- **Stati in tempo reale**: Monitoraggio dello stato della centrale (Armato, Disarmato, In Allarme, Arming, Disarming)
- **Gestione transizioni**: Visualizzazione degli stati transitori durante le operazioni
- **Feedback ottimistico**: Risposta immediata nell'interfaccia con conferma successiva

### 📡 Connessione WebSocket Real-Time
- **Eventi in tempo reale**: Ricezione immediata di tutti gli eventi dalla centrale
- **Auto-riconnessione**: Sistema intelligente di retry con backoff esponenziale
- **Gestione token**: Re-login automatico quando il token scade
- **Switch di controllo**: Possibilità di attivare/disattivare la connessione WebSocket per ogni centrale
- **Persistenza stato**: Le WebSocket si riattivano automaticamente dopo un riavvio di HA

### 🔔 Sistema di Notifiche Avanzato
- **Notifiche multi-canale**: Supporto per notifiche persistenti e mobile
- **Eventi monitorati**:
  - Attivazione/Disattivazione centrale
  - Allarmi scattati con notifica prioritaria
  - Errori PIN
  - Stato connessione WebSocket
  - Problemi di connessione al cloud
- **Controllo granulare**: Switch per abilitare/disabilitare le notifiche per singola centrale
- **Smart notifications**: Evita spam di notifiche con cooldown intelligente

### 🏠 Sensori Zone
- **Monitoraggio zone**: Stato real-time di tutte le zone (Aperto/Chiuso, Escluso, Sabotaggio)
- **Tipologie supportate**: Zone filari e radio
- **Attributi dettagliati**: Tipo zona, stato batteria (per zone radio), memoria allarme
- **Nomi personalizzati**: Utilizza i nomi configurati nella centrale

### 📊 Sensori di Sistema
- **Informazioni centrale**: Modello, versione firmware, stato connessione
- **Diagnostica**: Tensione batteria, stato alimentazione, temperatura
- **Contatori eventi**: Numero di allarmi, sabotaggi, anomalie
- **Stati componenti**: Sirene, espansioni, comunicatori

### 🔄 Coordinator Intelligente
- **Polling ottimizzato**: Aggiornamento dati ogni 10 secondi
- **Cache intelligente**: Mantiene i dati durante disconnessioni temporanee
- **Retry automatico**: Sistema di retry con backoff progressivo
- **Notifiche di stato**: Informa su problemi di connessione e ripristini

## 📋 Requisiti

- Home Assistant 2024.1.0 o superiore
- Account Lince Cloud attivo
- Centrale Lince compatibile con il servizio cloud
- Python 3.11 o superiore
- [Additional CA Integration](https://github.com/Athozs/hass-additional-ca) (per certificato SSL)

## 📦 Installazione

### ⚠️ Pre-requisito: Configurazione Certificato SSL

Il servizio Lince Cloud utilizza un certificato SSL self-signed che deve essere installato in Home Assistant per permettere la comunicazione sicura.

#### Passo 1: Installa Additional CA Integration

1. Installa HACS se non l'hai già fatto (vedi [documentazione HACS](https://hacs.xyz/docs/setup/download))
2. In HACS, cerca e installa: [Additional CA Integration](https://github.com/Athozs/hass-additional-ca)
3. Riavvia Home Assistant

#### Passo 2: Configura il certificato

1. Crea una cartella `additional_ca` nella root della configurazione di Home Assistant:
   ```bash
   mkdir /config/additional_ca
   ```

2. Copia il file del certificato `lince_cloud.pem` dal repository nella cartella appena creata:
   ```bash
   cp lince_cloud.pem /config/additional_ca/
   ```

3. Aggiungi la seguente configurazione al tuo `configuration.yaml`:
   ```yaml
   additional_ca:
     lince_cloud: lince_cloud.pem
   ```

4. Riavvia Home Assistant per applicare le modifiche

### Installazione dell'integrazione

#### Metodo 1: Installazione tramite HACS (Raccomandato)

1. Assicurati che HACS sia installato (vedi [documentazione HACS](https://hacs.xyz/docs/setup/download)).
2. Vai su HACS > Integrazioni > Menu (⋮) > Repositories personalizzati.
3. Aggiungi il repository: `https://github.com/M4v3r1cK87/Lince-Alarm-for-Home-Assistant`
4. Imposta la categoria su Integrazione e clicca su Aggiungi.
5. Cerca "Lince Alarm" in HACS e installalo.
6. Riavvia Home Assistant.
7. Vai in **Impostazioni** → **Dispositivi e Servizi** → **Aggiungi integrazione**.
8. Cerca **Lince Alarm** e segui la procedura guidata.

#### Metodo 2: Installazione Manuale

1. Scarica l'ultima release da [GitHub Releases](https://github.com/M4v3r1cK87/Lince-Alarm-for-Home-Assistant/releases)
2. Estrai la cartella `Lince-Alarm-for-Home-Assistant` in `config/custom_components/`
3. La struttura dovrebbe essere:
   ```
   config/
   ├── custom_components/
   │   └── Lince-Alarm-for-Home-Assistant/
   │       ├── __init__.py
   │       ├── manifest.json
   │       └── ...
   └── additional_ca/
       └── lince_cloud.pem
   ```
4. Riavvia Home Assistant
5. Vai in **Impostazioni** → **Dispositivi e Servizi** → **Aggiungi integrazione**
6. Cerca **Lince Alarm** e segui la procedura guidata

#### Metodo 3: Git Clone

```bash
cd /config/custom_components
git clone https://github.com/M4v3r1cK87/Lince-Alarm-for-Home-Assistant.git
# Copia il certificato
cp Lince-Alarm-for-Home-Assistant/lince_cloud.pem /config/additional_ca/
```

## ⚙️ Configurazione

### Prima Configurazione

1. Vai in **Impostazioni** → **Dispositivi e Servizi**
2. Clicca su **Aggiungi integrazione**
3. Cerca **Lince Alarm**
4. Inserisci le credenziali del tuo account Lince Cloud:
   - Email
   - Password
5. Seleziona le centrali da importare
6. Configura le opzioni per centrale

### Opzioni Configurabili

Per ogni centrale puoi configurare:
- **Numero zone filari**: Imposta il numero di zone cablate (0-35)
- **Numero zone radio**: Imposta il numero di zone wireless (0-64)
- **Associazioni programmi al pannello di allarme**: Associa i programmi G1/G2/G3/GEXT alle varie modalità di attivazione del pannello di allarme

## 🐛 Troubleshooting

### Errore SSL/TLS o connessione rifiutata
- Verifica di aver installato correttamente il certificato `lince_cloud.pem`
- Controlla che Additional CA Integration sia installato e configurato
- Riavvia Home Assistant dopo aver configurato il certificato

### La centrale non risponde ai comandi
- Verifica che il PIN inserito sia corretto
- Controlla che la WebSocket sia attiva (switch abilitato)
- Verifica la connessione internet della centrale
- Controlla i log per eventuali errori di autenticazione

### Le zone non si aggiornano
- Controlla il numero di zone configurate nelle opzioni dell'integrazione
- Verifica che la WebSocket sia connessa (controlla lo switch)
- Prova a disabilitare e riabilitare la WebSocket
- Ricarica l'integrazione

### Notifiche non ricevute
- Verifica che lo switch delle notifiche sia abilitato per la centrale
- Controlla la configurazione del servizio notify in HA
- Verifica nei log se ci sono errori di invio notifiche

## 📝 Logging

Per debug dettagliato, aggiungi al `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.lince_cloud: debug
    custom_components.lince_cloud.api: debug
    custom_components.lince_cloud.socket_client: debug
    custom_components.lince_cloud.coordinator: info
```

## 🔍 Verifica Installazione

Per verificare che tutto sia installato correttamente:

1. **Certificato SSL**: Controlla che il file esista
   ```bash
   ls -la /config/additional_ca/lince_cloud.pem
   ```

2. **Integrazione**: Verifica la presenza dei file
   ```bash
   ls -la /config/custom_components/Lince-Alarm-for-Home-Assistant/
   ```

3. **Log**: Controlla i log per errori
   ```bash
   grep -i "lince" /config/home-assistant.log
   ```

## 🤝 Contribuire

I contributi sono benvenuti! Per favore:

1. Forka il repository
2. Crea un branch per la tua feature (`git checkout -b feature/AmazingFeature`)
3. Committa le modifiche (`git commit -m 'Add some AmazingFeature'`)
4. Pusha il branch (`git push origin feature/AmazingFeature`)
5. Apri una Pull Request

## 📄 Licenza

Questo progetto è rilasciato sotto licenza MIT. Vedi il file [LICENSE](LICENSE) per i dettagli.

## ⚠️ Disclaimer

Questa è un'integrazione **non ufficiale**. Gli autori non sono affiliati con Lince o i suoi partner.
L'uso di questa integrazione è a proprio rischio e responsabilità.

Il certificato SSL incluso (`lince_cloud.pem`) è necessario per la comunicazione con i server Lince Cloud ed è fornito solo per scopi di interoperabilità.

## 🙏 Ringraziamenti

- Grazie alla community di Home Assistant
- Grazie agli sviluppatori di [Additional CA Integration](https://github.com/Athozs/hass-additional-ca)
- Grazie a tutti i beta tester e contributori

## 📞 Supporto

Per bug e feature request, apri una [issue su GitHub](https://github.com/M4v3r1cK87/Lince-Alarm-for-Home-Assistant/issues).

Per discussioni e supporto dalla community, partecipa alle [Discussions](https://github.com/M4v3r1cK87/Lince-Alarm-for-Home-Assistant/discussions).

---

**Made with ❤️ for Home Assistant**

[commits-shield]: https://img.shields.io/github/commit-activity/y/M4v3r1cK87/Lince-Alarm-for-Home-Assistant.svg?style=for-the-badge
[commits]: https://github.com/M4v3r1cK87/Lince-Alarm-for-Home-Assistant/commits/main
[license-shield]: https://img.shields.io/github/license/M4v3r1cK87/Lince-Alarm-for-Home-Assistant.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/M4v3r1cK87/Lince-Alarm-for-Home-Assistant.svg?style=for-the-badge
[releases]: https://github.com/M4v3r1cK87/Lince-Alarm-for-Home-Assistant/releases

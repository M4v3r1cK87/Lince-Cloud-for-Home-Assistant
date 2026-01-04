# Lince Alarm - Integrazione Home Assistant

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
![GitHub Stars][stars-shield]
[![License][license-shield]](LICENSE)

Integrazione Home Assistant per il controllo e monitoraggio delle centrali d'allarme **Lince**.

> ⚠️ **ATTENZIONE - Serie GR868**: Se utilizzi una centrale **Lince GR868** con modulo EuroNET, l'intervallo di polling deve essere impostato ad **almeno 2s (2 secondi)**. Valori inferiori possono causare problemi di comunicazione, mancata risposta ai comandi e comportamenti anomali.

## 🎯 Centrali e Modalità Supportate

| Centrale | Modalità Cloud | Modalità Locale (EuroNET) | Note |
|----------|:--------------:|:-------------------------:|:----:|
| **EuroPlus** | ✅ | ✅ |
| **Gold** | ✅ (beta) | ❌ |
| **GR868** | ❌ | ✅ | Impostare intervallo di polling ad almeno 2 secondi |

---

## 🆕 Modalità Locale (EuroNET)

Nuova modalità che sfrutta il modulo **EuroNET** (codice LINCE 4124EURONET) per una connessione diretta alla centrale via LAN, senza passare dal cloud.

### ✅ Vantaggi

| Vantaggio | Descrizione |
|-----------|-------------|
| **🔒 100% Locale** | Nessuna dipendenza da server cloud esterni |
| **⚡ Bassa latenza** | Comunicazione diretta sulla rete locale |
| **🔐 Privacy** | I dati non escono dalla tua rete |
| **📡 Polling configurabile** | Da 250ms a 60 secondi |
| **🔄 Sempre disponibile** | Funziona anche senza connessione internet (serve comunque connettività LAN) |

### 📊 Dati Disponibili

| Categoria | Informazioni |
|-----------|--------------|
| **Zone Filari** | Stato (aperto/chiuso), allarme, sabotaggio, esclusione, configurazione |
| **Zone Radio** | Stato, allarme, sabotaggio, batteria, segnale, supervisione |
| **Stato Centrale** | Armato/disarmato, programmi attivi, allarme in corso |
| **Diagnostica** | Temperatura, tensione batteria/bus, stato alimentazione |
| **Memorie** | Storico allarmi e sabotaggi |
| **Integrità** | Stato batteria interna/esterna, anomalie |

### 🎛️ Funzionalità

- **Pannello Allarme**: Arma/disarma con associazione programmi (G1, G2, G3, GEXT)
- **Profili**: Home, Away, Night, Vacation (mappabili liberamente ai programmi)
- **Notifiche**: Arm/disarm con nome modalità (attivabili/disattivabili per centrale)
- **Zone come sensori**: Binary sensor per ogni zona configurata

### 📋 Requisiti Modalità Locale

- Centrale **EuroPlus** o **GR868**
- Modulo **EuroNET** (LINCE 4124EURONET) installato e raggiungibile in LAN
- Credenziali di accesso al modulo EuroNET
- Codice installatore della centrale, per alcune funzionalità avanzate (nomi e configurazioni zone)

> ⚠️ **IMPORTANTE**: La modalità locale è esclusiva. Quando attiva in HA, non sarà possibile eseguire il login tramite browser nel modulo EuroNET; viceversa, se si è loggati nel modulo EuroNET, l'integrazione non funzionerà correttamente.

---

## ☁️ Modalità Cloud

Connessione tramite il servizio **Lince Cloud** con comunicazione WebSocket real-time.

### 🌟 Caratteristiche

#### 🔐 Controllo Allarme
- Gestione multi-profilo (Home, Away, Night, Vacation, Custom)
- Attivazione/Disattivazione con PIN utente
- Stati in tempo reale con feedback ottimistico

#### 📡 WebSocket Real-Time
- Eventi in tempo reale dalla centrale
- Auto-riconnessione con backoff esponenziale
- Re-login automatico alla scadenza token
- Switch per attivare/disattivare la WebSocket

#### 🔔 Notifiche Avanzate
- Notifiche persistenti e mobile
- Allarmi, arm/disarm, errori PIN, stato connessione
- Controllo granulare per centrale

#### 🏠 Sensori
- Zone filari e radio con stato real-time
- Diagnostica: tensione, temperatura, stati componenti
- Nomi personalizzati dalla centrale

### 📋 Requisiti Modalità Cloud

- Account **Lince Cloud** attivo
- Centrale compatibile con il servizio cloud
- Certificato SSL configurato (vedi sotto)

> ⚠️ **IMPORTANTE**: La WebSocket è esclusiva. Quando attiva in HA, l'app Lince Cloud non funzionerà e viceversa.

---

## 📦 Installazione

### Metodo 1: HACS (Raccomandato)

1. **HACS** → **Integrazioni** → **⋮** → **Repository personalizzati**
2. Aggiungi: `https://github.com/M4v3r1cK87/Lince-Alarm-for-Home-Assistant`
3. Categoria: **Integrazione** → **Aggiungi**
4. Cerca "**Lince Alarm**" e installa
5. **Riavvia Home Assistant**

### Metodo 2: Manuale

```bash
cd /config/custom_components
git clone https://github.com/M4v3r1cK87/Lince-Alarm-for-Home-Assistant.git
```
Riavvia Home Assistant.

---

## ⚙️ Configurazione

### Aggiungi l'Integrazione

1. **Impostazioni** → **Dispositivi e Servizi** → **Aggiungi integrazione**
2. Cerca **Lince Alarm**
3. Scegli la modalità di connessione:
   - **🏠 Connessione Locale (EuroNET)**
   - **☁️ Connessione Cloud**

---

### 🏠 Configurazione Locale (EuroNET)

#### Parametri Connessione

| Campo | Descrizione |
|-------|-------------|
| **Host** | Indirizzo IP del modulo EuroNET (es. `192.168.1.100`) |
| **Porta** | Porta HTTP (default: `80`) |
| **Nome utente** | Username del modulo EuroNET |
| **Password** | Password del modulo EuroNET |
| **Codice installatore** | Codice installatore della centrale |

#### Opzioni (dopo l'aggiunta)

| Opzione | Descrizione |
|---------|-------------|
| **Zone filari** | Numero di zone cablate (0-35) |
| **Zone radio** | Numero di zone wireless (0-64) |
| **Intervallo polling** | Frequenza aggiornamento (250-60000 ms) |
| **Profili ARM** | Associazione programmi alle modalità |

#### Esempio Profili ARM

| Modalità | Programmi |
|----------|-----------|
| Away (Fuori casa) | G1, G2, G3, GEXT |
| Home (In casa) | G1 |
| Night (Notte) | G1, G2 |
| Vacation (Vacanza) | G1, G2, G3 |

---

### ☁️ Configurazione Cloud

#### Pre-requisito: Certificato SSL

1. Installa **[Additional CA Integration](https://github.com/Athozs/hass-additional-ca)** da HACS
2. Copia il certificato:
   ```bash
   mkdir -p /config/additional_ca
   cp lince_cloud.pem /config/additional_ca/
   ```
3. Aggiungi a `configuration.yaml`:
   ```yaml
   additional_ca:
     lince_cloud: lince_cloud.pem
   ```
4. Riavvia Home Assistant

#### Parametri

- **Email**: Email account Lince Cloud
- **Password**: Password account Lince Cloud

---

## 🐛 Troubleshooting

### Modalità Locale (EuroNET)

| Problema | Soluzione |
|----------|-----------|
| Connessione rifiutata | Verifica IP e porta del modulo EuroNET |
| "NoLogin" dopo comando | Credenziali errate o sessione scaduta |
| Zone non visibili | Configura il numero di zone nelle opzioni |
| Stato non aggiornato | Verifica intervallo polling |

### Modalità Cloud

| Problema | Soluzione |
|----------|-----------|
| Errore SSL/TLS | Verifica certificato `lince_cloud.pem` |
| WebSocket non connette | Chiudi l'app Lince Cloud |
| Centrale non risponde | Verifica PIN e stato WebSocket |

---

## 📝 Logging

```yaml
logger:
  default: warning
  logs:
    custom_components.lince_alarm: debug
    custom_components.lince_alarm.euronet: debug
    custom_components.lince_alarm.europlus: debug
    custom_components.lince_alarm.gold: debug
```

---

## 🤝 Contribuire

1. Forka il repository
2. Crea un branch (`git checkout -b feature/NuovaFeature`)
3. Committa (`git commit -m 'Aggiungi NuovaFeature'`)
4. Pusha (`git push origin feature/NuovaFeature`)
5. Apri una Pull Request

---

## 📄 Licenza

Rilasciato sotto licenza MIT. Vedi [LICENSE](LICENSE).

## ⚠️ Disclaimer

Integrazione **non ufficiale**. Non affiliata con Lince.
Uso a proprio rischio e responsabilità.

Il certificato SSL (`lince_cloud.pem`) è fornito solo per interoperabilità con Lince Cloud.

---

## 📞 Supporto

- **Bug/Feature**: [GitHub Issues](https://github.com/M4v3r1cK87/Lince-Alarm-for-Home-Assistant/issues)
- **Discussioni**: [GitHub Discussions](https://github.com/M4v3r1cK87/Lince-Alarm-for-Home-Assistant/discussions)

---

**Made with ❤️ for Home Assistant**

[commits-shield]: https://img.shields.io/github/commit-activity/y/M4v3r1cK87/Lince-Alarm-for-Home-Assistant.svg?style=for-the-badge
[commits]: https://github.com/M4v3r1cK87/Lince-Alarm-for-Home-Assistant/commits/main
[license-shield]: https://img.shields.io/github/license/M4v3r1cK87/Lince-Alarm-for-Home-Assistant.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/M4v3r1cK87/Lince-Alarm-for-Home-Assistant.svg?style=for-the-badge
[releases]: https://github.com/M4v3r1cK87/Lince-Alarm-for-Home-Assistant/releases
[stars-shield]: https://img.shields.io/github/stars/M4v3r1cK87/Lince-Alarm-for-Home-Assistant.svg?style=for-the-badge

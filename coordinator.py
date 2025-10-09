import logging
import asyncio
from .europlusParser import europlusParser
from datetime import datetime, timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .utils import send_persistent_notification, dismiss_persistent_notification, send_notification

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEFAULT_FILARI = 0
DEFAULT_RADIO = 0
RETRY_INTERVAL = 300  # 5 minuti
MAX_RETRY_INTERVAL = 1800  # 30 minuti massimo
INITIAL_RETRY_INTERVAL = 60  # 1 minuto per il primo retry

class GoldCloudCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, api, config_entry):
        self.api = api
        self.socket_messages = {}

        # Mapping per-centrale
        self.systems_config = config_entry.options.get("systems_config", config_entry.data.get("systems_config", {}))
        self.Email = config_entry.data["email"]
        self.Password = config_entry.data["password"]
        self.config_entry = config_entry
        
        # Retry mechanism
        self._retry_task = None
        self._retry_count = 0
        self._last_successful_update = None
        self._connection_failed = False
        self._retry_interval = INITIAL_RETRY_INTERVAL
        self._notification_id = "lincecloud_connection_error"
        self._was_offline = False  # Flag per tracciare se eravamo offline
        self._pause_auto_update = False  # Flag per pausare gli update automatici durante retry
        self._notification_cleanup_task = None  # Task per rimuovere notifiche
        self._row_id = None

        super().__init__(
            hass,
            _LOGGER,
            name="GoldCloud Data Coordinator",
            update_interval=timedelta(seconds=10),
        )

    def _get_counts_for_system(self, system_id: int):
        cfg = self.systems_config.get(str(system_id), {})
        _LOGGER.debug(f"Configurazione per sistema {system_id}: {cfg}")
        nf = int(cfg.get("num_filari", DEFAULT_FILARI))
        nr = int(cfg.get("num_radio", DEFAULT_RADIO))
        return nf, nr

    async def _async_update_data(self):
        """Update data con gestione retry intelligente."""
        # Se siamo in retry mode, skip l'update automatico
        if self._pause_auto_update:
            _LOGGER.debug("Update automatico pausato durante retry")
            return self.data or []
            
        try:
            # Check token e login se necessario
            if self.api.is_token_expired():
                _LOGGER.info("Token scaduto o mancante: tentativo di login")
                try:
                    await self.api.login(self.Email, self.Password)
                    _LOGGER.info("Login completata con successo")
                except Exception as e:
                    _LOGGER.warning(f"Login fallita: {e}")
                    await self._handle_connection_failure(e)
                    # Ritorna i dati cached se disponibili
                    return self.data or []

            # Fetch systems
            try:
                systems = await self.api.fetch_systems() or []
            except Exception as e:
                _LOGGER.warning(f"Fetch systems fallito: {e}")
                await self._handle_connection_failure(e)
                return self.data or []

            updated_systems = []
            
            for system in systems:
                if system.get("connesso") == 1:
                    self._row_id = system["id"]
                    
                    # Fetch system access con gestione errori
                    try:
                        access_data = await self.api.fetch_system_access(self._row_id)
                        system["access_data"] = access_data
                    except Exception as e:
                        _LOGGER.warning(f"Fetch system access fallito per {self._row_id}: {e}")
                        # Usa dati cached se disponibili
                        if self.data:
                            for old_sys in self.data:
                                if old_sys.get("id") == self._row_id:
                                    system["access_data"] = old_sys.get("access_data")
                                    break

                    # socket message ultimo
                    system["socket_message"] = self.api.get_last_socket_message(self._row_id) or ""

                    # names/zone
                    try:
                        if system.get("access_data") and "store" in system.get("access_data", {}):
                            parser = europlusParser(None)
                            num_filari, num_radio = self._get_counts_for_system(self._row_id)
                            zonesName = parser.parseZones(system["access_data"]["store"], num_filari, num_radio)
                            keysName = parser.parse_keysName(system["access_data"]["store"])
                            system["keysName"] = keysName
                            system["zonesName"] = zonesName
                        else:
                            # Mantieni i nomi cached se disponibili
                            if self.data:
                                for old_sys in self.data:
                                    if old_sys.get("id") == self._row_id:
                                        system["keysName"] = old_sys.get("keysName", [])
                                        system["zonesName"] = old_sys.get("zonesName", {"filare": [], "radio": []})
                                        break
                            else:
                                system["keysName"] = []
                                system["zonesName"] = {"filare": [], "radio": []}
                    except Exception as e:
                        _LOGGER.error("Errore parsing zone %s: %s", self._row_id, e)
                        system["keysName"] = []
                        system["zonesName"] = {"filare": [], "radio": []}
                        
                    updated_systems.append(system)

            # Reset retry mechanism on success
            if updated_systems:
                await self._handle_connection_success()
            
            return updated_systems
            
        except Exception as err:
            _LOGGER.warning("Update dati fallito completamente: %s", err)
            await self._handle_connection_failure(err)
            # Ritorna i dati precedenti o lista vuota
            return self.data or []

    async def _handle_connection_failure(self, error: Exception):
        """Gestisce i fallimenti di connessione con retry intelligente."""
        self._connection_failed = True
        self._was_offline = True  # Segna che siamo andati offline
        self._pause_auto_update = True  # Pausa gli update automatici
        self._retry_count += 1
        
        # Calcola il prossimo intervallo con exponential backoff
        self._retry_interval = min(
            INITIAL_RETRY_INTERVAL * (2 ** min(self._retry_count - 1, 5)),
            MAX_RETRY_INTERVAL
        )
        
        # Crea notifica solo al primo fallimento o ogni 5 tentativi
        if self._retry_count == 1 or self._retry_count % 5 == 0:
            await self._create_connection_notification(error)
        
        # Avvia/riavvia il task di retry se non già attivo
        if not self._retry_task or self._retry_task.done():
            self._retry_task = self.hass.async_create_task(self._retry_connection())
        
        _LOGGER.info(
            f"Connessione fallita (tentativo {self._retry_count}). "
            f"Prossimo retry tra {self._retry_interval} secondi"
        )

    async def _handle_connection_success(self):
        """Reset del meccanismo di retry dopo una connessione riuscita."""
        if self._connection_failed:
            _LOGGER.info("Connessione ristabilita con successo")
            
            # Salva info per le notifiche prima di resettare
            retry_attempts = self._retry_count
            was_offline = self._was_offline
            
            # Reset stati
            self._connection_failed = False
            self._pause_auto_update = False  # Riprendi gli update automatici
            self._retry_count = 0
            self._retry_interval = INITIAL_RETRY_INTERVAL
            self._last_successful_update = datetime.now()
            
            # Cancella il task di retry se attivo
            if self._retry_task and not self._retry_task.done():
                self._retry_task.cancel()
                self._retry_task = None
            
            # Rimuovi notifica di errore
            await self._dismiss_connection_notification()
            
            # Se eravamo offline, invia notifiche e forza refresh
            if was_offline:
                _LOGGER.info("Sistema era offline, invio notifiche di riconnessione...")
                
                # Invia notifica persistente di successo
                await self._create_success_notification(retry_attempts)
                
                # Invia anche notifiche push se configurate
                #await self._send_reconnection_push_notifications(retry_attempts)
                
                # Reset flag PRIMA del refresh
                self._was_offline = False
                
                # Forza il refresh di tutte le entità DOPO le notifiche
                _LOGGER.info("Forzando refresh completo dopo riconnessione...")
                await self._force_entities_refresh()

    async def _retry_connection(self):
        """Task di retry con backoff esponenziale."""
        while self._connection_failed:
            _LOGGER.info(f"Attendo {self._retry_interval} secondi prima del prossimo tentativo...")
            await asyncio.sleep(self._retry_interval)
            
            if not self._connection_failed:  # Check se nel frattempo è tornata online
                break
            
            _LOGGER.info(f"Tentativo di riconnessione {self._retry_count + 1}")
            
            try:
                # NON chiudiamo le socket - potrebbero essere già riconnesse automaticamente
                # Verifichiamo prima lo stato delle socket
                await self._check_and_restore_sockets()
                
                # Prova prima il login
                if self.api.is_token_expired():
                    await self.api.login(self.Email, self.Password)
                    _LOGGER.info("Re-login completata con successo")
                
                # Poi prova a recuperare i sistemi
                systems = await self.api.fetch_systems()
                if systems:
                    _LOGGER.info("Sistemi recuperati con successo, triggering update")
                    
                    # Riabilita temporaneamente gli update
                    self._pause_auto_update = False
                    
                    # Forza un update completo del coordinator
                    await self.async_refresh()
                    
                    # Se il refresh ha avuto successo, esci dal loop
                    if not self._connection_failed:
                        _LOGGER.info("Riconnessione completata con successo!")
                        break
                    
            except Exception as e:
                self._retry_count += 1
                # Ricalcola intervallo con backoff
                self._retry_interval = min(
                    self._retry_interval * 1.5,  # Incremento più graduale
                    MAX_RETRY_INTERVAL
                )
                _LOGGER.debug(
                    f"Retry {self._retry_count} fallito: {e}. "
                    f"Prossimo tentativo tra {self._retry_interval} secondi"
                )
                
                # Aggiorna notifica ogni 10 tentativi
                if self._retry_count % 10 == 0:
                    await self._create_connection_notification(e)

    async def _check_and_restore_sockets(self):
        """Verifica lo stato delle socket e le ripristina solo se necessario."""
        try:
            _LOGGER.info("Verificando stato delle socket connections...")
            
            if self.data:
                for system in self.data:
                    if system.get("connesso") == 1:
                        self._row_id = system["id"]
                        
                        # Verifica se la socket è già connessa
                        if self.api.is_socket_connected(self._row_id):
                            _LOGGER.debug(f"Socket {self._row_id} già connessa, skip riavvio")
                            continue
                        
                        # Se non è connessa, prova ad avviarla
                        try:
                            _LOGGER.info(f"Socket {self._row_id} non connessa, tentativo di avvio...")
                            await self.api.start_socket_connection(self._row_id)
                            await asyncio.sleep(1)  # Piccola pausa tra una socket e l'altra
                        except Exception as e:
                            error_msg = str(e).lower()
                            if "in uso" in error_msg or "busy" in error_msg:
                                # La socket potrebbe essere in uno stato intermedio
                                _LOGGER.info(f"Socket {self._row_id} sembra già in uso, verifico meglio...")
                                
                                # Prova a forzare una chiusura pulita e riavvio
                                try:
                                    await self.api.stop_socket_connection(self._row_id)
                                    await asyncio.sleep(3)  # Attendi che il server rilasci la sessione
                                    await self.api.start_socket_connection(self._row_id)
                                    _LOGGER.info(f"Socket {self._row_id} riavviata con successo dopo pulizia")
                                except Exception as e2:
                                    _LOGGER.warning(f"Socket {self._row_id} probabilmente già connessa lato server: {e2}")
                                    # Assumiamo che la socket sia connessa e proseguiamo
                            else:
                                _LOGGER.warning(f"Errore avvio socket {self._row_id}: {e}")
                                
        except Exception as e:
            _LOGGER.warning(f"Errore durante verifica sockets: {e}")

    async def _force_entities_refresh(self):
        """Forza il refresh di tutte le entità dopo una riconnessione."""
        try:
            _LOGGER.info("Iniziando refresh forzato delle entità...")
            
            # Prima verifica/ripristina le socket se necessario
            await self._check_and_restore_sockets()
            
            # Attendi che le socket si stabilizzino
            await asyncio.sleep(2)
            
            # Forza un refresh completo dei dati con il metodo corretto
            try:
                # Usa async_refresh che gestisce correttamente gli errori
                await self.async_refresh()
                _LOGGER.info("async_refresh completato")
            except Exception as e:
                _LOGGER.warning(f"async_refresh fallito: {e}, provo con async_request_refresh")
                # Se fallisce, prova con async_request_refresh
                await self.async_request_refresh()
            
            # Assicurati che i dati vengano propagati alle entità
            if self.data:
                # Forza l'aggiornamento immediato notificando tutti i listener
                self.async_set_updated_data(self.data)
                _LOGGER.info(f"Dati aggiornati per {len(self.data)} sistemi")
                
                # Triggera anche un evento per forzare il refresh delle entità
                self.hass.async_create_task(
                    self.hass.async_add_job(self._notify_entity_refresh)
                )
            
            _LOGGER.info("Refresh forzato completato - tutte le entità dovrebbero essere aggiornate")
            
        except Exception as e:
            _LOGGER.error(f"Errore durante il refresh forzato: {e}")

    async def _notify_entity_refresh(self):
        """Notifica tutte le entità che i dati sono cambiati."""
        try:
            # Forza un update del coordinator state
            self.last_update_success = True
            self.last_exception = None
            
            # Invia evento per aggiornare tutte le entità
            self.hass.bus.async_fire(
                f"{DOMAIN}_data_updated",
                {"coordinator": "GoldCloudCoordinator"}
            )
            
            _LOGGER.debug("Evento di refresh entità inviato")
        except Exception as e:
            _LOGGER.error(f"Errore durante notifica refresh entità: {e}")

    async def _create_success_notification(self, retry_attempts: int):
        """Crea una notifica persistente di successo per la riconnessione."""
        try:
            # Calcola il tempo offline approssimativo
            offline_time = ""
            if retry_attempts > 0:
                # Stima approssimativa basata sui retry
                total_seconds = sum(
                    min(INITIAL_RETRY_INTERVAL * (2 ** min(i, 5)), MAX_RETRY_INTERVAL)
                    for i in range(retry_attempts)
                )
                minutes = total_seconds // 60
                if minutes > 0:
                    hours = minutes // 60
                    remaining_minutes = minutes % 60
                    if hours > 0:
                        offline_time = f" dopo circa {hours} or{'a' if hours == 1 else 'e'}"
                        if remaining_minutes > 0:
                            offline_time += f" e {remaining_minutes} minut{'o' if remaining_minutes == 1 else 'i'}"
                    else:
                        offline_time = f" dopo circa {minutes} minut{'o' if minutes == 1 else 'i'}"
                else:
                    offline_time = f" dopo {total_seconds} second{'o' if total_seconds == 1 else 'i'}"
            
            success_message = (
                "✅ **Connessione LinceCloud Ripristinata!**\n\n"
                f"La connessione è stata ristabilita con successo{offline_time}.\n"
            )
            
            if retry_attempts > 0:
                success_message += f"**Tentativi effettuati:** {retry_attempts}\n"
            
            success_message += (
                "\n**Stato attuale:**\n"
                "• ✅ Connessione al cloud attiva\n"
                "• ✅ Autenticazione valida\n"
                "• ✅ Socket connections ripristinate\n"
                "• ✅ Tutte le entità aggiornate\n\n"
                f"**Ultimo aggiornamento:** {datetime.now().strftime('%H:%M:%S')}"
            )
            
            # Crea notifica persistente che resta visibile per 5 minuti
            await send_persistent_notification(
                self.hass,
                message=success_message,
                title="LinceCloud - Connessione Ripristinata",
                notification_id=f"{self._notification_id}_success",
                centrale_id=self._row_id
            )
            
            # Programma la rimozione dopo 5 minuti SENZA bloccare
            self._schedule_notification_cleanup(f"{self._notification_id}_success", 300)
            
            _LOGGER.info("Notifica persistente di riconnessione creata")
            
        except Exception as e:
            _LOGGER.error(f"Errore creazione notifica di successo: {e}")

    def _schedule_notification_cleanup(self, notification_id: str, delay: int):
        """Schedula la rimozione di una notifica senza bloccare."""
        async def cleanup():
            try:
                await asyncio.sleep(delay)
                await dismiss_persistent_notification(self.hass, notification_id)
                _LOGGER.debug(f"Notifica {notification_id} rimossa dopo {delay} secondi")
            except asyncio.CancelledError:
                _LOGGER.debug(f"Cleanup notifica {notification_id} cancellato")
                raise
            except Exception as e:
                _LOGGER.debug(f"Errore rimozione notifica {notification_id}: {e}")
        
        # Cancella task precedente se esiste
        if self._notification_cleanup_task and not self._notification_cleanup_task.done():
            self._notification_cleanup_task.cancel()
        
        # Crea il task senza aspettarlo (fire and forget)
        self._notification_cleanup_task = asyncio.create_task(cleanup())
        # Aggiungi callback per evitare warning di task non gestiti
        self._notification_cleanup_task.add_done_callback(lambda t: None)

    async def _send_reconnection_push_notifications(self, retry_attempts: int):
        """Invia notifiche push per informare della riconnessione."""
        try:
            # Prepara il messaggio
            message = "Sistema LinceCloud riconnesso con successo"
            if retry_attempts > 0:
                message += f" dopo {retry_attempts} tentativi"
            
            # Conta le notifiche inviate con successo
            successful_notifications = 0
            failed_notifications = 0
            
            # Prima prova con il servizio notify generico
            try:
                await send_notification(
                    self.hass,
                    message=message,
                    title="🟢 LinceCloud Online",
                    centrale_id=self._row_id,
                    data={
                        "priority": "high",
                        "tag": "lincecloud_reconnected",
                        "color": "#00ff00",
                        "notification_icon": "mdi:cloud-check"
                    }
                )
                successful_notifications += 1
                _LOGGER.info("Notifica push generica inviata")
            except Exception as e:
                _LOGGER.debug(f"Servizio notify generico non disponibile o fallito: {e}")
                failed_notifications += 1
            
            # Prova anche con mobile_app se disponibili
            try:
                # Ottieni tutti i servizi disponibili
                services = self.hass.services.async_services().get("notify", {})
                mobile_services = [
                    svc for svc in services.keys() 
                    if svc.startswith("mobile_app_")
                ]
                
                for mobile_service in mobile_services:
                    try:
                        await send_notification(
                            self.hass,
                            message=message,
                            title="🟢 LinceCloud Online",
                            target=mobile_service,
                            centrale_id=self._row_id,
                            data={
                                "push": {
                                    "sound": {
                                        "name": "default",
                                        "critical": 0,
                                        "volume": 0.5
                                    }
                                },
                                "priority": "high",
                                "tag": "lincecloud_reconnected",
                                "color": "#00ff00",
                                "notification_icon": "mdi:cloud-check",
                                "actions": [
                                    {
                                        "action": "VIEW_SYSTEMS",
                                        "title": "Visualizza Sistemi"
                                    }
                                ]
                            }
                        )
                        successful_notifications += 1
                        _LOGGER.info(f"Notifica push inviata a {mobile_service}")
                        
                    except Exception as e:
                        error_str = str(e).lower()
                        # Gestisci specificamente i dispositivi non connessi
                        if "not connected" in error_str or "device not connected" in error_str:
                            _LOGGER.debug(f"Dispositivo {mobile_service} non connesso, skip notifica")
                        elif "not found" in error_str or "does not exist" in error_str:
                            _LOGGER.debug(f"Servizio {mobile_service} non trovato")
                        else:
                            _LOGGER.warning(f"Impossibile inviare notifica a {mobile_service}: {e}")
                        failed_notifications += 1
                        # Continua con il prossimo dispositivo invece di interrompere
                        continue
            
            except Exception as e:
                _LOGGER.debug(f"Errore durante enumerazione servizi mobile: {e}")
            
            # Log del risultato finale
            if successful_notifications > 0:
                _LOGGER.info(f"Notifiche di riconnessione inviate: {successful_notifications} successo, {failed_notifications} fallite/offline")
            elif failed_notifications > 0:
                _LOGGER.debug(f"Tutte le notifiche di riconnessione fallite ({failed_notifications}). Dispositivi probabilmente offline")
            else:
                _LOGGER.debug("Nessun servizio di notifica disponibile per la riconnessione")
                
        except Exception as e:
            _LOGGER.error(f"Errore critico durante invio notifiche di riconnessione: {e}")

    async def _cleanup_all_sockets(self):
        """Chiude tutte le socket attive per evitare sessioni zombie - usato solo quando necessario."""
        try:
            _LOGGER.info("Pulizia forzata di tutte le socket connections...")
            for self._row_id in list(self.api.socket_clients.keys()):
                try:
                    await self.api.stop_socket_connection(self._row_id)
                    _LOGGER.debug(f"Socket {self._row_id} chiusa")
                except Exception as e:
                    _LOGGER.debug(f"Errore chiusura socket {self._row_id}: {e}")
                    
            # Attendi un po' per dare tempo al server di pulire le sessioni
            await asyncio.sleep(3)
            
        except Exception as e:
            _LOGGER.warning(f"Errore durante cleanup sockets: {e}")

    async def _create_connection_notification(self, error: Exception):
        """Crea una notifica persistente per problemi di connessione utilizzando utils."""
        try:
            # Formatta il tempo di retry in modo più leggibile
            retry_minutes = self._retry_interval // 60
            retry_seconds = self._retry_interval % 60
            
            if retry_minutes > 0:
                retry_time_str = f"{retry_minutes} minut{'o' if retry_minutes == 1 else 'i'}"
                if retry_seconds > 0:
                    retry_time_str += f" e {retry_seconds} second{'o' if retry_seconds == 1 else 'i'}"
            else:
                retry_time_str = f"{retry_seconds} second{'o' if retry_seconds == 1 else 'i'}"
            
            # Costruisci il messaggio
            message_parts = [
                "❌ **Impossibile connettersi a LinceCloud**",
                "",
                f"**Errore:** `{str(error)}`",
                f"**Tentativi falliti:** {self._retry_count}",
                f"**Prossimo tentativo:** tra {retry_time_str}",
                ""
            ]
            
            # Aggiungi suggerimenti basati sul tipo di errore
            error_str = str(error).lower()
            if "dns" in error_str or "could not contact dns" in error_str:
                message_parts.extend([
                    "⚠️ **Problema DNS rilevato:**",
                    "• Verifica la connessione internet del sistema",
                    "• Controlla le impostazioni DNS del router",
                    "• Prova a riavviare il modem/router",
                    ""
                ])
            elif "timeout" in error_str:
                message_parts.extend([
                    "⏱️ **Timeout di connessione:**",
                    "• Il server potrebbe essere temporaneamente non raggiungibile",
                    "• Verifica eventuali problemi di rete locale",
                    ""
                ])
            elif "unauthorized" in error_str or "401" in error_str:
                message_parts.extend([
                    "🔐 **Problema di autenticazione:**",
                    "• Verifica che le credenziali siano corrette",
                    "• Il tuo account potrebbe essere bloccato",
                    ""
                ])
            elif "connect" in error_str:
                message_parts.extend([
                    "🌐 **Problema di connessione:**",
                    "• Verifica la connessione internet",
                    "• Controlla che non ci siano firewall che bloccano la connessione",
                    ""
                ])
            
            message_parts.append("L'integrazione continuerà a tentare la riconnessione automaticamente.")
            
            # Se ci sono molti tentativi falliti, aggiungi un suggerimento
            if self._retry_count > 10:
                message_parts.extend([
                    "",
                    "💡 **Suggerimento:** Dopo molti tentativi falliti, potrebbe essere necessario:",
                    "• Ricaricare l'integrazione manualmente",
                    "• Verificare lo stato del servizio LinceCloud"
                ])
            
            message = "\n".join(message_parts)
            
            # Invia la notifica persistente usando il metodo di utils
            await send_persistent_notification(
                self.hass,
                message=message,
                title="LinceCloud - Problema di Connessione",
                notification_id=self._notification_id,
                centrale_id=self._row_id
            )
            
            _LOGGER.debug(f"Notifica di errore connessione creata/aggiornata (tentativo {self._retry_count})")
            
        except Exception as e:
            _LOGGER.debug(f"Impossibile creare notifica: {e}")

    async def _dismiss_connection_notification(self):
        """Rimuove la notifica di errore connessione utilizzando utils."""
        try:
            success = await dismiss_persistent_notification(
                self.hass,
                notification_id=self._notification_id
            )
            
            if success:
                _LOGGER.debug("Notifica di errore connessione rimossa")
        except Exception as e:
            _LOGGER.debug(f"Errore durante la rimozione della notifica: {e}")

    async def stop_retry_task(self):
        """Ferma il task di retry (chiamato durante unload)."""
        self._pause_auto_update = False
        
        # Cancella il task di retry
        if self._retry_task and not self._retry_task.done():
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass
            self._retry_task = None
        
        # Cancella il task di cleanup notifiche
        if self._notification_cleanup_task and not self._notification_cleanup_task.done():
            self._notification_cleanup_task.cancel()
            try:
                await self._notification_cleanup_task
            except asyncio.CancelledError:
                pass
            self._notification_cleanup_task = None
        
        # Rimuovi anche eventuali notifiche pendenti
        try:
            await dismiss_persistent_notification(self.hass, self._notification_id)
            await dismiss_persistent_notification(self.hass, f"{self._notification_id}_success")
        except Exception:
            pass
        
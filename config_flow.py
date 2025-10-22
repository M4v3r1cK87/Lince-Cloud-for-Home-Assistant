"""Config flow for LinceCloud integration."""
from __future__ import annotations
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import OptionsFlowWithReload
from homeassistant.helpers.selector import (
    TextSelector, TextSelectorConfig, TextSelectorType,
    SelectSelector, SelectSelectorConfig, SelectOptionDict, SelectSelectorMode,
)
from .const import DOMAIN
from .common.api import CommonAPI  # ✅ Questo è corretto, la classe esiste
from .factory import ComponentFactory

_LOGGER = logging.getLogger(__name__)


class LinceGoldCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow: SOLO login (email/password)."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            # Usa CommonAPI per il login iniziale - questo è corretto
            api = CommonAPI(self.hass)  # ✅ CommonAPI esiste in common/api.py
            try:
                await api.login(user_input["email"], user_input["password"])
                if not api.token:
                    errors["base"] = "auth_failed"
                else:
                    return self.async_create_entry(
                        title=f"Lince Cloud ({user_input['email']})",
                        data={"email": user_input["email"], "password": user_input["password"]},
                    )
            except Exception as e:
                _LOGGER.error(f"Login fallito: {e}")
                errors["base"] = "auth_failed"

        schema = vol.Schema({
            vol.Required("email"): TextSelector(
                TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
            ),
            vol.Required("password"): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="password")
            ),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return LinceGoldCloudOptionsFlow(config_entry)
    
    async def async_step_reauth(self, user_input=None):
        """Handle reauth when token/credentials no longer valid."""
        errors = {}
        entry = self.hass.config_entries.async_get_entry(self.context.get("entry_id"))
        
        if user_input is None:
            # Mostra form con email pre-compilata
            schema = vol.Schema({
                vol.Required("email", default=entry.data.get("email", "")): str,
                vol.Required("password"): str,
            })
            return self.async_show_form(step_id="reauth", data_schema=schema, errors=errors)

        # Verifica nuove credenziali
        api = CommonAPI(self.hass)  # ✅ CommonAPI esiste
        try:
            await api.login(user_input["email"], user_input["password"])
            if not api.token:
                raise Exception("No token received")
        except Exception as e:
            _LOGGER.error(f"Reauth fallito: {e}")
            errors["base"] = "auth_failed"
            schema = vol.Schema({
                vol.Required("email", default=user_input["email"]): str,
                vol.Required("password"): str,
            })
            return self.async_show_form(step_id="reauth", data_schema=schema, errors=errors)

        # Credenziali OK -> aggiorna il config_entry
        data = dict(entry.data)
        data["email"] = user_input["email"]
        data["password"] = user_input["password"]
        self.hass.config_entries.async_update_entry(entry, data=data)

        # Ricarica l'integrazione
        await self.hass.config_entries.async_reload(entry.entry_id)
        return self.async_abort(reason="reauth_successful")


class LinceGoldCloudOptionsFlow(OptionsFlowWithReload):
    """Options Flow per-centrale con supporto multi-brand."""

    def __init__(self, entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self._entry = entry
        self._systems: list[dict] = []
        self._current_sid: int | None = None
        self._current_brand: str = "lince-europlus"

    @staticmethod
    def _program_display_name_from_access(system: dict | None, code: str) -> str:
        """Costruisce il label 'G1 - Porta' usando system['access_data']."""
        upper = code.upper()
        access = (system or {}).get("access_data", {}) or {}
        custom = (access.get(code) or "").strip()
        return f"{upper} - {custom}" if custom else upper

    def _get_system_by_sid(self, sid: int) -> dict | None:
        """Trova un sistema per ID."""
        for s in self._systems or []:
            if s.get("id") == sid:
                return s
        return None

    async def async_step_init(self, user_input=None):
        """Step iniziale: selezione della centrale."""
        errors = {}
        
        # Carica lista centrali
        email = self._entry.data.get("email")
        password = self._entry.data.get("password")
        api = CommonAPI(self.hass)  # ✅ CommonAPI esiste in common/api.py
        
        try:
            await api.login(email, password)
            self._systems = await api.fetch_systems() or []
            
            # Recupera access_data e determina brand per ogni sistema
            for s in self._systems:
                sid = s["id"]
                try:
                    s["access_data"] = await api.fetch_system_access(sid)
                except Exception as e:
                    _LOGGER.debug(f"Impossibile caricare access_data per sistema {sid}: {e}")
                    s["access_data"] = {}
                
                # Determina e salva il brand
                s["_brand"] = ComponentFactory.get_brand_from_system(s)
                
        except Exception as e:
            _LOGGER.debug("Impossibile caricare centrali in Options: %s", e)
            # Fallback dalle opzioni salvate
            systems_config = self._entry.options.get("systems_config", {})
            self._systems = []
            for sid_str in systems_config.keys():
                try:
                    sid = int(sid_str)
                    config = systems_config[sid_str]
                    self._systems.append({
                        "id": sid, 
                        "name": f"Centrale {sid}",
                        "_brand": config.get("brand", "lince-europlus")
                    })
                except ValueError:
                    continue

        # Crea opzioni per il selettore
        options = []
        for s in self._systems:
            sid = s["id"]
            brand = s.get("_brand", "lince-europlus")
            display = f"{s.get('name') or s.get('nome') or f'Centrale {sid}'}"
            if s.get('id_centrale'):
                display += f" - {s.get('id_centrale')}"
            display += f" [{brand}]"
            options.append(SelectOptionDict(value=str(sid), label=display))

        if not options:
            # Nessuna centrale configurabile
            return self.async_create_entry(title="", data=self._entry.options)

        schema = vol.Schema({
            vol.Required("system"): SelectSelector(
                SelectSelectorConfig(
                    options=options, 
                    multiple=False, 
                    mode=SelectSelectorMode.DROPDOWN
                )
            )
        })

        if user_input is not None:
            self._current_sid = int(user_input["system"])
            # Determina il brand del sistema selezionato
            system = self._get_system_by_sid(self._current_sid)
            if system:
                self._current_brand = system.get("_brand", "lince-europlus")
            return await self.async_step_edit_details()

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def _load_name_for_sid(self, sid: int) -> str:
        """Ritorna 'Nome - id_centrale' per il sistema."""
        name = f"Centrale {sid}"
        cached = self._get_system_by_sid(sid)
        if cached:
            base_name = cached.get('name') or cached.get('nome') or name
            if cached.get('id_centrale'):
                return f"{base_name} - {cached.get('id_centrale')}"
            return base_name
            
        # Rifetch solo se necessario
        email = self._entry.data.get("email")
        password = self._entry.data.get("password")
        try:
            api = CommonAPI(self.hass)  # ✅ CommonAPI esiste
            await api.login(email, password)
            systems = await api.fetch_systems() or []
            for s in systems:
                if s["id"] == sid:
                    base_name = s.get('name') or s.get('nome') or name
                    if s.get('id_centrale'):
                        return f"{base_name} - {s.get('id_centrale')}"
                    return base_name
        except Exception:
            pass
        return name

    async def async_step_edit_details(self, user_input=None):
        """Step per configurare dettagli della centrale (zone e profili)."""
        errors: dict[str, str] = {}

        if not self._current_sid:
            return await self.async_step_init()

        sid = self._current_sid
        sid_str = str(sid)
        name = await self._load_name_for_sid(sid)
        system = self._get_system_by_sid(sid)
        
        # Determina il brand e ottieni le costanti appropriate
        brand = self._current_brand
        constants = ComponentFactory.get_constants(brand)
        
        # Estrai costanti brand-specific
        MAX_FILARI_BRAND = constants["MAX_FILARI"]
        MAX_RADIO_BRAND = constants["MAX_RADIO"]
        DEFAULT_FILARI_BRAND = constants["DEFAULT_FILARI"]
        DEFAULT_RADIO_BRAND = constants["DEFAULT_RADIO"]
        SUPPORTS_GEXT = constants["SUPPORTS_GEXT"]
        PROGRAMS = constants["PROGRAMS"]

        _LOGGER.debug(f"Configurazione per centrale {sid} (brand: {brand}): "
                     f"MAX_FILARI={MAX_FILARI_BRAND}, MAX_RADIO={MAX_RADIO_BRAND}, "
                     f"SUPPORTS_GEXT={SUPPORTS_GEXT}, PROGRAMS={PROGRAMS}")

        # Carica configurazioni esistenti
        systems_config = dict(self._entry.options.get("systems_config", {}))
        arm_profiles = dict(self._entry.options.get("arm_profiles", {}))

        # Opzioni dinamiche per i programmi in base al brand
        prog_options = []
        for prog in PROGRAMS:
            prog_options.append(
                SelectOptionDict(
                    value=prog,
                    label=self._program_display_name_from_access(system, prog)
                )
            )

        # Defaults correnti da options salvate
        cfg = systems_config.get(sid_str, {})
        prof = arm_profiles.get(sid_str, {
            "home": [], "away": [], "night": [], "vacation": []
        })
        
        defaults = {
            "num_filari": int(cfg.get("num_filari", DEFAULT_FILARI_BRAND)),
            "num_radio": int(cfg.get("num_radio", DEFAULT_RADIO_BRAND)),
            "home": list(prof.get("home", [])),
            "away": list(prof.get("away", [])),
            "night": list(prof.get("night", [])),
            "vacation": list(prof.get("vacation", [])),
        }

        # Filtra profili per rimuovere programmi non supportati
        for profile in ["home", "away", "night", "vacation"]:
            defaults[profile] = [p for p in defaults[profile] if p in PROGRAMS]

        # Schema base con limiti brand-specific
        base_schema = vol.Schema({
            vol.Required("num_filari", default=defaults["num_filari"]): 
                vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_FILARI_BRAND)),
            vol.Required("num_radio", default=defaults["num_radio"]): 
                vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_RADIO_BRAND)),
            vol.Optional("home", default=defaults["home"]): SelectSelector(
                SelectSelectorConfig(
                    options=prog_options, 
                    multiple=True, 
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Optional("away", default=defaults["away"]): SelectSelector(
                SelectSelectorConfig(
                    options=prog_options, 
                    multiple=True, 
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Optional("night", default=defaults["night"]): SelectSelector(
                SelectSelectorConfig(
                    options=prog_options, 
                    multiple=True, 
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Optional("vacation", default=defaults["vacation"]): SelectSelector(
                SelectSelectorConfig(
                    options=prog_options, 
                    multiple=True, 
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
        })

        # Se l'utente ha inviato il form, valida e salva
        if user_input is not None:
            # Parse sicuro dei numerici
            try:
                nfil = int(user_input.get("num_filari", DEFAULT_FILARI_BRAND))
                nrad = int(user_input.get("num_radio", DEFAULT_RADIO_BRAND))
            except Exception:
                nfil, nrad = DEFAULT_FILARI_BRAND, DEFAULT_RADIO_BRAND

            # Clamp ai massimi brand-specific
            nfil = min(max(0, nfil), MAX_FILARI_BRAND)
            nrad = min(max(0, nrad), MAX_RADIO_BRAND)

            # Multi-select -> liste
            selected = {
                "home": user_input.get("home", []) or [],
                "away": user_input.get("away", []) or [],
                "night": user_input.get("night", []) or [],
                "vacation": user_input.get("vacation", []) or [],
            }

            # Validazione "mask uniche" tra profili
            # Costruisci bitmask dinamicamente in base ai programmi supportati
            PROGRAM_BITS = constants.get("PROGRAM_BITS", {})

            def to_mask(progs: list[str]) -> int:
                m = 0
                for x in progs or []:
                    m |= PROGRAM_BITS.get(x, 0)
                return m

            masks = {
                "home": to_mask(selected["home"]),
                "away": to_mask(selected["away"]),
                "night": to_mask(selected["night"]),
                "vacation": to_mask(selected["vacation"]),
            }

            # Conta duplicati
            count_by_mask: dict[int, int] = {}
            for mode, m in masks.items():
                if m != 0:
                    count_by_mask[m] = count_by_mask.get(m, 0) + 1

            # Modalità duplicate
            dup_modes = [mode for mode, m in masks.items() 
                        if m != 0 and count_by_mask.get(m, 0) > 1]
            
            if dup_modes:
                # Errori per duplicati
                errors["base"] = "duplicate_profiles"
                for mode in dup_modes:
                    errors[mode] = "duplicate_profile"

                # Mantieni valori con suggested
                suggested = {
                    "num_filari": nfil,
                    "num_radio": nrad,
                    "home": selected["home"],
                    "away": selected["away"],
                    "night": selected["night"],
                    "vacation": selected["vacation"],
                }
                schema_with_suggested = self.add_suggested_values_to_schema(base_schema, suggested)
                return self.async_show_form(
                    step_id="edit_details",
                    data_schema=schema_with_suggested,
                    errors=errors,
                    description_placeholders={
                        "system_name": name, 
                        "system_id": sid,
                        "brand": brand,
                        "max_filari": MAX_FILARI_BRAND,
                        "max_radio": MAX_RADIO_BRAND
                    },
                )

            # Nessun duplicato -> salva configurazione
            systems_config[sid_str] = {
                "num_filari": nfil, 
                "num_radio": nrad,
                "brand": brand  # Salva anche il brand nella config
            }
            arm_profiles[sid_str] = selected
            
            _LOGGER.debug(f"Salvando config per centrale {sid} (brand: {brand}): "
                         f"filari={nfil}, radio={nrad}")
            _LOGGER.debug(f"Profili ARM per {sid}: {selected}")

            new_options = dict(self._entry.options)
            new_options["systems_config"] = systems_config
            new_options["arm_profiles"] = arm_profiles
            
            return self.async_create_entry(title="", data=new_options)

        # Primo rendering della form
        return self.async_show_form(
            step_id="edit_details",
            data_schema=base_schema,
            errors=errors,
            description_placeholders={
                "system_name": name, 
                "system_id": sid,
                "brand": brand,
                "max_filari": MAX_FILARI_BRAND,
                "max_radio": MAX_RADIO_BRAND
            },
        )
    
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
from .api import GoldCloudAPI

_LOGGER = logging.getLogger(__name__)

# Default / range
DEFAULT_FILARI = 0
DEFAULT_RADIO = 0
MAX_FILARI = 35
MAX_RADIO = 64


class LinceGoldCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow: SOLO login (email/password)."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            api = GoldCloudAPI(self.hass)
            try:
                await api.login(user_input["email"], user_input["password"])
                if not api.token:
                    errors["base"] = "auth_failed"
                else:
                    return self.async_create_entry(
                        title=f"Lince GoldCloud ({user_input['email']})",
                        data={"email": user_input["email"], "password": user_input["password"]},
                    )
            except Exception:
                errors["base"] = "auth_failed"

        schema = vol.Schema({
            vol.Required("email"): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")),
            vol.Required("password"): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="password")),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        return LinceGoldCloudOptionsFlow(config_entry)


class LinceGoldCloudOptionsFlow(OptionsFlowWithReload):
    """
    Options Flow per-centrale:
    - init: selezione della centrale
    - edit_details: num_filari, num_radio, 4 multi-select (Home/Away/Night/Vacation)
      con label dinamico "Gx - Nome" e validazione di profili duplicati (mask uguali).
    """

    def __init__(self, entry: config_entries.ConfigEntry):
        self._entry = entry
        self._systems: list[dict] = []
        self._current_sid: int | None = None

    # -------- helpers --------
    @staticmethod
    def _program_display_name_from_access(system: dict | None, code: str) -> str:
        """
        Costruisce il label 'G1 - Porta' usando system['access_data'].
        'code' è in minuscolo ('g1','g2','g3','gext'); accediamo con la chiave minuscola (se presente).
        """
        upper = code.upper()
        access = (system or {}).get("access_data", {}) or {}
        custom = (access.get(code) or "").strip()
        return f"{upper} - {custom}" if custom else upper

    def _get_system_by_sid(self, sid: int) -> dict | None:
        for s in self._systems or []:
            if s.get("id") == sid:
                return s
        return None

    async def async_step_init(self, user_input=None):
        errors = {}
        # Carico la lista centrali usando fetch_systems()
        email = self._entry.data.get("email")
        password = self._entry.data.get("password")
        api = GoldCloudAPI(self.hass)
        try:
            await api.login(email, password)
            self._systems = await api.fetch_systems() or []
        except Exception as e:
            _LOGGER.debug("Impossibile caricare centrali in Options: %s", e)
            systems_config = self._entry.options.get("systems_config", {})
            # Fallback (etichette generiche)
            self._systems = [{"id": sid, "name": f"Centrale {sid}"} for sid in systems_config.keys()]

        options = []
        for s in self._systems:
            sid = s["id"]
            s["access_data"] = await api.fetch_system_access(sid)
            display = f"{s.get('name') or s.get('nome') or f'Centrale {sid}'} - {s.get('id_centrale')}"
            options.append(SelectOptionDict(value=str(sid), label=display))

        if not options:
            # Nessuna centrale configurabile -> esco senza modificare
            return self.async_create_entry(title="", data=self._entry.options)

        schema = vol.Schema({
            vol.Required("system"): SelectSelector(
                SelectSelectorConfig(options=options, multiple=False, mode=SelectSelectorMode.DROPDOWN)
            )
        })

        if user_input is not None:
            self._current_sid = int(user_input["system"])
            return await self.async_step_edit_details()

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def _load_name_for_sid(self, sid: int) -> str:
        """Ritorna 'Nome - id_centrale' preferendo la cache _systems, altrimenti rifetch."""
        name = f"Centrale {sid}"
        cached = self._get_system_by_sid(sid)
        if cached:
            return f"{cached.get('name') or cached.get('nome') or name} - {cached.get('id_centrale')}"
        # rifetch solo se necessario
        email = self._entry.data.get("email")
        password = self._entry.data.get("password")
        try:
            api = GoldCloudAPI(self.hass)
            await api.login(email, password)
            systems = await api.fetch_systems() or []
            for s in systems:
                if s["id"] == sid:
                    return f"{s.get('name') or s.get('nome') or name} - {s.get('id_centrale')}"
        except Exception:
            pass
        return name

    async def async_step_edit_details(self, user_input=None):
        errors: dict[str, str] = {}

        if not self._current_sid:
            return await self.async_step_init()

        sid = self._current_sid
        name = await self._load_name_for_sid(sid)
        system = self._get_system_by_sid(sid)

        systems_config = dict(self._entry.options.get("systems_config", {}))
        arm_profiles = dict(self._entry.options.get("arm_profiles", {}))

        # Opzioni dinamiche "Gx - Nome" usando access_data
        prog_options = [
            SelectOptionDict(value="g1", label=self._program_display_name_from_access(system, "g1")),
            SelectOptionDict(value="g2", label=self._program_display_name_from_access(system, "g2")),
            SelectOptionDict(value="g3", label=self._program_display_name_from_access(system, "g3")),
            SelectOptionDict(value="gext", label=self._program_display_name_from_access(system, "gext")),
        ]

        # Defaults correnti da options salvate
        cfg = systems_config.get(str(sid), {})  # num_filari/num_radio
        prof = arm_profiles.get(str(sid), {"home": [], "away": [], "night": [], "vacation": []})
        defaults = {
            "num_filari": int(cfg.get("num_filari", DEFAULT_FILARI)),
            "num_radio": int(cfg.get("num_radio", DEFAULT_RADIO)),
            "home": list(prof.get("home", [])),
            "away": list(prof.get("away", [])),
            "night": list(prof.get("night", [])),
            "vacation": list(prof.get("vacation", [])),
        }

        # Schema base (senza suggested ancora)
        base_schema = vol.Schema({
            vol.Required("num_filari", default=defaults["num_filari"]): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_FILARI)),
            vol.Required("num_radio", default=defaults["num_radio"]): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_RADIO)),
            vol.Optional("home", default=defaults["home"]): SelectSelector(
                SelectSelectorConfig(options=prog_options, multiple=True, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional("away", default=defaults["away"]): SelectSelector(
                SelectSelectorConfig(options=prog_options, multiple=True, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional("night", default=defaults["night"]): SelectSelector(
                SelectSelectorConfig(options=prog_options, multiple=True, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional("vacation", default=defaults["vacation"]): SelectSelector(
                SelectSelectorConfig(options=prog_options, multiple=True, mode=SelectSelectorMode.DROPDOWN)
            ),
        })

        # Se l'utente ha inviato il form, validiamo e in caso di errore ri-mostriamo con suggested values
        if user_input is not None:
            # Parse sicuro dei numerici
            try:
                nfil = int(user_input.get("num_filari", MAX_FILARI))
                nrad = int(user_input.get("num_radio", MAX_RADIO))
            except Exception:
                nfil, nrad = MAX_FILARI, MAX_RADIO

            # 4 multi-select -> liste
            selected = {
                "home": user_input.get("home", []) or [],
                "away": user_input.get("away", []) or [],
                "night": user_input.get("night", []) or [],
                "vacation": user_input.get("vacation", []) or [],
            }

            # ---- Validazione "mask uniche" tra profili ----
            BIT = {"g1": 1, "g2": 2, "g3": 4, "gext": 8}

            def to_mask(progs: list[str]) -> int:
                m = 0
                for x in progs or []:
                    m |= BIT.get(x, 0)
                return m

            masks = {
                "home": to_mask(selected["home"]),
                "away": to_mask(selected["away"]),
                "night": to_mask(selected["night"]),
                "vacation": to_mask(selected["vacation"]),
            }

            # Conta quante volte appare ciascuna mask non-zero
            count_by_mask: dict[int, int] = {}
            for mode, m in masks.items():
                if m != 0:
                    count_by_mask[m] = count_by_mask.get(m, 0) + 1

            # Modalità duplicate = quelle con una mask non-zero che compare >1 volta
            dup_modes = [mode for mode, m in masks.items() if m != 0 and count_by_mask.get(m, 0) > 1]
            if dup_modes:
                # Banner generale
                errors["base"] = "duplicate_profiles"
                # Errori per-campo: evidenzia i campi incriminati
                for mode in dup_modes:
                    errors[mode] = "duplicate_profile"

                # Mantieni i valori inseriti usando "suggested values"
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
                    description_placeholders={"system_name": name, "system_id": sid},
                )

            # Nessun duplicato -> salvataggio
            systems_config[sid] = {"num_filari": nfil, "num_radio": nrad}
            _LOGGER.debug("Scrivo configurazione di sistema: %s -> %s", sid, systems_config[sid])
            arm_profiles[sid] = selected

            new_options = dict(self._entry.options)
            new_options["systems_config"] = systems_config
            new_options["arm_profiles"] = arm_profiles
            return self.async_create_entry(title="", data=new_options)

        # Primo rendering della form (nessun submit): schema base
        return self.async_show_form(
            step_id="edit_details",
            data_schema=base_schema,
            errors=errors,
            description_placeholders={"system_name": name, "system_id": sid},
        )
    
    
    async def async_step_reauth(self, user_input=None):
        """Handle reauth when token/credentials no longer valid."""
        errors = {}
        entry = self._get_reauth_entry()  # oppure self._reauth_entry se già assegnato altrove
        if user_input is None:
            # ripropone le credenziali (pre‑riempi l'email se vuoi)
            schema = vol.Schema({
                vol.Required("email", default=entry.data.get("email", "")): str,
                vol.Required("password"): str,
            })
            return self.async_show_form(step_id="reauth", data_schema=schema, errors=errors)

        api = GoldCloudAPI(self.hass)
        try:
            await api.login(user_input["email"], user_input["password"])
        except Exception:
            errors["base"] = "auth_failed"
            schema = vol.Schema({
                vol.Required("email", default=user_input["email"]): str,
                vol.Required("password"): str,
            })
            return self.async_show_form(step_id="reauth", data_schema=schema, errors=errors)

        # credenziali ok -> aggiorna il config_entry
        data = dict(entry.data)
        data["email"] = user_input["email"]
        data["password"] = user_input["password"]
        self.hass.config_entries.async_update_entry(entry, data=data)

        # ricarica l'integrazione
        await self.hass.config_entries.async_reload(entry.entry_id)
        return self.async_abort(reason="reauth_successful")

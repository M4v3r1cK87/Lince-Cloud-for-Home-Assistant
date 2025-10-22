"""API comune per operazioni base condivise tra brand."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta, timezone
import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.core import HomeAssistant

from ..const import (
    API_SESSION_URL,
    API_SYSTEMS_URL,
    API_SYSTEM_ACCESS_URL,
    TOKEN_EXPIRY_MINUTES,
    TOKEN_SAFETY_SKEW_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class CommonAPI:
    """API base con funzionalità comuni a tutti i brand."""
    
    def __init__(self, hass: HomeAssistant, email: str | None = None, password: str | None = None):
        self.hass = hass
        self.session = async_get_clientsession(hass)
        self.token: str | None = None
        self.token_expiry: datetime | None = None
        self._email = email
        self._password = password
    
    async def login(self, email: str | None = None, password: str | None = None):
        """Esegue la login al servizio REST - COMUNE A TUTTI I BRAND."""
        if email is None:
            email = self._email
        if password is None:
            password = self._password
            
        payload = {"email": email, "password": password}
        try:
            async with self.session.post(API_SESSION_URL, json=payload) as resp:
                if resp.status not in (200, 201):
                    _LOGGER.error("Login fallita. Status code: %s", resp.status)
                    if resp.status == 401:
                        self.request_reauth_if_needed()
                    raise Exception(f"Login fallita errore {resp.status}")

                data = await resp.json()
                self.token = data.get("token")

                # Calcola scadenza token
                expires_at: datetime | None = None
                try:
                    if isinstance(data, dict):
                        if "expiresAt" in data:
                            expires_at = datetime.fromisoformat(data["expiresAt"])
                        elif "exp" in data:
                            expires_at = datetime.fromtimestamp(int(data["exp"]), tz=timezone.utc)
                        elif "expiresIn" in data:
                            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(data["expiresIn"]))
                except Exception:
                    expires_at = None

                if not expires_at:
                    expires_at = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRY_MINUTES)

                self.token_expiry = expires_at - timedelta(seconds=TOKEN_SAFETY_SKEW_SECONDS)
                _LOGGER.debug("Login effettuata con successo. Token acquisito, scade: %s", self.token_expiry)
                
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            _LOGGER.error("Errore di rete durante la login: %s", e)
            self.token = None
            self.token_expiry = None
            raise
    
    async def fetch_systems(self):
        """Recupera la lista sistemi - COMUNE A TUTTI I BRAND."""
        if self.is_token_expired():
            await self.login()
        
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with self.session.get(API_SYSTEMS_URL, headers=headers) as resp:
                if resp.status == 401:
                    _LOGGER.warning("Token scaduto, ri-autenticando...")
                    await self.login()
                    headers = {"Authorization": f"Bearer {self.token}"}
                    async with self.session.get(API_SYSTEMS_URL, headers=headers) as retry_resp:
                        if retry_resp.status != 200:
                            raise Exception(f"Errore nel recupero sistemi: Error code {retry_resp.status}")
                        return await retry_resp.json()
                elif resp.status != 200:
                    raise Exception(f"Errore nel recupero sistemi: Error code {resp.status}")
                
                return await resp.json()
        except Exception as e:
            _LOGGER.error("Errore durante fetch_systems: %s", e)
            raise
    
    async def fetch_system_access(self, row_id: int):
        """Recupera i dettagli di accesso a un sistema - COMUNE A TUTTI I BRAND."""
        if self.is_token_expired():
            await self.login()
        
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{API_SYSTEM_ACCESS_URL}/{row_id}"
        try:
            async with self.session.get(url, headers=headers) as resp:
                if resp.status == 401:
                    _LOGGER.warning("Token scaduto, ri-autenticando...")
                    await self.login()
                    headers = {"Authorization": f"Bearer {self.token}"}
                    async with self.session.get(url, headers=headers) as retry_resp:
                        if retry_resp.status != 200:
                            raise Exception(f"Errore nel recupero system-access per {row_id}: HTTP {retry_resp.status}")
                        return await retry_resp.json()
                elif resp.status != 200:
                    raise Exception(f"Errore nel recupero system-access per {row_id}: HTTP {resp.status}")
                
                return await resp.json()
        except Exception as e:
            _LOGGER.error("Errore durante fetch_system_access(%s): %s", row_id, e)
            raise
    
    def is_token_expired(self) -> bool:
        """True se il token è scaduto o mancante - COMUNE."""
        if self.token is None or self.token_expiry is None:
            return True
        return datetime.now(timezone.utc) >= self.token_expiry
    
    def get_credentials(self) -> tuple[str | None, str | None]:
        """Espone email/password - COMUNE."""
        return (self._email, self._password)

    def get_auth_header(self) -> dict[str, str]:
        """Header Authorization Bearer - COMUNE."""
        if not self.token:
            raise Exception("Token non disponibile. Effettua il login prima.")
        return {"Authorization": f"Bearer {self.token}"}
    
    def request_reauth_if_needed(self):
        """Richiede reauth se necessario - COMUNE."""
        _LOGGER.warning("Richiesta re-autenticazione necessaria")
        # TODO: Implementare trigger del reauth flow di HA
        
"""Base coordinator class for brand-specific implementations."""
from abc import ABC, abstractmethod
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from typing import Dict, Any, Optional
import logging

_LOGGER = logging.getLogger(__name__)

class BaseCoordinator(DataUpdateCoordinator, ABC):
    """Coordinator base per tutti i brand."""
    
    def __init__(self, hass, api, config_entry, update_interval):
        """Initialize base coordinator."""
        self.api = api
        self.config_entry = config_entry
        
        super().__init__(
            hass,
            _LOGGER,
            name="Lince Alarm Coordinator",
            update_interval=update_interval,
        )
    
    @abstractmethod
    async def _async_update_data(self):
        """Fetch data from API."""
        pass
    
    @abstractmethod
    def _get_counts_for_system(self, system_id: int) -> tuple:
        """Get zone counts for a system."""
        pass
    
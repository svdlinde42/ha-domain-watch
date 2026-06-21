"""Domain Watch sensor."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DomainWatchCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Domain Watch sensor from a config entry."""
    coordinator: DomainWatchCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DomainWatchSensor(coordinator, entry)])


class DomainWatchSensor(CoordinatorEntity[DomainWatchCoordinator], SensorEntity):
    """Sensor showing the total count of detected impostor domains."""

    _attr_has_entity_name = True
    _attr_name = "Detections"
    _attr_icon = "mdi:shield-search"
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(
        self,
        coordinator: DomainWatchCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_detections"

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("count", 0)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "last_checked": self.coordinator.last_checked,
            "last_successful_poll": self.coordinator.last_successful_poll,
            "detections": (self.coordinator.data or {}).get("detections", []),
        }

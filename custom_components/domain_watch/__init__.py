"""Domain Watch integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import DomainWatchCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

_MARK_REVIEWED_SCHEMA = vol.Schema({vol.Required("domain"): cv.string})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Domain Watch from a config entry."""
    coordinator = DomainWatchCoordinator(hass, entry)
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _scan_now(_call: ServiceCall) -> None:
        await coordinator.async_refresh()

    async def _mark_reviewed(call: ServiceCall) -> None:
        domain: str = call.data["domain"]
        if domain in coordinator._seen:
            coordinator._seen[domain]["reviewed"] = True
            await coordinator._store.async_save(coordinator._seen)
            coordinator.async_update_listeners()

    hass.services.async_register(DOMAIN, "scan_now", _scan_now)
    hass.services.async_register(
        DOMAIN, "mark_reviewed", _mark_reviewed, schema=_MARK_REVIEWED_SCHEMA
    )
    entry.async_on_unload(
        lambda: hass.services.async_remove(DOMAIN, "scan_now")
    )
    entry.async_on_unload(
        lambda: hass.services.async_remove(DOMAIN, "mark_reviewed")
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: DomainWatchCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator._store.async_save(coordinator._seen)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload on options change (e.g. interval update)."""
    await hass.config_entries.async_reload(entry.entry_id)

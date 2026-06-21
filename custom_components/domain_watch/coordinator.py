"""Coordinator for Domain Watch."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_INTERVAL,
    CONF_KEYWORDS,
    CONF_NOTIFY,
    DEFAULT_INTERVAL,
    DOMAIN,
    EVENT_DETECTED,
)
from .sources import SOURCES, Detection
from .store import DomainWatchStore

_LOGGER = logging.getLogger(__name__)

_ENABLED_SOURCES = ["crtsh"]


class DomainWatchCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls detection sources and manages the in-memory + persisted state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        interval = entry.options.get(
            CONF_INTERVAL, entry.data.get(CONF_INTERVAL, DEFAULT_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=interval),
        )
        self._entry = entry
        self._store = DomainWatchStore(hass)
        # Authoritative live state — keyed by domain name
        self._seen: dict[str, dict[str, Any]] = {}
        # Sensor reads these directly so they survive UpdateFailed
        self.last_checked: str | None = None
        self.last_successful_poll: str | None = None

    async def async_setup(self) -> None:
        """Load persisted detections before the first coordinator refresh."""
        self._seen = await self._store.async_load()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch new detections, persist, and return sensor payload."""
        self.last_checked = dt_util.utcnow().isoformat()
        keywords: list[str] = self._entry.data[CONF_KEYWORDS]
        session = async_get_clientsession(self.hass)

        try:
            all_detections: list[Detection] = []
            for key in _ENABLED_SOURCES:
                source = SOURCES[key]()
                all_detections.extend(await source.fetch(session, keywords))
        except Exception as exc:
            raise UpdateFailed(f"crt.sh fetch failed: {exc}") from exc

        new = [d for d in all_detections if d.domain not in self._seen]
        if new:
            await self._record_detections(new)

        self.last_successful_poll = self.last_checked
        return {
            "count": len(self._seen),
            "detections": list(self._seen.values()),
        }

    async def _record_detections(self, detections: list[Detection]) -> None:
        """Write new detections to in-memory state and flush the store.

        This is the single write path — called only from _async_update_data.
        Store is flushed before events are fired so state is durable if a
        subsequent step fails.
        """
        now = dt_util.utcnow().isoformat()
        for d in detections:
            self._seen[d.domain] = {
                "first_seen": now,
                "source": d.source,
                "reviewed": False,
                **d.evidence,
            }
            _LOGGER.info("New impostor domain detected: %s", d.domain)

        await self._store.async_save(self._seen)

        for d in detections:
            self.hass.bus.async_fire(EVENT_DETECTED, {"domain": d.domain, **self._seen[d.domain]})

        await self._async_notify(detections)

    async def _async_notify(self, detections: list[Detection]) -> None:
        """Call the configured HA notify service for each new detection."""
        raw = self._entry.options.get(CONF_NOTIFY, "").strip()
        if not raw:
            return
        # Accept both "notify.service_name" and "service_name"
        service = raw.removeprefix("notify.")
        for d in detections:
            record = self._seen[d.domain]
            lines = [f"New impostor domain: {d.domain}"]
            if "not_before" in record:
                lines.append(f"Cert issued: {record['not_before']}")
            try:
                await self.hass.services.async_call(
                    "notify",
                    service,
                    {"title": "Domain Watch", "message": "\n".join(lines)},
                    blocking=False,
                )
            except Exception as exc:
                _LOGGER.warning("Domain Watch notification failed for %s: %s", d.domain, exc)

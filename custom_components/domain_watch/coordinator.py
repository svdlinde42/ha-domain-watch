"""Coordinator for Domain Watch."""
from __future__ import annotations

import asyncio
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
    RDAP_BASE_URL,
    RDAP_TIMEOUT,
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
        """Persist new detections, enrich via RDAP, then fire events.

        Order: raw store flush → RDAP enrich (parallel) → enriched flush →
        fire events → notify. Raw flush runs first so detections are never
        lost even if RDAP or downstream steps fail.
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

        rdap_results = await asyncio.gather(
            *[self._enrich_rdap(d.domain) for d in detections]
        )
        needs_flush = False
        for d, rdap in zip(detections, rdap_results):
            if rdap:
                self._seen[d.domain].update(rdap)
                needs_flush = True
        if needs_flush:
            await self._store.async_save(self._seen)

        for d in detections:
            self.hass.bus.async_fire(
                EVENT_DETECTED, {"domain": d.domain, **self._seen[d.domain]}
            )

        await self._async_notify(detections)

    async def _enrich_rdap(self, domain: str) -> dict[str, Any]:
        """Fetch RDAP registration data for a domain. Returns {} on any failure."""
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(RDAP_TIMEOUT):
                async with session.get(f"{RDAP_BASE_URL}{domain}") as resp:
                    if resp.status != 200:
                        return {}
                    data = await resp.json(content_type=None)
            return _parse_rdap(data)
        except Exception as exc:
            _LOGGER.debug("RDAP lookup failed for %s: %s", domain, exc)
            return {}

    async def _async_notify(self, detections: list[Detection]) -> None:
        """Call the configured HA notify service for each new detection."""
        raw = self._entry.options.get(CONF_NOTIFY, "").strip()
        if not raw:
            return
        service = raw.removeprefix("notify.")
        for d in detections:
            record = self._seen[d.domain]
            lines = [f"New impostor domain: {d.domain}"]
            if "registrar" in record:
                lines.append(f"Registrar: {record['registrar']}")
            if "registration_date" in record:
                lines.append(f"Registered: {record['registration_date']}")
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
                _LOGGER.warning(
                    "Domain Watch notification failed for %s: %s", d.domain, exc
                )


def _parse_rdap(data: dict) -> dict[str, Any]:
    """Extract registrar, registration_date, and nameservers from an RDAP response.

    Absent fields are omitted entirely — never None or empty string.
    """
    result: dict[str, Any] = {}

    for event in data.get("events", []):
        if event.get("eventAction") == "registration":
            date = (event.get("eventDate") or "").strip()
            if date:
                result["registration_date"] = date
            break

    for entity in data.get("entities", []):
        if "registrar" in entity.get("roles", []):
            vcard = entity.get("vcardArray") or [None, []]
            for item in vcard[1]:
                if item[0] == "fn" and item[3]:
                    result["registrar"] = item[3]
                    break
            break

    nameservers = [
        ns["ldhName"].lower()
        for ns in data.get("nameservers", [])
        if ns.get("ldhName")
    ]
    if nameservers:
        result["nameservers"] = nameservers

    return result

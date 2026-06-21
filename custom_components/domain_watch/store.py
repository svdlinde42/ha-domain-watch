"""Persistent store for Domain Watch."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORE_KEY, STORE_VERSION

_LOGGER = logging.getLogger(__name__)


class DomainWatchStore:
    """Thin wrapper around HA's storage helper.

    The Store instance is injected so unit tests can provide a stub
    without requiring a real HomeAssistant instance.
    """

    def __init__(self, hass: HomeAssistant, store: Store | None = None) -> None:
        self._store: Store = store or Store(hass, STORE_VERSION, STORE_KEY)

    async def async_load(self) -> dict[str, Any]:
        """Load from storage, running schema migration if needed.

        Returns the domain dict (keyed by domain name).
        """
        raw: dict[str, Any] = await self._store.async_load() or {}

        version = raw.get("schema_version", 0)
        if version == 0:
            # v0 → v1: flat domain dict, wrap it
            raw = {"schema_version": STORE_VERSION, "domains": raw}

        return dict(raw.get("domains", {}))

    async def async_save(self, domains: dict[str, Any]) -> None:
        """Persist the domain dict to storage."""
        data = {"schema_version": STORE_VERSION, "domains": domains}
        try:
            await self._store.async_save(data)
        except Exception as exc:
            _LOGGER.warning("Domain Watch store flush failed: %s", exc)

"""Certificate Transparency source via crt.sh."""
from __future__ import annotations

import asyncio
import logging

import aiohttp

from . import Detection, Source
from ..const import CRTSH_BASE_URL, CRTSH_MAX_RETRIES, CRTSH_TIMEOUT

_LOGGER = logging.getLogger(__name__)

_QUERY_PARAMS = "output=json&exclude=expired&deduplicate=Y"


class CrtShSource(Source):
    """Detection source backed by the crt.sh Certificate Transparency API."""

    name = "crtsh"

    async def fetch(
        self,
        session: aiohttp.ClientSession,
        keywords: list[str],
    ) -> list[Detection]:
        """Fetch and deduplicate detections for all keywords."""
        seen: dict[str, Detection] = {}
        for keyword in keywords:
            for detection in await self._fetch_keyword(session, keyword):
                if detection.domain not in seen:
                    seen[detection.domain] = detection
        return list(seen.values())

    async def _fetch_keyword(
        self,
        session: aiohttp.ClientSession,
        keyword: str,
    ) -> list[Detection]:
        url = f"{CRTSH_BASE_URL}?q=%25{keyword}%25&{_QUERY_PARAMS}"
        last_exc: Exception | None = None

        for attempt in range(1, CRTSH_MAX_RETRIES + 1):
            try:
                async with asyncio.timeout(CRTSH_TIMEOUT):
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                        data: list[dict] = await resp.json(content_type=None)
                return _parse(data)
            except Exception as exc:
                last_exc = exc
                if attempt < CRTSH_MAX_RETRIES:
                    wait = 2**attempt
                    _LOGGER.warning(
                        "crt.sh attempt %d/%d failed for %r: %s — retrying in %ds",
                        attempt,
                        CRTSH_MAX_RETRIES,
                        keyword,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)

        _LOGGER.error(
            "crt.sh failed for %r after %d attempts: %s",
            keyword,
            CRTSH_MAX_RETRIES,
            last_exc,
        )
        raise last_exc  # noqa: TRY201 — coordinator wraps in UpdateFailed


def _parse(data: list[dict]) -> list[Detection]:
    """Extract unique normalised Detection objects from a crt.sh response.

    When the same domain appears in multiple certificates, the entry with
    the latest not_before timestamp is kept.
    """
    best: dict[str, Detection] = {}

    for entry in data:
        cert_id = entry.get("id")
        issuer_name: str = entry.get("issuer_name", "")
        not_before: str = entry.get("not_before", "")

        for raw_name in entry.get("name_value", "").split("\n"):
            domain = raw_name.strip().lstrip("*.").lower()
            if not domain:
                continue

            evidence: dict = {}
            if cert_id is not None:
                evidence["cert_id"] = cert_id
            if issuer_name:
                evidence["issuer_name"] = issuer_name
            if not_before:
                evidence["not_before"] = not_before

            candidate = Detection(domain=domain, source="crtsh", evidence=evidence)

            if domain not in best:
                best[domain] = candidate
            elif not_before > best[domain].evidence.get("not_before", ""):
                best[domain] = candidate

    return list(best.values())

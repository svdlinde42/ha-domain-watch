"""Source ABC, Detection dataclass, and source registry."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiohttp


@dataclass
class Detection:
    """A single detected domain."""

    domain: str
    source: str
    evidence: dict = field(default_factory=dict)


class Source(ABC):
    """Abstract base for detection sources."""

    name: str

    @abstractmethod
    async def fetch(
        self,
        session: aiohttp.ClientSession,
        keywords: list[str],
    ) -> list[Detection]:
        """Fetch detections for the given keywords."""


# Registry — static, populated at import time.
# Coordinator iterates enabled source keys against this dict.
from .crtsh import CrtShSource  # noqa: E402

SOURCES: dict[str, type[Source]] = {
    "crtsh": CrtShSource,
}

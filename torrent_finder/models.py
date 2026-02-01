from __future__ import annotations

"""
Data models for Torrent Finder.

Short, sweet, and wearing a plaster. Just enough structure to keep the
rest of the codebase from tripping over itself.
"""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class Candidate:
    """Represents a single torrent candidate, charming as me."""

    magnet: str
    title: Optional[str] = None
    seeders: Optional[int] = None
    leechers: Optional[int] = None
    size_bytes: Optional[int] = None
    source: str = "torznab"

    def rank_tuple(self) -> Tuple[int, float, int]:
        """
        Produce a ranking tuple for torrents.

        Returns
        -------
        tuple
            ``(seeders, ratio, has_counts)`` - enough info to pick what you need.
        """

        seeders = self.seeders or 0
        leechers = self.leechers or 0
        ratio = seeders / (leechers + 1.0)
        has_counts = 1 if (self.seeders is not None or self.leechers is not None) else 0
        return seeders, ratio, has_counts

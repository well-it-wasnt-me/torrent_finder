from __future__ import annotations

"""
High-level torrent selection logic.

Listens to the Torznab, assign a score and crowns the winner without breaking a sweat.
"""

import logging
from typing import List, Optional

from .models import Candidate
from .torznab import TorznabClient


class TorrentFinder:
    """Wraps TorznabClient to fetch candidates and choose the best one."""

    def __init__(self, torznab_client: TorznabClient):
        """
        Parameters
        ----------
        torznab_client : TorznabClient
            I refuse to write what this is.
        """

        self._torznab = torznab_client

    def find_candidates(self, title: str, debug: bool = False) -> List[Candidate]:
        """
        Pull a fresh list of matching torrents.

        Parameters
        ----------
        title : str
            Search term supplied by the user.
        debug : bool, optional
            Enable verbose Torznab logging, default is ``False``.

        Returns
        -------
        list[Candidate]
            All candidate torrents the indexer coughed up.
        """

        candidates = self._torznab.search(title, debug=debug)
        logging.debug("Finder received %d candidates", len(candidates))
        return candidates

    def pick_best(self, candidates: List[Candidate]) -> Optional[Candidate]:
        """
        Select the highest-ranked candidate.

        Parameters
        ----------
        candidates : list[Candidate]
            Potential torrents waiting to be judged.

        Returns
        -------
        Candidate | None
            The top-ranked candidate, or ``None`` if the search is empty.
        """

        if not candidates:
            return None

        best = max(candidates, key=lambda candidate: candidate.rank_tuple())
        logging.debug(
            "Best candidate: %s | seeders=%s leechers=%s",
            best.title or "(no title)",
            best.seeders,
            best.leechers,
        )
        return best

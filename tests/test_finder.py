from __future__ import annotations

"""Tests for the TorrentFinder—making sure the talent show stays honest."""

import unittest
from unittest.mock import MagicMock

from torrent_finder.finder import TorrentFinder
from torrent_finder.models import Candidate


class TorrentFinderTests(unittest.TestCase):
    """Confirm that TorrentFinder can spot a winner without night-vision goggles."""

    def test_pick_best_returns_highest_rank(self) -> None:
        candidates = [
            Candidate(magnet="magnet:one", title="One", seeders=10, leechers=5),
            Candidate(magnet="magnet:two", title="Two", seeders=20, leechers=10),
            Candidate(magnet="magnet:three", title="Three", seeders=15, leechers=1),
        ]
        finder = TorrentFinder(torznab_client=MagicMock())
        best = finder.pick_best(candidates)
        self.assertIsNotNone(best)
        self.assertEqual(best.magnet, "magnet:two")

    def test_find_candidates_delegates_to_client(self) -> None:
        mock_client = MagicMock()
        mock_client.search.return_value = [Candidate(magnet="magnet:one")]
        finder = TorrentFinder(mock_client)
        result = finder.find_candidates("test", debug=True)
        mock_client.search.assert_called_once_with("test", debug=True)
        self.assertEqual(result[0].magnet, "magnet:one")


if __name__ == "__main__":
    unittest.main()

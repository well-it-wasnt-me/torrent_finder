from __future__ import annotations

from torrent_finder.models import Candidate
from torrent_finder.telegram.messages import MessageFactory
from torrent_finder.transmission import TransmissionController


def test_format_status_table_includes_id_and_bar() -> None:
    statuses = [
        TransmissionController.TorrentStatus(
            torrent_id=7,
            name="Test Torrent",
            status="downloading",
            percent_done=0.5,
            eta="5m",
        )
    ]
    report = MessageFactory().format_status_report(statuses)
    assert "ID  : 7" in report
    assert "State: actively downloading" in report
    assert "#####-----" in report


def test_format_candidate_card_contains_size_and_source() -> None:
    candidate = Candidate(
        magnet="magnet:?xt=urn:btih:ABC123",
        title="Example",
        seeders=10,
        leechers=2,
        size_bytes=1048576,
        source="indexer-one",
    )
    lines = MessageFactory().format_candidate_card(1, candidate)
    assert lines[0].startswith("1. Example")
    assert "seeds: 10" in lines[1]
    assert "size: 1.0 MB" in lines[1]
    assert "source: indexer-one" in lines[1]

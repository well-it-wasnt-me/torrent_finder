from __future__ import annotations

"""Tests for Torznab-specific helpers."""

import threading
import xml.etree.ElementTree as ET

from torrent_finder.config import TorznabConfig
from torrent_finder.torznab import TorznabClient


def _build_item(inner_xml: str) -> ET.Element:
    xml = f'<item xmlns:torznab="http://torznab.com/schemas/2015/feed">{inner_xml}</item>'
    return ET.fromstring(xml)


def test_extract_magnet_from_guid() -> None:
    item = _build_item("<guid>magnet:?xt=urn:btih:ABC123</guid>")
    assert TorznabClient._extract_magnet(item) == "magnet:?xt=urn:btih:ABC123"


def test_extract_magnet_from_attr() -> None:
    item = _build_item('<torznab:attr name="magnetUrl" value="magnet:?xt=urn:btih:DEF456" />')
    assert TorznabClient._extract_magnet(item) == "magnet:?xt=urn:btih:DEF456"


def _make_client() -> TorznabClient:
    cfg = TorznabConfig(url="http://example.com", apikey="KEY")
    return TorznabClient(cfg)


def test_session_reused_within_thread() -> None:
    client = _make_client()
    session_one = client._get_session()
    session_two = client._get_session()
    assert session_one is session_two


def test_session_is_thread_local() -> None:
    client = _make_client()
    sessions = []

    def grab_session() -> None:
        sessions.append(client._get_session())

    threads = [threading.Thread(target=grab_session) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]

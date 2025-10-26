from __future__ import annotations

"""Tests for Torznab-specific helpers."""

import xml.etree.ElementTree as ET

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

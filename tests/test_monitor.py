from __future__ import annotations

import base64

from torrent_finder.telegram.monitor import DownloadMonitor


def test_extract_info_hash_from_hex_magnet() -> None:
    magnet = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567"
    assert DownloadMonitor._extract_info_hash(magnet) == "0123456789abcdef0123456789abcdef01234567"


def test_extract_info_hash_from_base32_magnet() -> None:
    hex_hash = "0123456789abcdef0123456789abcdef01234567"
    base32_hash = base64.b32encode(bytes.fromhex(hex_hash)).decode("ascii").strip("=")
    magnet = f"magnet:?xt=urn:btih:{base32_hash}"
    assert DownloadMonitor._extract_info_hash(magnet) == hex_hash

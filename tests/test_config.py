from __future__ import annotations

"""Tests for configuration helpers—because even the rodeo clown needs a safety net."""

import json
import tempfile
import unittest
from pathlib import Path

from torrent_finder.config import (
    AppConfig,
    ConfigError,
    ConfigLoader,
    LoggingConfig,
    TorznabConfig,
    TransmissionConfig,
)


class ConfigLoaderTests(unittest.TestCase):
    """Exercises ConfigLoader so the crowd doesn't boo when parsing fails."""

    def _write_config(self, data) -> Path:
        temp_dir = tempfile.mkdtemp()
        path = Path(temp_dir) / "config.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_load_valid_config(self) -> None:
        payload = {
            "torznab": {"url": "http://example.com", "apikey": "KEY", "categories": "2000"},
            "transmission": {"download_dir": "/downloads"},
        }
        loader = ConfigLoader(self._write_config(payload))
        config = loader.load()
        self.assertIsInstance(config, AppConfig)
        self.assertEqual(config.torznab.url, "http://example.com")
        self.assertEqual(config.transmission.download_dir, "/downloads")

    def test_missing_section_raises(self) -> None:
        payload = {"torznab": {"url": "http://example.com", "apikey": "KEY"}}
        loader = ConfigLoader(self._write_config(payload))
        with self.assertRaises(ConfigError):
            loader.load()

    def test_apply_overrides_respects_none_values(self) -> None:
        config = AppConfig(
            torznab=TorznabConfig(url="http://example.com", apikey="KEY", categories="1000"),
            transmission=TransmissionConfig(download_dir="/downloads", host="localhost", port=9091),
            logging=LoggingConfig(level="INFO"),
        )

        overrides = {
            "download_dir": None,  # should not override existing download dir
            "host": "192.168.1.2",
            "port": None,  # should keep existing port
        }
        updated = ConfigLoader.apply_overrides(config, overrides)
        self.assertEqual(updated.transmission.download_dir, "/downloads")
        self.assertEqual(updated.transmission.host, "192.168.1.2")
        self.assertEqual(updated.transmission.port, 9091)


if __name__ == "__main__":
    unittest.main()

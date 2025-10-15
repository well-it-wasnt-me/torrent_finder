from __future__ import annotations

"""Tests that keep the Transmission controller from drunk-dialing."""

import unittest
from unittest.mock import MagicMock, patch

from torrent_finder.config import TransmissionConfig
from torrent_finder.transmission import TransmissionController


class TransmissionControllerTests(unittest.TestCase):
    """Stress-test RPC vs CLI behavior without waking the actual daemon."""
    @patch("torrent_finder.transmission.shutil.which", return_value="/usr/bin/transmission-remote")
    def test_ensure_available_remote(self, which_mock) -> None:
        config = TransmissionConfig(download_dir="/downloads", use_rpc=False)
        controller = TransmissionController(config)
        controller.ensure_available()
        which_mock.assert_called_once_with("transmission-remote")

    @patch("torrent_finder.transmission.shutil.which", return_value=None)
    def test_ensure_available_remote_missing_binary(self, which_mock) -> None:
        config = TransmissionConfig(download_dir="/downloads", use_rpc=False)
        controller = TransmissionController(config)
        with self.assertRaises(SystemExit):
            controller.ensure_available()

    @patch("torrent_finder.transmission.transmission_rpc", MagicMock())
    def test_ensure_available_rpc(self) -> None:
        config = TransmissionConfig(download_dir="/downloads", use_rpc=True)
        controller = TransmissionController(config)
        controller.ensure_available()

    @patch("torrent_finder.transmission.subprocess.run")
    @patch("torrent_finder.transmission.shutil.which", return_value="/usr/bin/transmission-remote")
    def test_add_remote_invokes_cli(self, which_mock, run_mock) -> None:
        run_mock.return_value = MagicMock(returncode=0, stdout="added", stderr="")
        config = TransmissionConfig(
            download_dir="/downloads",
            use_rpc=False,
            host="host",
            port=1234,
            auth="user:pass",
            start=False,
        )
        controller = TransmissionController(config)
        controller.add("magnet:?xt=123", start_override=True)
        run_mock.assert_called_once()
        args = run_mock.call_args[0][0]
        self.assertIn("--auth", args)
        self.assertIn("--start", args)

    @patch("torrent_finder.transmission.transmission_rpc.Client")
    def test_add_rpc_invokes_client(self, client_mock) -> None:
        config = TransmissionConfig(
            download_dir="/downloads",
            use_rpc=True,
            host="host",
            port=9091,
            username="user",
            password="pass",
            start=True,
        )
        controller = TransmissionController(config)
        controller.add("magnet:?xt=123")
        client_mock.assert_called_once_with(host="host", port=9091, username="user", password="pass")
        client_mock.return_value.add_torrent.assert_called_once()


if __name__ == "__main__":
    unittest.main()

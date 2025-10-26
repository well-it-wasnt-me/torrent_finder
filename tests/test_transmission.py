from __future__ import annotations

"""Tests that keep the Transmission controller from drunk-dialing."""

import unittest
from datetime import timedelta
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

    @patch("torrent_finder.transmission.transmission_rpc.Client")
    def test_list_torrents_rpc_filters_active(self, client_mock) -> None:
        class DummyTorrent:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        client_mock.return_value.get_torrents.return_value = [
            DummyTorrent(
                id=1, name="Active", status="downloading", percentDone=0.5, eta=120, magnetLink="magnet:?xt=aaaa"
            ),
            DummyTorrent(id=2, name="Done", status="seeding", percentDone=1.0, eta=-1, magnetLink="magnet:?xt=bbbb"),
        ]

        config = TransmissionConfig(
            download_dir="/downloads", use_rpc=True, host="host", port=9091, username="user", password="pass"
        )
        controller = TransmissionController(config)
        statuses = controller.list_torrents(active_only=True)
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].name, "Active")
        self.assertFalse(statuses[0].is_complete)

    @patch("torrent_finder.transmission.subprocess.run")
    def test_list_torrents_remote_parses_output(self, run_mock) -> None:
        run_mock.return_value = MagicMock(
            returncode=0,
            stdout=(
                "Name: Alpha Download\n"
                "ID: 4\n"
                "Status: Downloading\n"
                "Percent Done: 40%\n"
                "ETA: 5 mins\n"
                "Magnet: magnet:?xt=alpha\n"
                "\n"
                "Name: Beta Finished\n"
                "ID: 5\n"
                "Status: Seeding\n"
                "Percent Done: 100%\n"
                "ETA: None\n"
            ),
            stderr="",
        )
        config = TransmissionConfig(download_dir="/downloads", use_rpc=False, host="host", port=9091, auth="user:pass")
        controller = TransmissionController(config)
        statuses = controller.list_torrents(active_only=False)
        self.assertEqual(len(statuses), 2)
        self.assertEqual(statuses[0].torrent_id, 4)
        self.assertEqual(statuses[0].eta, "5 mins")
        active = controller.list_torrents(active_only=True)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].name, "Alpha Download")

    def test_format_eta_handles_timedelta_and_floats(self) -> None:
        self.assertEqual(TransmissionController._format_eta_seconds(90), "1m")
        self.assertEqual(TransmissionController._format_eta_seconds(90.5), "1m")
        self.assertEqual(TransmissionController._format_eta_seconds(timedelta(seconds=30)), "30s")


if __name__ == "__main__":
    unittest.main()

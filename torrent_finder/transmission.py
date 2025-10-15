from __future__ import annotations

"""
Transmission integration with the bedside manner of me after a bottle of whiskey.

This module keeps the conversation going between Torrent Finder and
Transmission, whether you're dialing RPC or hollering through the CLI.
"""

import logging
import shutil
import subprocess
from typing import Optional

from .config import TransmissionConfig

try:
    import transmission_rpc  # type: ignore
except Exception:
    transmission_rpc = None  # type: ignore


class TransmissionController:
    """Coordinate adds to Transmission."""

    def __init__(self, config: TransmissionConfig):
        """
        Parameters
        ----------
        config : TransmissionConfig
            Connection details, credentials, and start-mode preferences.
        """

        self.config = config

    def ensure_available(self) -> None:
        """
        Verify that the configured Transmission interface is reachable.

        Raises
        ------
        SystemExit
            If neither the RPC library nor the CLI binary can be found, depending on the mode.
        """

        if self.config.use_rpc:
            if transmission_rpc is None:
                raise SystemExit("Install transmission-rpc: pip install transmission-rpc")
        else:
            if not shutil.which("transmission-remote"):
                raise SystemExit("transmission-remote not found in PATH.")

    def add(self, magnet: str, start_override: Optional[bool] = None) -> None:
        """
        Add the magnet link via the configured interface.

        Parameters
        ----------
        magnet : str
            Magnet URI to send to Transmission.
        start_override : bool, optional
            Override the start/paused behavior for just this call.
        """

        start = self.config.start if start_override is None else start_override
        if self.config.use_rpc:
            self._add_via_rpc(magnet, start)
        else:
            self._add_via_remote(magnet, start)

    def _add_via_remote(self, magnet: str, start: bool) -> None:
        """
        Use ``transmission-remote`` to add a torrent.

        Parameters
        ----------
        magnet : str
            Magnet link to add.
        start : bool
            Whether to start the torrent immediately.

        Raises
        ------
        SystemExit
            When the CLI command bails with a non-zero status.
        """

        target = f"{self.config.host}:{self.config.port}"
        args = ["transmission-remote", target, "--add", magnet]
        if self.config.auth:
            args.extend(["--auth", self.config.auth])
        if self.config.download_dir:
            args.extend(["--download-dir", self.config.download_dir])
        args.append("--start" if start else "--no-start")

        logging.debug("Running transmission-remote with args: %s", args)

        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise SystemExit(
                "transmission-remote failed {code}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}".format(
                    code=result.returncode, stdout=result.stdout, stderr=result.stderr
                )
            )
        if result.stdout:
            logging.info(result.stdout.strip())

    def _add_via_rpc(self, magnet: str, start: bool) -> None:
        """
        Use the Transmission RPC API to add a torrent.

        Parameters
        ----------
        magnet : str
            Magnet link to add.
        start : bool
            Whether to start the torrent immediately.

        Raises
        ------
        SystemExit
            If the RPC client is unavailable.
        """

        if transmission_rpc is None:
            raise SystemExit("Install transmission-rpc: pip install transmission-rpc")

        client = transmission_rpc.Client(
            host=self.config.host,
            port=self.config.port,
            username=self.config.username,
            password=self.config.password,
        )
        client.add_torrent(magnet, download_dir=self.config.download_dir or None, paused=not start)

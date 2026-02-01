from __future__ import annotations

"""
Transmission integration with the bedside manner of me after a bottle of whiskey.

This module keeps the conversation going between Torrent Finder and
Transmission, whether you're dialing RPC or hollering through the CLI.
"""

import logging
import re
import shutil
import subprocess
from datetime import timedelta
from dataclasses import dataclass
from typing import List, Optional, Union

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

    @dataclass
    class TorrentStatus:
        torrent_id: Optional[int]
        name: str
        status: str
        percent_done: float
        eta: Optional[str]
        magnet: Optional[str] = None
        info_hash: Optional[str] = None

        @property
        def is_complete(self) -> bool:
            return self.percent_done >= 99.9

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

    def add(self, magnet: str, start_override: Optional[bool] = None, download_dir: Optional[str] = None) -> None:
        """
        Add the magnet link via the configured interface.

        Parameters
        ----------
        magnet : str
            Magnet URI to send to Transmission.
        start_override : bool, optional
            Override the start/paused behavior for just this call.
        download_dir : str, optional
            Target download directory for this torrent, falling back to the configured default.
        """

        start = self.config.start if start_override is None else start_override
        target_dir = download_dir or self.config.download_dir
        if self.config.use_rpc:
            self._add_via_rpc(magnet, start, target_dir)
        else:
            self._add_via_remote(magnet, start, target_dir)

    def stop_and_remove(self, torrent_id: int, delete_data: bool = False) -> None:
        """
        Stop a torrent and remove it from Transmission.

        Parameters
        ----------
        torrent_id : int
            Transmission torrent ID.
        delete_data : bool, optional
            When True, also delete local data (default False).
        """

        self.ensure_available()
        if self.config.use_rpc:
            self._stop_and_remove_rpc(torrent_id, delete_data)
        else:
            self._stop_and_remove_remote(torrent_id, delete_data)

    def list_torrents(self, active_only: bool = False) -> List["TransmissionController.TorrentStatus"]:
        """
        Fetch torrent statuses from Transmission.

        Parameters
        ----------
        active_only : bool
            When True, only include torrents that have not finished downloading.
        """

        statuses = self._list_via_rpc() if self.config.use_rpc else self._list_via_remote()
        if active_only:
            statuses = [status for status in statuses if not status.is_complete]
        return statuses

    def _add_via_remote(self, magnet: str, start: bool, download_dir: Optional[str]) -> None:
        """
        Use ``transmission-remote`` to add a torrent.

        Parameters
        ----------
        magnet : str
            Magnet link to add.
        start : bool
            Whether to start the torrent immediately.
        download_dir : str, optional
            Destination folder for this torrent.

        Raises
        ------
        SystemExit
            When the CLI command bails with a non-zero status.
        """

        target = f"{self.config.host}:{self.config.port}"
        args = ["transmission-remote", target, "--add", magnet]
        if self.config.auth:
            args.extend(["--auth", self.config.auth])
        if download_dir:
            args.extend(["--download-dir", download_dir])
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

    def _add_via_rpc(self, magnet: str, start: bool, download_dir: Optional[str]) -> None:
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

        client = self._build_rpc_client()
        client.add_torrent(magnet, download_dir=download_dir or None, paused=not start)

    def _stop_and_remove_rpc(self, torrent_id: int, delete_data: bool) -> None:
        if transmission_rpc is None:
            raise SystemExit("Install transmission-rpc: pip install transmission-rpc")
        client = self._build_rpc_client()
        client.stop_torrent(torrent_id)
        client.remove_torrent(torrent_id, delete_data=delete_data)

    def _stop_and_remove_remote(self, torrent_id: int, delete_data: bool) -> None:
        target = f"{self.config.host}:{self.config.port}"
        base_args = ["transmission-remote", target, "--torrent", str(torrent_id)]
        if self.config.auth:
            base_args.extend(["--auth", self.config.auth])

        for action in ("--stop", "--remove-and-delete" if delete_data else "--remove"):
            args = [*base_args, action]
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

    def _build_rpc_client(self):
        if transmission_rpc is None:
            raise SystemExit("Install transmission-rpc: pip install transmission-rpc")
        return transmission_rpc.Client(
            host=self.config.host,
            port=self.config.port,
            username=self.config.username,
            password=self.config.password,
        )

    def _list_via_rpc(self) -> List["TransmissionController.TorrentStatus"]:
        client = self._build_rpc_client()
        torrents = client.get_torrents()
        statuses: List[TransmissionController.TorrentStatus] = []
        for torrent in torrents:
            raw_percent = getattr(torrent, "percentDone", None)
            if raw_percent is None:
                raw_percent = getattr(torrent, "percent_done", None)
            percent = float(raw_percent) if raw_percent is not None else 0.0
            if percent <= 1.0:
                percent *= 100.0
            status_text = str(getattr(torrent, "status", "unknown"))
            eta_seconds = getattr(torrent, "eta", None)
            magnet = getattr(torrent, "magnetLink", None)
            info_hash = getattr(torrent, "hashString", None) or getattr(torrent, "hash_string", None)
            torrent_id = getattr(torrent, "id", None)
            name = getattr(torrent, "name", "") or "(untitled)"
            statuses.append(
                TransmissionController.TorrentStatus(
                    torrent_id=torrent_id,
                    name=name,
                    status=status_text,
                    percent_done=percent,
                    eta=self._format_eta_seconds(eta_seconds),
                    magnet=magnet,
                    info_hash=self._normalize_info_hash(str(info_hash)) if info_hash else None,
                )
            )
        return statuses

    def _list_via_remote(self) -> List["TransmissionController.TorrentStatus"]:
        target = f"{self.config.host}:{self.config.port}"
        args = ["transmission-remote", target, "--torrent", "all", "--info"]
        if self.config.auth:
            args.extend(["--auth", self.config.auth])

        logging.debug("Running transmission-remote for status with args: %s", args)

        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise SystemExit(
                "transmission-remote status failed {code}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}".format(
                    code=result.returncode, stdout=result.stdout, stderr=result.stderr
                )
            )

        return self._parse_remote_info(result.stdout)

    def _parse_remote_info(self, stdout: str) -> List["TransmissionController.TorrentStatus"]:
        statuses: List[TransmissionController.TorrentStatus] = []
        if not stdout:
            return statuses

        current: dict[str, str] = {}

        def flush_current() -> None:
            if not current:
                return
            name = current.get("name")
            if not name:
                current.clear()
                return
            torrent_id = self._safe_int(current.get("id"))
            percent = self._safe_float(current.get("percent"))
            eta_value = self._clean_eta(current.get("eta"))
            info_hash = self._normalize_info_hash(current.get("hash"))
            statuses.append(
                TransmissionController.TorrentStatus(
                    torrent_id=torrent_id,
                    name=name,
                    status=current.get("status", "unknown"),
                    percent_done=percent,
                    eta=eta_value,
                    magnet=current.get("magnet"),
                    info_hash=info_hash,
                )
            )
            current.clear()

        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if not line:
                flush_current()
                continue
            if ":" not in line:
                continue

            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            mapped_key = self._map_remote_key(key)
            if not mapped_key:
                continue
            if mapped_key == "name" and "name" in current:
                flush_current()
            if mapped_key == "percent":
                current[mapped_key] = value.replace("%", "").strip()
            else:
                current[mapped_key] = value

        flush_current()
        return statuses

    @staticmethod
    def _map_remote_key(key: str) -> Optional[str]:
        mapping = {
            "name": "name",
            "torrent": "name",
            "id": "id",
            "percent done": "percent",
            "progress": "percent",
            "status": "status",
            "state": "status",
            "eta": "eta",
            "magnet": "magnet",
            "hash": "hash",
        }
        return mapping.get(key)

    @staticmethod
    def _safe_int(value: Optional[str]) -> Optional[int]:
        if value is None:
            return None
        match = re.search(r"\d+", value)
        if not match:
            return None
        try:
            return int(match.group())
        except ValueError:
            return None

    @staticmethod
    def _safe_float(value: Optional[str]) -> float:
        if value is None:
            return 0.0
        try:
            return float(value)
        except ValueError:
            return 0.0

    @staticmethod
    def _clean_eta(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        lowered = value.lower()
        if lowered in {"unknown", "none", "n/a"}:
            return None
        return value

    @staticmethod
    def _normalize_info_hash(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        return re.sub(r"\s+", "", value).lower()

    @staticmethod
    def _format_eta_seconds(seconds: Optional[Union[int, float, timedelta]]) -> Optional[str]:
        if seconds is None:
            return None
        if isinstance(seconds, timedelta):
            total_seconds = int(seconds.total_seconds())
        else:
            try:
                total_seconds = int(float(seconds))
            except (TypeError, ValueError):
                return None
        if total_seconds < 0:
            return None
        minutes, sec = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if not parts:
            parts.append(f"{sec}s")
        return " ".join(parts)

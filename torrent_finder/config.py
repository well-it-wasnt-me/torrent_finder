from __future__ import annotations

"""
Configuration plumbing for Torrent Finder.

Flips tables if anything looks shady.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; MagnetFinder/torznab-only 1.0)"
DEFAULT_REQUEST_TIMEOUT = 12.0
DEFAULT_SLEEP_BETWEEN_REQUESTS = 0.6


class ConfigError(Exception):
    """Raised when configuration loading faceplants harder than you after reading this."""


@dataclass
class TorznabConfig:
    """Settings for Torznab/Jackett, a.k.a. the talent scout."""

    url: str
    apikey: str
    categories: Optional[str] = None
    user_agent: str = DEFAULT_USER_AGENT
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    sleep_between_requests: float = DEFAULT_SLEEP_BETWEEN_REQUESTS

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TorznabConfig":
        """
        Build an instance from raw configuration data.

        Parameters
        ----------
        data : dict[str, Any]
            Chunk of config JSON scoped to Torznab.

        Returns
        -------
        TorznabConfig
            Fully hydrated config object ready for that first HTTP handshake.

        Raises
        ------
        ConfigError
            If the essentials are missing, like forgetting your car key inside the car and the car is closed.
        """

        try:
            url = data["url"]
            apikey = data["apikey"]
        except KeyError as exc:
            raise ConfigError(f"Missing Torznab setting: {exc.args[0]}") from exc

        return cls(
            url=url,
            apikey=apikey,
            categories=data.get("categories"),
            user_agent=data.get("user_agent", DEFAULT_USER_AGENT),
            request_timeout=float(data.get("request_timeout", DEFAULT_REQUEST_TIMEOUT)),
            sleep_between_requests=float(data.get("sleep_between_requests", DEFAULT_SLEEP_BETWEEN_REQUESTS)),
        )


@dataclass
class TransmissionConfig:
    """Transmission connection details: who we call, how we call them, and whether to bring alcohol."""

    download_dir: str
    start: bool = False
    use_rpc: bool = False
    host: str = "localhost"
    port: int = 9091
    username: Optional[str] = None
    password: Optional[str] = None
    auth: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TransmissionConfig":
        """
        Build a TransmissionConfig from a JSON blob.

        Parameters
        ----------
        data : dict[str, Any]
            Configuration chunk dedicated to Transmission.

        Returns
        -------
        TransmissionConfig
            The settings TransmissionController expects.

        Raises
        ------
        ConfigError
            If the download directory is missing, because we like knowing where the loot goes.
        """

        try:
            download_dir = data["download_dir"]
        except KeyError as exc:
            raise ConfigError(f"Missing Transmission setting: {exc.args[0]}") from exc

        return cls(
            download_dir=download_dir,
            start=bool(data.get("start", False)),
            use_rpc=bool(data.get("use_rpc", False)),
            host=data.get("host", "localhost"),
            port=int(data.get("port", 9091)),
            username=data.get("username"),
            password=data.get("password"),
            auth=data.get("auth"),
        )


@dataclass
class LoggingConfig:
    """Lightweight logging configuration for when INFO just isn't loud enough."""

    level: str = "INFO"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "LoggingConfig":
        """
        Create a logging config from a dict.

        Parameters
        ----------
        data : dict[str, Any] | None
            Optional logging section. ``None`` means we stick with INFO like responsible adults.

        Returns
        -------
        LoggingConfig
            The final logging level wrapped in a dataclass hug.
        """

        if data is None:
            return cls()
        return cls(level=str(data.get("level", "INFO")).upper())


@dataclass
class AppConfig:
    """Aggregate configuration with Torznab, Transmission, and logging in one friendly bundle."""

    torznab: TorznabConfig
    transmission: TransmissionConfig
    logging: LoggingConfig

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        """
        Stitch together the full configuration set from JSON.

        Parameters
        ----------
        data : dict[str, Any]
            Entire configuration payload.

        Returns
        -------
        AppConfig
            Everything the app needs to know, tied up in a dataclass bow.

        Raises
        ------
        ConfigError
            If you're missing a top-level section, which is the config equivalent of forgetting your only child at a bus stop.
        """

        try:
            torznab_data = data["torznab"]
            transmission_data = data["transmission"]
        except KeyError as exc:
            raise ConfigError(f"Missing top-level section: {exc.args[0]}") from exc

        logging_data = data.get("logging")

        return cls(
            torznab=TorznabConfig.from_dict(torznab_data),
            transmission=TransmissionConfig.from_dict(transmission_data),
            logging=LoggingConfig.from_dict(logging_data),
        )


class ConfigLoader:
    """Loads application configuration from JSON files and delivers it."""

    def __init__(self, path: str | Path):
        """
        Parameters
        ----------
        path : str | Path
            File system path where the config JSON resides, probably fell down the couch.
        """

        self.path = Path(path)

    def load(self) -> AppConfig:
        """
        Read and validate the configuration file.

        Returns
        -------
        AppConfig
            The fully parsed configuration bundle.

        Raises
        ------
        ConfigError
            When the file is missing or invalid.
        """

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ConfigError(f"Configuration file not found: {self.path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON configuration: {exc.msg}") from exc

        return AppConfig.from_dict(payload)

    @staticmethod
    def apply_overrides(config: AppConfig, overrides: dict[str, Any]) -> AppConfig:
        """
        Update the in-memory configuration with CLI overrides.

        Parameters
        ----------
        config : AppConfig
            The baseline configuration, straight from the JSON file.
        overrides : dict[str, Any]
            CLI overrides.

        Returns
        -------
        AppConfig
            The same object, adjusted in place just for this whim.
        """

        tx = config.transmission
        tor = config.torznab

        if "download_dir" in overrides and overrides["download_dir"]:
            tx.download_dir = overrides["download_dir"]
        if "start" in overrides and overrides["start"] is not None:
            tx.start = overrides["start"]
        if "use_rpc" in overrides and overrides["use_rpc"] is not None:
            tx.use_rpc = overrides["use_rpc"]
        if "host" in overrides and overrides["host"]:
            tx.host = overrides["host"]
        if "port" in overrides and overrides["port"] is not None:
            tx.port = int(overrides["port"])
        if overrides.get("username") is not None:
            tx.username = overrides["username"]
        if overrides.get("password") is not None:
            tx.password = overrides["password"]
        if overrides.get("auth") is not None:
            tx.auth = overrides["auth"]
        if "categories" in overrides and overrides["categories"] is not None:
            tor.categories = overrides["categories"]

        return config

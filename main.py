#!/usr/bin/env python3
from __future__ import annotations

"""
Main entry point for the Torrent Finder CLI.

This module keeps the pace brisk: load the config,
call the folks who know what they're doing, and deliver the magnet
straight to Transmission.
"""

import argparse
import logging
from typing import Any

from torrent_finder.config import AppConfig, ConfigError, ConfigLoader
from torrent_finder.finder import TorrentFinder
from torrent_finder.torznab import TorznabClient
from torrent_finder.transmission import TransmissionController


def parse_args() -> argparse.Namespace:
    """
    Build and parse the CLI arguments.

    Returns
    -------
    argparse.Namespace
        The parsed arguments, ready for a night out with the main routine.
    """

    parser = argparse.ArgumentParser(description="Find the best Torznab magnet and send it to Transmission.")
    parser.add_argument("title", help="Title to search for.")
    parser.add_argument("--config", default="config.json", help="Path to the JSON configuration file.")

    parser.add_argument("--download-dir", help="Override download directory for this run.")
    parser.add_argument(
        "--start", dest="start", action="store_const", const=True, default=None, help="Start download immediately."
    )
    parser.add_argument(
        "--no-start", dest="start", action="store_const", const=False, help="Add paused regardless of config."
    )
    parser.add_argument(
        "--use-rpc",
        dest="use_rpc",
        action="store_const",
        const=True,
        default=None,
        help="Use Transmission RPC even if config says otherwise.",
    )
    parser.add_argument(
        "--use-remote",
        dest="use_rpc",
        action="store_const",
        const=False,
        help="Use transmission-remote CLI even if config says otherwise.",
    )
    parser.add_argument("--host", help="Override Transmission host.")
    parser.add_argument("--port", type=int, help="Override Transmission port.")
    parser.add_argument("--username", help="Transmission username (RPC).")
    parser.add_argument("--password", help="Transmission password (RPC).")
    parser.add_argument("--auth", help="transmission-remote auth user:pass (remote mode).")
    parser.add_argument("--categories", help="Override Torznab categories for this run.")

    parser.add_argument("--debug", action="store_true", help="Enable debug logging regardless of config.")
    return parser.parse_args()


def configure_logging(config: AppConfig, debug: bool) -> None:
    """
    Funnel the logging level into place.

    Parameters
    ----------
    config : AppConfig
        Freshly loaded configuration with its chosen verbosity.
    debug : bool
        When ``True`` we skip straight to DEBUG.
    """

    level_name = "DEBUG" if debug else config.logging.level.upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def collect_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """
    Gather CLI overrides into a single place.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments that may contain last-minute whims.

    Returns
    -------
    dict[str, Any]
        A mapping of override keys to values, ready for the config mixer.
    """

    return {
        "download_dir": args.download_dir,
        "start": args.start,
        "use_rpc": args.use_rpc,
        "host": args.host,
        "port": args.port,
        "username": args.username,
        "password": args.password,
        "auth": args.auth,
        "categories": args.categories,
    }


def main() -> None:
    """
    Run the CLI workflow.

    Steps
    -----
    1. Parse CLI arguments like a polite bartender.
    2. Load config.
    3. Ask Torznab for leads, pick the winner, and forward it to Transmission.
    """

    args = parse_args()

    loader = ConfigLoader(args.config)
    try:
        config = loader.load()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    overrides = collect_overrides(args)
    config = ConfigLoader.apply_overrides(config, overrides)

    configure_logging(config, args.debug)

    logging.info("Searching Torznab for: %s", args.title)
    torznab_client = TorznabClient(config.torznab)
    finder = TorrentFinder(torznab_client)
    candidates = finder.find_candidates(args.title, debug=args.debug)
    if not candidates:
        logging.error("Torznab returned no matching items. Check URL/key, indexers, or try a broader query.")
        raise SystemExit("ERROR: No candidates found from Torznab.")

    best = finder.pick_best(candidates)
    if not best:
        raise SystemExit("ERROR: Could not select a candidate.")

    logging.info("Selected: %s | seeders=%s leechers=%s", best.title or "(no title)", best.seeders, best.leechers)
    logging.debug("Magnet: %s", best.magnet)

    transmission = TransmissionController(config.transmission)
    transmission.ensure_available()
    transmission.add(best.magnet, start_override=args.start)

    logging.info("Done.")


if __name__ == "__main__":
    main()

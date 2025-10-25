# API Overview

The Python modules ship with docstrings and type hints so you can script your own workflows. Highlighted entry points:

- **`torrent_finder.config`** – loads and validates `config.json`, exposes dataclasses for Torznab, Transmission, Telegram, and logging.
- **`torrent_finder.torznab`** – lightweight Torznab client that wraps Jackett and produces `Candidate` objects.
- **`torrent_finder.finder`** – orchestration logic that ranks candidates and selects the best torrent.
- **`torrent_finder.models`** – dataclasses (`Candidate`) and helper methods used during ranking.
- **`torrent_finder.transmission`** – wrapper around Transmission RPC or `transmission-remote` for adding magnets and verifying availability.
- **`main.py`** – CLI glue code that wires everything together and applies command-line overrides.
- **`telegram_bot.py`** – chat controller built with `python-telegram-bot` that surfaces search/download to Telegram.

Import these modules directly in your own scripts, or use them as reference when extending the CLI. All public classes and functions are annotated, so IDEs and `pydoc` will surface the same information that Sphinx previously generated.

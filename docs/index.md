# torrent_finder documentation

`torrent_finder` automates the hunt for the "best" torrent by pulling results from a Torznab/Jackett
endpoint, ranking the candidates, and handing the winner directly to Transmission. The project favors
simple configuration, readable logging, and a workflow that you can script or invoke ad-hoc.

## Key capabilities

- Query Torznab/Jackett feeds and score candidates by seeders and leechers.
- Apply defaults from `config.json` but allow one-off CLI overrides.
- Dispatch the chosen magnet to Transmission via RPC or `transmission-remote`.

## Command-line pit stop

```bash
python main.py "The Big Lebowski" \
  --config config.json \
  --start \
  --category movies
```

## What you'll find here

- A quick path to installation and verification.
- Guidance on shaping `config.json` for Torznab, Transmission, Telegram, and logging.
- Usage patterns for the CLI and Telegram bot, plus an API overview for extending the toolkit.

Use the navigation links to jump into setup, usage, configuration, or the API reference. Run the site locally with `mkdocs serve`.

# Usage

The CLI glues together configuration loading, Torznab searching, and Transmission handoff. You only need to supply a title, but most configuration fields can be overridden per invocation.

## Basic search

```bash
python main.py "Drunken Master"
```

The command above loads `config.json` from the project root, queries the configured Torznab feed, logs the ranked candidates, and sends the top magnet to Transmission using the defaults defined in the configuration file.

## Command-line options

- `title`: required positional argument that specifies the search phrase sent to Torznab.
- `--config PATH`: alternate path to the JSON configuration file (defaults to `config.json`).
- `--download-dir DIR`: temporary download directory that overrides the Transmission `download_dir` setting.
- `--start / --no-start`: force the torrent to start immediately or be added in a paused state.
- `--use-rpc / --use-remote`: switch between Transmission's RPC interface and the `transmission-remote` CLI regardless of what the configuration specifies.
- `--host, --port`: override the Transmission host and port when connecting over RPC or `transmission-remote`.
- `--username, --password`: credentials for Transmission RPC mode.
- `--auth`: `user:pass` combination for the `transmission-remote` CLI.
- `--categories`: replace the Torznab category filter for this run (comma-separated list).
- `--debug`: elevate logging to `DEBUG` regardless of the configuration.

## Workflow tips

- Use the overrides to script batch downloads without touching `config.json`.
- Pair `--debug` with a temporary `--download-dir` when diagnosing indexer or Transmission issues.
- If `transmission-remote` is not found, toggle RPC mode with `--use-rpc` (requires `transmission-rpc` to be installed in the active environment).

## Telegram chat control

A lightweight Telegram bot ships with the project for couch-friendly control:

```bash
python telegram_bot.py --config config.json
```

Flow:

1. Send `search Cowboy Bepop` (or any `search <keywords>` query).
2. The bot replies with the top five ranked results and seed/peer stats.
3. Respond with the list number to add that torrent to Transmission.
4. Send `status` to check in on active downloads; the bot auto-notifies you when a Telegram-triggered download finishes.

Populate the `telegram` section of `config.json` with your `bot_token` (and optional `chat_id`) or override with `--token` / `--chat-id`. Tweak `--max-results` when you want more or fewer options. The bot shares the same `config.json` as the CLI, so keep your Torznab/Transmission settings up to date there.

!!! tip
    Auto-notifications for finished torrents rely on the Telegram JobQueue. Install the optional dependency via `pip install "python-telegram-bot[job-queue]"` so the bot can schedule those background checks.

Need to troubleshoot Jackett responses? Run with `--telemetry-level DEBUG` or pass the dedicated
`--torznab-debug` flag to log a preview of the Torznab feed whenever it comes back empty.

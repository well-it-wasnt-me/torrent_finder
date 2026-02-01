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
- `--category`: friendly presets for common filters (`movies`, `tv`, `comics`, `software`, `software-mac`, `software-win`, `zip`, `all`).
- `--debug`: elevate logging to `DEBUG` regardless of the configuration.

### Category presets cheat sheet

| Preset | Torznab IDs | Example |
| ------ | ----------- | ------- |
| `movies` | `2000` | `python main.py "Dune" --category movies` |
| `tv` | `5000` | `python main.py "The Bear" --category tv` |
| `comics` | `7030` | `python main.py "Saga" --category comics` |
| `software` | `4000` | `python main.py "Blender" --category software` |
| `software-mac` | `4050` | `python main.py "Final Cut" --category software-mac` |
| `software-win` | `4010,4020` | `python main.py "Office" --category software-win` |
| `zip` | `8000` | `python main.py "Archive" --category zip` |
| `all` | *(no filter)* | `python main.py "Dune" --category all` |

The presets simply override `torznab.categories`, so existing config values stay untouched for subsequent runs.

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

1. Run `/start` to open the inline menu, then tap **Search** or a category button (or type `search Cowboy Bepop`).
2. Add an optional category keyword upfront—`search movies dune`, `search tv s04`, `search comics saga`, `search software mac final cut`, `search zip files pack`, or `search all dune`—to reuse the CLI presets inside Telegram.
3. The bot replies with ranked cards (title, seeds, size, source), plus Next/Prev paging and a **More like** shortcut.
4. Respond with the list number or tap the inline button to pick one; you will then be prompted to pick a download folder from a set of buttons before it gets sent to Transmission.
5. Update the folder presets in `telegram_bot.py` (`_download_dir_options`) to reflect your Transmission directories—the defaults are just examples and can be expanded with your own paths.
6. Send `status` (or tap **Status**) to list every torrent with a quick read on its Transmission state (downloading, seeding, stopped, etc.). The status block includes the Transmission ID for removals, plus Active/All filters and a refresh button that edits in place. The bot auto-notifies you when a Telegram-triggered download finishes regardless.

Populate the `telegram` section of `config.json` with your `bot_token` (and optional `chat_id`) or override with `--token` / `--chat-id`. Tweak `--max-results` when you want more or fewer options. The bot shares the same `config.json` as the CLI, so keep your Torznab/Transmission settings up to date there.

Kick the conversation off with `/start` to open the inline menu (Search/Status/Help + category buttons) for tap-friendly control.

**Commands recap**

- `search <query>` – runs a search; prepend the category keywords listed above for quick filters.
- `<number>` or tapping the inline button – sends that specific result to Transmission.
- `/start_magnet <magnet_url>` – send a magnet link straight to Transmission.
- `/remove <id or name>` – stop and remove a torrent (prefer the numeric ID from `status`).
- `status` – lists every torrent and adds a short explanation of each Transmission state (also available via the **Status** button).
- `help` / `/help` – prints the command list again.

> [!TIP]
> Auto-notifications for finished torrents prefer the Telegram JobQueue. Install
> the optional dependency via `pip install "python-telegram-bot[job-queue]"` for native
> scheduling; without it, the bot falls back to an internal asyncio poller so the pings still happen.

Need to troubleshoot Jackett responses? Run with `--telemetry-level DEBUG` or pass the dedicated
`--torznab-debug` flag to log a preview of the Torznab feed whenever it comes back empty.

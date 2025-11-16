# Torrent Finder

Folks kept asking me 
>How do I get my *perfectly legal* movie/file/show lined up and ready to download without 
>juggling between unreachable websites, ads and all like I’m auditioning for Cirque du Soleil? 

So I got tired of answering and wrote this toolkit instead. 
Pour a drink and let `torrent_finder` do the heavy lifting.

## What This Contraption Does
- Talks to your friendly neighborhood Torznab/Jackett endpoint and hunts down magnets that actually match what you asked for.
- Ranks the hits by seeders (because buffering is for people who make salad at barbecues).
- Tosses the winner straight into Transmission.
- Wraps it all in a tidy class-based architecture with a configuration file so you can stop memorizing stuff.

## Installation (A.K.A. "Some Assembly Required")
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
If you plan on using the RPC interface and Python throws a fit about `transmission_rpc`, that means you skipped the third line. Don’t be that person.

## Configure Before You Accelerate
Copy `config.example.json` to `config.json` and fill in your grown-up details.

yes, the defaults are just suggestions:

```json
{
  "torznab": {
    "url": "http://localhost:9117/jackett/torznab/all",
    "apikey": "CHANGE_ME",
    "categories": "2000"
  },
  "transmission": {
    "download_dir": "/path/to/save",
    "start": false,
    "use_rpc": true,
    "host": "localhost",
    "port": 9091,
    "username": "transmission",
    "password": "transmission"
  },
  "logging": {
    "level": "INFO"
  }
}
```

**Highlights**:
- `torznab.url` and `torznab.apikey` are the secret handshake to your indexers. No handshake, no magnets.
- `torznab.categories` keeps the noise down. Comma-separated, like a grocery list, minus the kale—and now you can pass `--category movies|tv|software|software-mac|software-win|all` for the common presets without remembering IDs.
- `transmission.start` decides if Transmission hits the gas or waits politely in park.
- `logging.level` understands "DEBUG", "INFO", "WARNING", and "ERROR". No, "LOUD" is not an option.
- Add a `telegram` section when you want the chat bot to pick up credentials:

```json
"telegram": {
  "bot_token": "123456:ABC",
  "chat_id": "123456789"
}
```

`chat_id` is optional but keeps random chats from hijacking your downloads.

## Bootstrap Jackett + FlareSolverr
If you do not already have Jackett and FlareSolverr on your machine, the project ships with a helper:

```bash
python scripts/setup_indexing_stack.py
```

What it does:
- Detects running instances before doing anything destructive.
- Writes a `docker-compose.yml` (linuxserver/jackett + ghcr.io/flaresolverr) under `~/.local/share/torrent_finder/stack` and brings it up via Docker.
- Links Jackett to FlareSolverr and scaffolds the compose stack so you can begin adding trackers (indexers are **not** added automatically).
- Prints the local Jackett URL so you can finish setup manually—log in, add the indexers you care about, and copy the Torznab API key back into `config.json`. (Jackett does not expose that key via automation.)
- Updates `config.json` when `torznab.url`/`apikey` are still on the placeholder values once you paste the key.

Use `--help` for overrides (custom ports, tracker list, skipping Docker, or forcing a config update). Docker has to be installed if you want the automatic install; otherwise run with `--no-docker` and the script will only perform the API wiring.

> **After bootstrapping:** open the printed Jackett URL (usually `http://127.0.0.1:9117`), walk through the UI to add one or more indexers (e.g. Jackett → `Add Indexer`), then copy the API key from the Jackett dashboard into `config.json`. This step is manual—Jackett currently offers no supported way to script API-key retrieval or indexer imports without user interaction.

## Fire It Up
```bash
python main.py "I wil not write the tile of the movie here"
```
Need to override something on a whim?
```bash
python main.py "Nature Documentary" \
  --config config.json \
  --download-dir "/external/drive" \
  --start \
  --username transmission \
  --password secret \
  --category movies
```
Prefer raw Torznab IDs? Keep `--categories "2000,5000"` around for custom combos—the presets just save you from memorizing them.

### Category presets

| Preset        | Under the hood      | Sample CLI usage                          | Telegram equivalent                     |
|---------------|---------------------|-------------------------------------------|-----------------------------------------|
| `movies`      | `2000`              | `--category movies`                       | `search movies dune`                    |
| `tv`          | `5000`              | `--category tv`                           | `search tv the bear`                    |
| `software`    | `4000`              | `--category software`                     | `search software blender`               |
| `software-mac`| `4050`              | `--category software-mac`                 | `search software mac final cut`         |
| `software-win`| `4010,4020`         | `--category software-win`                 | `search software win office`            |
| `all`         | no filter           | `--category all`                          | `search all dune`                       |

The presets piggyback on top of `torznab.categories`, so they work without touching `config.json`. Mix and match with the usual overrides to script one-off runs.

## Telegram Chat Control
Want to drive searches from your phone? Spin up the Telegram bot:

```bash
pip install -r requirements.txt  # once
python telegram_bot.py --token "<bot api token>" --config config.json
```

Flow:
- Send `search the movie title` to the bot.
- Add an optional category word—`search movies dune`, `search tv s04`, `search software mac final cut`, or `search all dune`—to switch Torznab filters without editing the config.
- It responds with the top five matches (seed/leech counts included).
- Reply with the list number *or tap the inline button* to push that magnet into Transmission.
- Send `status` (or tap the button under the results) any time to see active downloads and their progress; run `status all` when you need every torrent plus a quick explanation of each state (downloading, seeding, stopped, etc.).
- The bot pings you once a Telegram-triggered download finishes so you can hit play quicker.

The token can also come from the `telegram.bot_token` section in `config.json` (or `TELEGRAM_TOKEN`). Add
`telegram.chat_id` if you want to lock the bot to a single chat/channel. Use `--max-results` to tweak
how many options are shown. `/start` drops a tiny reply keyboard with Status/Help shortcuts so you can keep tapping instead of typing.

**Quick commands**
- `search <query>` – fetches results; prefix with `movies`, `tv`, `software`, `software mac`, `software win`, or `all` to reuse the presets listed above.
- `<number>` – selects one of the previous results (inline buttons do the same).
- `status` – checks Transmission (also available as a dedicated button and inline callback).
- `status all` – lists every torrent and annotates Transmission’s reported state (downloading, seeding, stopped, queued).
- `help` / `/help` – shows the condensed cheat-sheet.

> **Heads up:** background status polling uses Python Telegram Bot's JobQueue. Install the optional extra via
> `pip install "python-telegram-bot[job-queue]"` to enable the completion pings.

### Getting the Telegram token and chat ID

1. DM [@BotFather](https://t.me/BotFather), run `/newbot`, follow the prompts, and copy the API token it prints (looks like `1234567890:ABC...`).
2. Drop that token into `config.json` under `telegram.bot_token` (or export `TELEGRAM_TOKEN`, or pass `--token` when running the bot).
3. (Optional) Lock the bot to a single chat: start a conversation with your bot (or add it to the group), send `/start`, then run `curl "https://api.telegram.org/bot<token>/getUpdates"`; copy the `chat.id` shown in the JSON. Alternatively, DM [@userinfobot](https://t.me/userinfobot) and reuse the `Id` it reports.
4. Store that numeric ID in `telegram.chat_id`.

Skip the chat ID to let the bot respond to any chat during initial testing.

Crank telemetry up with `--telemetry-level DEBUG` (or pass `--torznab-debug`) when you need the raw Jackett
response previews logged to stdout—handy when a feed returns zero results and you want to know why.

## Formatting
Install the dev tooling once and let Black keep indentation sane:

```bash
pip install -r requirements-dev.txt
black .
```

Use `black --check .` locally or in CI to make sure everything stays formatted.

## Docs
The documentation site now uses MkDocs.

```bash
pip install -r requirements.txt  # already includes mkdocs
mkdocs serve                     # live-reload server at http://127.0.0.1:8000/
mkdocs build                     # produce the static site in ./site
```

## Behind the Curtain
- `torrent_finder/config.py` loads and validates JSON like a responsible adult.
- `torrent_finder/torznab.py` handles the Torznab tango, filters titles, and keeps notes on seeders and leechers.
- `torrent_finder/finder.py` picks the winner.
- `torrent_finder/transmission.py` talks to Transmission.
- `main.py` glues it together, handles overrides, and logs the play-by-play.

## Troubleshooting
- **"No matching items"**: Either your indexers are empty or you searched for something that doesn’t exist. Maybe don’t.
- **"transmission-remote not found"**: Install Transmission or switch to RPC. Wishing real hard won’t make it appear.
- **"Invalid JSON configuration"**: You missed a comma. Computers are picky like that.

## (Un)Requested Advice
Use it for your own stuff, or with permission. You get caught pirating, that’s on you. I’ll be over here, sipping whiskey, guinness and enjoying the show.

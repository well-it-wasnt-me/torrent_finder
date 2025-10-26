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
- `torznab.categories` keeps the noise down. Comma-separated, like a grocery list, minus the kale.
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
- Links Jackett to FlareSolverr, imports a handful of public trackers (`1337x`, `torrentgalaxyclone`, `yts`, `eztv`, `nyaasi`, `limetorrents` by default), and surfaces the API key.
- Updates `config.json` when `torznab.url`/`apikey` are still on the placeholder values.

Use `--help` for overrides (custom ports, tracker list, skipping Docker, or forcing a config update). Docker has to be installed if you want the automatic install; otherwise run with `--no-docker` and the script will only perform the API wiring.

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
  --categories "2000,5000"
```

## Telegram Chat Control
Want to drive searches from your phone? Spin up the Telegram bot:

```bash
pip install -r requirements.txt  # once
python telegram_bot.py --token "<bot api token>" --config config.json
```

Flow:
- Send `search the movie title` to the bot.
- It responds with the top five matches (seed/leech counts included).
- Reply with the list number to push that magnet into Transmission.
- Send `status` any time to see active downloads and their progress.
- The bot pings you once a Telegram-triggered download finishes so you can hit play quicker.

The token can also come from the `telegram.bot_token` section in `config.json` (or `TELEGRAM_TOKEN`). Add
`telegram.chat_id` if you want to lock the bot to a single chat/channel. Use `--max-results` to tweak
how many options are shown.

> **Heads up:** background status polling uses Python Telegram Bot's JobQueue. Install the optional extra via
> `pip install "python-telegram-bot[job-queue]"` to enable the completion pings.

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

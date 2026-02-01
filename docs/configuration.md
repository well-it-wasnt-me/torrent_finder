# Configuration

The application reads a single JSON document (`config.json` by default) that controls Torznab queries, Transmission interaction, Telegram access, and log verbosity. Start from the sample file that ships in the repository, then adjust the sections described below.

## Example layout

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
  },
  "telegram": {
    "bot_token": "123456:ABC",
    "chat_id": "123456789"
  }
}
```

## Torznab section

- `url`: Base Torznab/Jackett endpoint (required).
- `apikey`: API key for the feed (required).
- `categories`: optional comma-separated category identifiers to filter search results. Use the CLI shortcut `--category movies|tv|comics|software|software-mac|software-win|zip|all` (or issue `search movies <title>` inside Telegram) when you prefer named presets over raw IDs.
- `user_agent`: custom HTTP `User-Agent` string. Defaults to `Mozilla/5.0 (compatible; MagnetFinder/torznab-only 1.0)`.
- `request_timeout`: timeout in seconds for Torznab requests (float, default `12.0`).
- `sleep_between_requests`: delay in seconds between requests to avoid hammering the indexer (float, default `0.6`).

## Transmission section

- `download_dir`: destination directory for completed or in-progress downloads (required).
- `start`: whether torrents should start immediately after being added (default `false`).
- `use_rpc`: set to `true` to use the Transmission RPC interface; `false` switches to the `transmission-remote` CLI.
- `host`, `port`: where Transmission is reachable. Defaults to `localhost`/`9091`.
- `username`, `password`: RPC credentials when `use_rpc` is enabled. Leave `null` to connect without authentication.
- `auth`: `user:pass` credentials for the `transmission-remote` CLI.

## Logging section

- `level`: one of `DEBUG`, `INFO`, `WARNING`, `ERROR`. Defaults to `INFO`. Use `--debug` on the CLI to override temporarily.

## Telegram section

- `bot_token`: Telegram bot token obtained from BotFather. Required when this section is present and enables the chat controller.
- `chat_id`: optional numeric chat ID. When provided, only that chat (or channel) may send commands to the bot. Leave it empty to accept messages from any chat that knows the bot’s username.

Once configured, the bot accepts `search <title>` requests (including the same preset keywords used by the CLI), replies with tappable inline buttons for each result, lets you send plain numbers to start downloads, and exposes `status`, `help`, `/start`, `/start_magnet`, and `/remove` shortcuts—handy when you want to drive everything from your phone.

### Obtaining the Telegram credentials

1. Open Telegram and talk to [@BotFather](https://t.me/BotFather).
2. Run `/newbot`, answer the prompts (name + username), and copy the token BotFather prints (looks like `1234567890:ABC...`). Paste this into `telegram.bot_token` (or set `TELEGRAM_TOKEN`/`--token`).
3. (Optional) To restrict the bot to a single chat ID:
   - Start a conversation with the bot (or add it to your group/channel), send `/start`, then run `curl "https://api.telegram.org/bot<token>/getUpdates"` and read the `chat.id` value.
   - Alternatively DM [@userinfobot](https://t.me/userinfobot) and reuse the `Id` it reports for you/the chat.
4. Store that numeric value in `telegram.chat_id`.

Leave `chat_id` blank if you want to interact with the bot from any chat during initial setup/testing.

## Applying overrides

Every command-line flag documented in [Usage](usage.md) maps to a configuration key. CLI overrides are applied after `config.json` is loaded, letting you script temporary tweaks without editing the JSON file.

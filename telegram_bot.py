#!/usr/bin/env python3
from __future__ import annotations

"""
Telegram entrypoint for torrent_finder.

Usage
-----
python telegram_bot.py --token <bot-token> [--config config.json]
"""

import argparse
import logging
import os
from typing import Awaitable, Callable, List, Optional, Tuple

from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from torrent_finder.config import AppConfig, ConfigError, ConfigLoader
from torrent_finder.finder import TorrentFinder
from torrent_finder.torznab import TorznabClient
from torrent_finder.transmission import TransmissionController
from torrent_finder.telegram import (
    DownloadMonitor,
    KeyboardBuilder,
    MessageFactory,
    TelegramTorrentController,
    UserSessions,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_DOWNLOAD_DIR_OPTIONS: List[Tuple[str, str]] = [
    ("Movies (default)", "/var/lib/transmission-daemon/downloads/movies"),
    ("TV Show", "/var/lib/transmission-daemon/downloads/tv_show"),
    ("Other", "/var/lib/transmission-daemon/downloads"),
]


def _chain_lifecycle_callback(
    existing: Optional[Callable[[Application], Awaitable[None]]],
    new_callback: Callable[[Application], Awaitable[None]],
) -> Callable[[Application], Awaitable[None]]:
    if existing is None:
        return new_callback

    async def combined(application: Application) -> None:
        await existing(application)
        await new_callback(application)

    return combined


async def _set_bot_commands(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Show quick instructions and keyboard"),
            BotCommand("help", "Show usage and search tips"),
            BotCommand("status", "List torrents and their state"),
            BotCommand("start_magnet", "Queue a magnet link directly"),
            BotCommand("remove", "Stop and remove a torrent"),
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram bot that controls torrent_finder.")
    parser.add_argument("--config", default="config.json", help="Path to torrent_finder configuration file.")
    parser.add_argument("--token", help="Telegram Bot API token (overrides config/env).")
    parser.add_argument(
        "--chat-id",
        type=int,
        help="Restrict the bot to a single Telegram chat ID (overrides config).",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="How many top candidates to send back to Telegram users (default: 5).",
    )
    parser.add_argument(
        "--listen-updates",
        default="polling",
        choices=("polling",),
        help="Transport used to receive Telegram updates (polling only for now).",
    )
    parser.add_argument(
        "--telemetry-level",
        default="INFO",
        help="Logging level for stdout (DEBUG/INFO/WARNING/ERROR).",
    )
    parser.add_argument(
        "--torznab-debug",
        action="store_true",
        help="Emit verbose Torznab logs (implied when --telemetry-level DEBUG).",
    )
    return parser.parse_args()


def build_app(
    config: AppConfig,
    token: str,
    max_results: int,
    chat_id: Optional[int],
    torznab_debug: bool,
) -> Application:
    torznab = TorznabClient(config.torznab)
    finder = TorrentFinder(torznab)
    transmission = TransmissionController(config.transmission)
    sessions = UserSessions()
    keyboards = KeyboardBuilder(
        selection_prefix=TelegramTorrentController.SELECTION_PREFIX,
        dir_selection_prefix=TelegramTorrentController.DIR_SELECTION_PREFIX,
        menu_callback=TelegramTorrentController.MENU_CALLBACK,
        search_callback=TelegramTorrentController.SEARCH_CALLBACK,
        help_callback=TelegramTorrentController.HELP_CALLBACK,
        status_all_callback=TelegramTorrentController.STATUS_ALL_CALLBACK,
        status_active_callback=TelegramTorrentController.STATUS_ACTIVE_CALLBACK,
        status_refresh_prefix=TelegramTorrentController.STATUS_REFRESH_PREFIX,
        cancel_callback=TelegramTorrentController.CANCEL_CALLBACK,
        category_prefix=TelegramTorrentController.CATEGORY_PREFIX,
        page_prefix=TelegramTorrentController.PAGE_PREFIX,
        more_like_prefix=TelegramTorrentController.MORE_LIKE_PREFIX,
        download_dir_options=DEFAULT_DOWNLOAD_DIR_OPTIONS,
    )
    messages = MessageFactory()
    monitor = DownloadMonitor(transmission)
    controller = TelegramTorrentController(
        finder=finder,
        transmission=transmission,
        sessions=sessions,
        keyboards=keyboards,
        messages=messages,
        download_monitor=monitor,
        max_results=max_results,
        allowed_chat_id=chat_id,
        torznab_debug=torznab_debug,
    )

    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", controller.handle_start))
    application.add_handler(CommandHandler("help", controller.handle_help))
    application.add_handler(CommandHandler("status", controller.handle_status_command))
    application.add_handler(CommandHandler("start_magnet", controller.handle_start_magnet))
    application.add_handler(CommandHandler("remove", controller.handle_remove))
    application.add_handler(CallbackQueryHandler(controller.handle_candidate_button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, controller.handle_text))
    controller.enable_background_tasks(application)
    application.post_init = _chain_lifecycle_callback(application.post_init, _set_bot_commands)
    return application


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.telemetry_level.upper(), logging.INFO))

    loader = ConfigLoader(args.config)
    try:
        config = loader.load()
    except ConfigError as exc:
        raise SystemExit(f"Config error: {exc}") from exc

    telegram_config = config.telegram
    token = args.token or (telegram_config.bot_token if telegram_config else None) or os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise SystemExit("Provide a Telegram token via --token, config.telegram.bot_token, or TELEGRAM_TOKEN env var.")

    chat_id = args.chat_id
    if chat_id is None and telegram_config and telegram_config.chat_id:
        chat_id = telegram_config.chat_id

    torznab_debug = args.torznab_debug or args.telemetry_level.upper() == "DEBUG"

    application = build_app(config, token, args.max_results, chat_id, torznab_debug)

    LOGGER.info("Starting Telegram bot in polling mode.")
    application.run_polling()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

"""
Telegram chat control for torrent_finder.

Usage
-----
python telegram_bot.py --token <bot-token> [--config config.json]

Flow
----
- User sends: ``search dune part two``.
- Bot replies with the top five ranked torrents (seeders/leechers shown) and remembers them.
- User answers with ``1`` (or any list number) to start the download via Transmission.
"""

import argparse
import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from torrent_finder.config import AppConfig, ConfigLoader, ConfigError
from torrent_finder.finder import TorrentFinder
from torrent_finder.transmission import TransmissionController
from torrent_finder.torznab import TorznabClient
from torrent_finder.models import Candidate


LOGGER = logging.getLogger(__name__)


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
    return parser.parse_args()


@dataclass
class PendingSearch:
    query: str
    candidates: List[Candidate]


class TelegramTorrentController:
    """Bridges Telegram updates to TorrentFinder and Transmission."""

    def __init__(
        self,
        finder: TorrentFinder,
        transmission: TransmissionController,
        max_results: int,
        allowed_chat_id: Optional[int] = None,
    ):
        self._finder = finder
        self._transmission = transmission
        self._max_results = max(1, max_results)
        self._allowed_chat_id = allowed_chat_id
        self._pending: Dict[int, PendingSearch] = {}

    async def handle_start(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        await self._reply(update, "Send `search <title>` to see the top torrents, then respond with the number to download.", markdown=True)

    async def handle_help(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        await self._reply(
            update,
            "Commands:\n"
            "- `search <title>`: look up torrents and see the top matches.\n"
            "- `<number>`: pick one of the previously listed torrents to start the download.\n"
            "- `/help`: show this message again.",
            markdown=True,
        )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return

        chat_id = update.effective_chat.id if update.effective_chat else None
        text = update.message.text.strip()
        if not chat_id:
            LOGGER.debug("Skipping message without chat.")
            return

        if not self._is_authorized(update):
            return

        if text.lower().startswith("search "):
            query = text[7:].strip()
            if not query:
                await self._reply(update, "Give me something to search for, e.g. `search dune`.", markdown=True)
                return
            await self._perform_search(update, query)
        elif text.isdigit():
            await self._handle_selection(update, chat_id, int(text))
        else:
            await self._reply(update, "Say `search <title>` to look for something, or send a number to pick from the last list.")

    async def _perform_search(self, update: Update, query: str) -> None:
        await self._reply(update, f"Searching for “{query}”…")
        loop = asyncio.get_running_loop()
        try:
            candidates = await loop.run_in_executor(None, self._finder.find_candidates, query, False)
        except Exception as exc:  # pragma: no cover - defensive, Finder already logs
            LOGGER.exception("Torznab search failed")
            await self._reply(update, f"Search failed: {exc}")
            return

        ranked = sorted(candidates, key=lambda c: c.rank_tuple(), reverse=True)[: self._max_results]
        if not ranked:
            await self._reply(update, "Nothing found. Try a broader query or verify your Jackett config.")
            return

        chat_id = update.effective_chat.id if update.effective_chat else 0
        self._pending[chat_id] = PendingSearch(query=query, candidates=ranked)

        lines = [f"Top {len(ranked)} results for *{query}*:"]
        for idx, candidate in enumerate(ranked, start=1):
            title = candidate.title or "(untitled)"
            seeders = candidate.seeders if candidate.seeders is not None else "?"
            leechers = candidate.leechers if candidate.leechers is not None else "?"
            lines.append(f"{idx}. {title} — seeders: {seeders} | leechers: {leechers}")
        lines.append("Reply with the number to send it to Transmission.")
        await self._reply(update, "\n".join(lines), markdown=True)

    async def _handle_selection(self, update: Update, chat_id: int, selection: int) -> None:
        pending = self._pending.get(chat_id)
        if not pending:
            await self._reply(update, "No active search. Use `search <title>` first.", markdown=True)
            return

        if selection < 1 or selection > len(pending.candidates):
            await self._reply(update, f"Choose between 1 and {len(pending.candidates)}.")
            return

        candidate = pending.candidates[selection - 1]
        await self._reply(update, f"Sending *{candidate.title or '(untitled)'}* to Transmission…", markdown=True)

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._enqueue_download, candidate)
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Failed to queue torrent")
            await self._reply(update, f"Transmission said nope: {exc}")
            return

        await self._reply(update, "Done. Want something else?")

    def _enqueue_download(self, candidate: Candidate) -> None:
        self._transmission.ensure_available()
        self._transmission.add(candidate.magnet, start_override=None)

    @staticmethod
    async def _reply(update: Update, text: str, markdown: bool = False) -> None:
        if not update.message:
            return
        parse_mode = "Markdown" if markdown else None
        await update.message.reply_text(text, parse_mode=parse_mode)

    def _is_authorized(self, update: Update) -> bool:
        if not self._allowed_chat_id:
            return True
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id != self._allowed_chat_id:
            LOGGER.warning("Ignoring message from unauthorized chat %s", chat_id)
            return False
        return True


def build_app(config: AppConfig, token: str, max_results: int, chat_id: Optional[int]) -> Application:
    torznab = TorznabClient(config.torznab)
    finder = TorrentFinder(torznab)
    transmission = TransmissionController(config.transmission)
    controller = TelegramTorrentController(finder, transmission, max_results=max_results, allowed_chat_id=chat_id)

    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", controller.handle_start))
    application.add_handler(CommandHandler("help", controller.handle_help))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, controller.handle_text))
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

    application = build_app(config, token, args.max_results, chat_id)

    LOGGER.info("Starting Telegram bot in polling mode.")
    application.run_polling()


if __name__ == "__main__":
    main()

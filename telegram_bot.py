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
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from torrent_finder.categories import describe_preset, extract_preset_from_query
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
    parser.add_argument(
        "--torznab-debug",
        action="store_true",
        help="Emit verbose Torznab logs (implied when --telemetry-level DEBUG).",
    )
    return parser.parse_args()


@dataclass
class PendingSearch:
    query: str
    candidates: List[Candidate]


@dataclass
class TrackedDownload:
    tracking_id: str
    chat_id: int
    title: str
    magnet: str


class TelegramTorrentController:
    """Bridges Telegram updates to TorrentFinder and Transmission."""

    _SELECTION_PREFIX = "pick:"
    _STATUS_CALLBACK = "status"

    def __init__(
        self,
        finder: TorrentFinder,
        transmission: TransmissionController,
        max_results: int,
        allowed_chat_id: Optional[int] = None,
            torznab_debug: bool = False,
    ):
        self._finder = finder
        self._transmission = transmission
        self._max_results = max(1, max_results)
        self._allowed_chat_id = allowed_chat_id
        self._torznab_debug = torznab_debug
        self._pending: Dict[int, PendingSearch] = {}
        self._tracked_downloads: Dict[str, TrackedDownload] = {}
        self._tracking_lock = asyncio.Lock()

    async def handle_start(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        await self._reply(
            update,
            "Send `search <title>` to see the top torrents, tap *Status* to inspect downloads, then press a number or button to start the transfer.",
            markdown=True,
            reply_markup=self._build_shortcuts_keyboard(),
        )

    async def handle_help(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        await self._send_help(update)

    async def handle_status_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        await self._send_status(update)

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
        elif text.lower() == "status":
            await self._send_status(update)
        elif text.lower() == "help":
            await self._send_help(update)
        elif text.isdigit():
            await self._handle_selection(update, chat_id, int(text))
        else:
            await self._reply(
                update,
                "Say `search <title>` to look for something, `status` to inspect active torrents, or send a number to pick from the last list.",
            )

    async def handle_candidate_button(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.data:
            return

        data = query.data
        await query.answer()

        if not self._is_authorized(update):
            return

        if data == self._STATUS_CALLBACK:
            await self._send_status(update)
            return

        if not data.startswith(self._SELECTION_PREFIX):
            LOGGER.debug("Ignoring unknown callback payload: %s", data)
            return

        try:
            selection = int(data[len(self._SELECTION_PREFIX) :])
        except ValueError:
            LOGGER.warning("Bad selection index from Telegram callback: %s", data)
            return

        message = query.message
        chat_id = message.chat_id if message else (update.effective_chat.id if update.effective_chat else None)
        if not chat_id:
            LOGGER.debug("Callback without chat ID.")
            return

        if message:
            try:
                await message.edit_reply_markup(reply_markup=None)
            except Exception:  # pragma: no cover - best effort cleanup
                LOGGER.debug("Could not clear inline keyboard for message %s", message.message_id)

        await self._handle_selection(update, chat_id, selection)

    async def _perform_search(self, update: Update, query: str) -> None:
        categories, trimmed_query, preset_slug = extract_preset_from_query(query)
        if not trimmed_query:
            await self._reply(update, "Give me something to search for after the category keyword.", markdown=False)
            return

        await self._reply(update, self._format_search_prompt(trimmed_query, preset_slug))
        loop = asyncio.get_running_loop()
        try:
            candidates = await loop.run_in_executor(
                None,
                self._finder.find_candidates,
                trimmed_query,
                categories,
                self._torznab_debug,
            )
        except Exception as exc:  # pragma: no cover - defensive, Finder already logs
            LOGGER.exception("Torznab search failed")
            await self._reply(update, f"Search failed: {exc}")
            return

        ranked = sorted(candidates, key=lambda c: c.rank_tuple(), reverse=True)[: self._max_results]
        if not ranked:
            await self._reply(update, "Nothing found. Try a broader query or verify your Jackett config.")
            return

        chat_id = update.effective_chat.id if update.effective_chat else 0
        self._pending[chat_id] = PendingSearch(query=trimmed_query, candidates=ranked)

        filter_suffix = ""
        if preset_slug and preset_slug != "all":
            filter_suffix = f" ({describe_preset(preset_slug)})"

        lines = [f"Top {len(ranked)} results for *{trimmed_query}*{filter_suffix}:"]
        for idx, candidate in enumerate(ranked, start=1):
            title = candidate.title or "(untitled)"
            seeders = candidate.seeders if candidate.seeders is not None else "?"
            leechers = candidate.leechers if candidate.leechers is not None else "?"
            lines.append(f"{idx}. {title} — seeders: {seeders} | leechers: {leechers}")
        lines.append("Reply with the number to send it to Transmission.")
        await self._reply(
            update,
            "\n".join(lines),
            markdown=True,
            reply_markup=self._build_results_keyboard(len(ranked)),
        )

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

        await self._remember_download(chat_id, candidate)
        await self._reply(update, "Done. Want something else?")

    def _enqueue_download(self, candidate: Candidate) -> None:
        self._transmission.ensure_available()
        self._transmission.add(candidate.magnet, start_override=None)

    async def _remember_download(self, chat_id: int, candidate: Candidate) -> None:
        tracking_id = uuid.uuid4().hex
        tracked = TrackedDownload(
            tracking_id=tracking_id,
            chat_id=chat_id,
            title=candidate.title or "(untitled)",
            magnet=candidate.magnet,
        )
        async with self._tracking_lock:
            self._tracked_downloads[tracking_id] = tracked

    async def _send_status(self, update: Update) -> None:
        await self._reply(update, "Checking Transmission…")
        loop = asyncio.get_running_loop()
        try:
            statuses = await loop.run_in_executor(None, self._transmission.list_torrents, True)
        except SystemExit as exc:  # pragma: no cover - defensive
            LOGGER.warning("Transmission status check aborted: %s", exc)
            await self._reply(update, f"Status check failed: {exc}")
            return
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("Failed to inspect Transmission")
            await self._reply(update, f"Status check failed: {exc}")
            return

        if not statuses:
            await self._reply(update, "No active torrents in Transmission.")
            return

        lines = ["Active torrents:"]
        for status in statuses:
            eta = status.eta or "unknown"
            lines.append(f"- {status.name} — {status.percent_done:.1f}% ({status.status}, ETA: {eta})")
        await self._reply(update, "\n".join(lines))

    async def _poll_downloads(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with self._tracking_lock:
            tracked_items = list(self._tracked_downloads.items())

        if not tracked_items:
            return

        loop = asyncio.get_running_loop()
        try:
            statuses = await loop.run_in_executor(None, self._transmission.list_torrents, False)
        except SystemExit as exc:  # pragma: no cover - defensive
            LOGGER.warning("Transmission status poll aborted: %s", exc)
            return
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Transmission status poll failed: %s", exc)
            return

        completed: List[Tuple[str, TrackedDownload]] = []
        for tracking_id, tracked in tracked_items:
            status = self._match_status(statuses, tracked)
            if status and status.is_complete:
                completed.append((tracking_id, tracked))
                text = f"✅ Torrent ready: {status.name}"
                await context.bot.send_message(chat_id=tracked.chat_id, text=text)

        if not completed:
            return

        async with self._tracking_lock:
            for tracking_id, _ in completed:
                self._tracked_downloads.pop(tracking_id, None)

    @staticmethod
    def _match_status(
        statuses: List[TransmissionController.TorrentStatus],
        tracked: TrackedDownload,
    ) -> Optional[TransmissionController.TorrentStatus]:
        title = tracked.title.lower() if tracked.title else None
        for status in statuses:
            if status.magnet and tracked.magnet and status.magnet == tracked.magnet:
                return status
            if title and status.name and status.name.lower() == title:
                return status
        return None

    def enable_background_tasks(self, application: Application, interval_seconds: int = 30) -> None:
        job_queue = getattr(application, "_job_queue", None)
        if not job_queue:
            return
        job_queue.run_repeating(
            self._poll_downloads,
            interval=interval_seconds,
            first=interval_seconds,
            name="torrent-download-monitor",
        )

    async def _send_help(self, update: Update) -> None:
        await self._reply(
            update,
            "Commands:\n"
            "- `search <title>`: look up torrents and see the top matches.\n"
            "- Prefix with `search movies ...`, `search tv ...`, or `search software ...` for category presets.\n"
            "- `<number>` or button tap: pick one of the previously listed torrents to start the download.\n"
            "- `status`: show Transmission's active downloads (inline button available).\n"
            "- `/help`: show this message again.",
            markdown=True,
        )

    async def _reply(self, update: Update, text: str, markdown: bool = False, reply_markup=None) -> None:
        message = update.message
        if not message and update.callback_query:
            message = update.callback_query.message
        if not message:
            return
        parse_mode = "Markdown" if markdown else None
        await message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)

    @staticmethod
    def _format_search_prompt(query: str, preset_slug: Optional[str]) -> str:
        if preset_slug == "all":
            return f"Searching all categories for “{query}”…"
        if preset_slug:
            return f"Searching {describe_preset(preset_slug)} for “{query}”…"
        return f"Searching for “{query}”…"

    @classmethod
    def _build_results_keyboard(cls, count: int) -> InlineKeyboardMarkup:
        buttons: List[List[InlineKeyboardButton]] = []
        row: List[InlineKeyboardButton] = []
        for idx in range(1, count + 1):
            row.append(InlineKeyboardButton(str(idx), callback_data=f"{cls._SELECTION_PREFIX}{idx}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("📡 Status", callback_data=cls._STATUS_CALLBACK)])
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def _build_shortcuts_keyboard() -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            [[KeyboardButton("status"), KeyboardButton("help")]],
            resize_keyboard=True,
        )

    def _is_authorized(self, update: Update) -> bool:
        if not self._allowed_chat_id:
            return True
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id != self._allowed_chat_id:
            LOGGER.warning("Ignoring message from unauthorized chat %s", chat_id)
            return False
        return True


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
    controller = TelegramTorrentController(
        finder,
        transmission,
        max_results=max_results,
        allowed_chat_id=chat_id,
        torznab_debug=torznab_debug,
    )

    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", controller.handle_start))
    application.add_handler(CommandHandler("help", controller.handle_help))
    application.add_handler(CommandHandler("status", controller.handle_status_command))
    application.add_handler(CallbackQueryHandler(controller.handle_candidate_button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, controller.handle_text))
    controller.enable_background_tasks(application)
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

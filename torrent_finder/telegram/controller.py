import asyncio
import logging
from typing import Optional

from telegram import ForceReply, Update
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from telegram.ext import ContextTypes

from torrent_finder.categories import describe_preset, extract_preset_from_query
from torrent_finder.finder import TorrentFinder
from torrent_finder.models import Candidate
from torrent_finder.transmission import TransmissionController

from .keyboards import KeyboardBuilder
from .messages import MessageFactory
from .monitor import DownloadMonitor
from .sessions import UserSessions

LOGGER = logging.getLogger(__name__)


class TelegramTorrentController:
    """Bridges Telegram updates to TorrentFinder and Transmission."""

    SELECTION_PREFIX = "pick:"
    DIR_SELECTION_PREFIX = "dir:"
    STATUS_CALLBACK = "status"
    SEARCH_TV_CALLBACK = "search-tv"
    SEARCH_MOVIE_CALLBACK = "search-movie"
    HELP_KEYBOARD_CALLBACK = "help-keyboard"
    _TV_SEARCH_PROMPT = "Send the TV show name to search:"
    _MOVIE_SEARCH_PROMPT = "Send the movie name to search:"
    def __init__(
        self,
        finder: TorrentFinder,
        transmission: TransmissionController,
        sessions: UserSessions,
        keyboards: KeyboardBuilder,
        messages: MessageFactory,
        download_monitor: DownloadMonitor,
        max_results: int,
        allowed_chat_id: Optional[int] = None,
        torznab_debug: bool = False,
    ) -> None:
        self._finder = finder
        self._transmission = transmission
        self._sessions = sessions
        self._keyboards = keyboards
        self._messages = messages
        self._download_monitor = download_monitor
        self._max_results = max(1, max_results)
        self._allowed_chat_id = allowed_chat_id
        self._torznab_debug = torznab_debug

    async def handle_start(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        await self._reply(
            update,
            "Send `search <title>` to see the top torrents, tap *Status* to inspect downloads, then press a number or button to start the transfer.",
            markdown=True,
            reply_markup=self._keyboards.shortcuts_keyboard(),
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

        if self._is_tv_search_reply(update.message):
            tv_query = text
            if not tv_query:
                await self._reply(update, "Send a TV show name to search.")
                return
            await self._perform_search(update, f"tv {tv_query}")
            return
        if self._is_movie_search_reply(update.message):
            movie_query = text
            if not movie_query:
                await self._reply(update, "Send a movie name to search.")
                return
            await self._perform_search(update, f"movies {movie_query}")
            return

        if text.lower().startswith("search "):
            query = text[7:].strip()
            if not query:
                await self._reply(update, "Give me something to search for, e.g. `search the big lebowski`.", markdown=True)
                return
            await self._perform_search(update, query)
        elif text.lower().startswith("status"):
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

        if data == self.STATUS_CALLBACK:
            await self._send_status(update)
            return
        if data == self.HELP_KEYBOARD_CALLBACK:
            await self._reply(
                update,
                "Shortcut keyboard restored.",
                reply_markup=self._keyboards.shortcuts_keyboard(),
            )
            return
        if data == self.SEARCH_TV_CALLBACK:
            await self._reply(
                update,
                self._TV_SEARCH_PROMPT,
                reply_markup=ForceReply(selective=True, input_field_placeholder="e.g., The Expanse"),
            )
            return
        if data == self.SEARCH_MOVIE_CALLBACK:
            await self._reply(
                update,
                self._MOVIE_SEARCH_PROMPT,
                reply_markup=ForceReply(selective=True, input_field_placeholder="e.g., Dune Part Two"),
            )
            return
        if data.startswith(self.DIR_SELECTION_PREFIX):
            await self._handle_directory_choice(update, data)
            return

        if not data.startswith(self.SELECTION_PREFIX):
            LOGGER.debug("Ignoring unknown callback payload: %s", data)
            return

        try:
            selection = int(data[len(self.SELECTION_PREFIX) :])
        except ValueError:
            LOGGER.warning("Bad selection index from Telegram callback: %s", data)
            return

        chat_id = update.effective_chat.id if update.effective_chat else None
        if not chat_id:
            LOGGER.debug("Callback without chat ID.")
            return

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:  # best effort cleanup
            message_id = query.message.message_id if query.message else "inline"
            LOGGER.debug("Could not clear inline keyboard for message %s", message_id)

        await self._handle_selection(update, chat_id, selection)

    async def _perform_search(self, update: Update, query: str) -> None:
        categories, trimmed_query, preset_slug = extract_preset_from_query(query)
        if not trimmed_query:
            await self._reply(update, "Give me something to search for after the category keyword.", markdown=False)
            return

        await self._reply(update, self._messages.search_prompt(trimmed_query, preset_slug))
        loop = asyncio.get_running_loop()
        try:
            candidates = await loop.run_in_executor(
                None,
                self._finder.find_candidates,
                trimmed_query,
                categories,
                self._torznab_debug,
            )
        except Exception as exc:  # Finder already logs
            LOGGER.exception("Torznab search failed")
            await self._reply(update, f"Search failed: {exc}")
            return

        ranked = sorted(candidates, key=lambda c: c.rank_tuple(), reverse=True)[: self._max_results]
        if not ranked:
            await self._reply(update, "Nothing found. Try a broader query or verify your Jackett config.")
            return

        chat_id = update.effective_chat.id if update.effective_chat else 0
        self._sessions.save_search(chat_id, trimmed_query, ranked)

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
            reply_markup=self._keyboards.results_keyboard(len(ranked)),
        )

    async def _handle_selection(self, update: Update, chat_id: int, selection: int) -> None:
        pending = self._sessions.get_search(chat_id)
        if not pending:
            await self._reply(update, "No active search. Use `search <title>` first.", markdown=True)
            return

        if selection < 1 or selection > len(pending.candidates):
            await self._reply(update, f"Choose between 1 and {len(pending.candidates)}.")
            return

        candidate = pending.candidates[selection - 1]
        self._sessions.remember_download_choice(chat_id, candidate)
        await self._reply(
            update,
            f"Where should I save *{candidate.title or '(untitled)'}*?",
            markdown=True,
            reply_markup=self._keyboards.download_dir_keyboard(),
        )

    def _enqueue_download(self, candidate: Candidate, download_dir: Optional[str]) -> None:
        self._transmission.ensure_available()
        self._transmission.add(candidate.magnet, start_override=None, download_dir=download_dir)

    async def _handle_directory_choice(self, update: Update, data: str) -> None:
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is None:
            return

        candidate = self._sessions.pop_download_choice(chat_id)
        if not candidate:
            await self._reply(update, "No torrent is waiting for a download location. Start with `search ...`.", markdown=True)
            return

        download_dir = data[len(self.DIR_SELECTION_PREFIX) :]
        await self._reply(update, f"Sending *{candidate.title or '(untitled)'}* to Transmission…", markdown=True)

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._enqueue_download, candidate, download_dir)
        except Exception as exc:
            LOGGER.exception("Failed to queue torrent")
            await self._reply(update, f"Transmission said nope: {exc}")
            return

        await self._download_monitor.track_download(chat_id, candidate)
        await self._reply(update, "Done. Want something else?")

    async def _send_status(self, update: Update) -> None:
        await self._reply(update, "Checking Transmission…")
        loop = asyncio.get_running_loop()
        try:
            statuses = await loop.run_in_executor(None, self._transmission.list_torrents, False)
        except SystemExit as exc:  # defensive
            LOGGER.warning("Transmission status check aborted: %s", exc)
            await self._reply(update, f"Status check failed: {exc}")
            return
        except Exception as exc:  # defensive
            LOGGER.exception("Failed to inspect Transmission")
            await self._reply(update, f"Status check failed: {exc}")
            return

        if not statuses:
            await self._reply(update, "Transmission has no torrents yet.")
            return

        heading = f"*{escape_markdown('All torrents', version=2)}*"
        table = self._messages.format_status_table(statuses)
        table_message = f"{heading}\n```\n{table}\n```"
        await self._reply(
            update,
            table_message,
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    def enable_background_tasks(self, application) -> None:
        self._download_monitor.enable_background_tasks(application)

    async def _send_help(self, update: Update) -> None:
        await self._reply(
            update,
            "Commands:\n"
            "- `search <title>`: look up torrents and see the top matches.\n"
            "- Prefix with `search movies ...`, `search tv ...`, or `search software ...` for category presets.\n"
            "- `<number>` or button tap: pick one of the previously listed torrents to start the download.\n"
            "- `status`: list every torrent with a short explanation of its state.\n"
            "- `help`: show this message again.",
            markdown=True,
            reply_markup=self._keyboards.help_keyboard(),
        )

    async def _reply(
        self,
        update: Update,
        text: str,
        markdown: bool = False,
        reply_markup=None,
        parse_mode: Optional[str] = None,
    ) -> None:
        message = update.message
        if not message and update.callback_query:
            message = update.callback_query.message
        if not message:
            return
        resolved_parse_mode = parse_mode
        if not resolved_parse_mode and markdown:
            resolved_parse_mode = ParseMode.MARKDOWN
        await message.reply_text(text, parse_mode=resolved_parse_mode, reply_markup=reply_markup)

    def _is_tv_search_reply(self, message) -> bool:
        reply = getattr(message, "reply_to_message", None)
        if not reply or not getattr(reply, "text", None):
            return False
        return reply.text.strip() == self._TV_SEARCH_PROMPT

    def _is_movie_search_reply(self, message) -> bool:
        reply = getattr(message, "reply_to_message", None)
        if not reply or not getattr(reply, "text", None):
            return False
        return reply.text.strip() == self._MOVIE_SEARCH_PROMPT

    def _is_authorized(self, update: Update) -> bool:
        if not self._allowed_chat_id:
            return True
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id != self._allowed_chat_id:
            LOGGER.warning("Ignoring message from unauthorized chat %s", chat_id)
            return False
        return True

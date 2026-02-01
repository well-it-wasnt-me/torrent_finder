import asyncio
import logging
import math
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

from telegram import Update
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
    MENU_CALLBACK = "menu"
    SEARCH_CALLBACK = "search"
    HELP_CALLBACK = "help"
    STATUS_ALL_CALLBACK = "status:all"
    STATUS_ACTIVE_CALLBACK = "status:active"
    STATUS_REFRESH_PREFIX = "status:refresh:"
    CATEGORY_PREFIX = "cat:"
    PAGE_PREFIX = "page:"
    MORE_LIKE_PREFIX = "more:"
    CANCEL_CALLBACK = "cancel"
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
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is not None:
            self._sessions.clear_pending_prompt(chat_id)
        await self._send_menu(update)

    async def handle_help(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is not None:
            self._sessions.clear_pending_prompt(chat_id)
        await self._send_help(update)

    async def handle_status_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is not None:
            self._sessions.clear_pending_prompt(chat_id)
        await self._send_status(update, active_only=False, edit=False)

    async def handle_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        if not update.message:
            return
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is not None:
            self._sessions.clear_pending_prompt(chat_id)

        raw_target = ""
        if context and context.args:
            raw_target = " ".join(context.args).strip()
        if not raw_target and update.message.text:
            raw_text = update.message.text.strip()
            if " " in raw_text:
                raw_target = raw_text.split(" ", 1)[1].strip()

        if not raw_target:
            await self._reply(update, "Usage: /remove <id or name>. Tip: run `status` to see IDs.", markdown=True)
            return

        await self._reply(update, "Checking Transmission…")
        loop = asyncio.get_running_loop()
        try:
            statuses = await loop.run_in_executor(None, self._transmission.list_torrents, False)
        except SystemExit as exc:  # defensive
            LOGGER.warning("Transmission remove lookup aborted: %s", exc)
            await self._reply(update, f"Remove failed: {exc}")
            return
        except Exception as exc:  # defensive
            LOGGER.exception("Failed to inspect Transmission for removal")
            await self._reply(update, f"Remove failed: {exc}")
            return

        if not statuses:
            await self._reply(update, "Transmission has no torrents to remove.")
            return

        match, error = self._match_removal_target(statuses, raw_target)
        if error:
            await self._reply(update, error)
            return
        if not match or match.torrent_id is None:
            await self._reply(update, "Couldn't resolve that torrent. Try using the numeric ID from `status`.")
            return

        try:
            await loop.run_in_executor(None, self._transmission.stop_and_remove, match.torrent_id, False)
        except SystemExit as exc:
            LOGGER.warning("Transmission removal aborted: %s", exc)
            await self._reply(update, f"Remove failed: {exc}")
            return
        except Exception as exc:
            LOGGER.exception("Failed to remove torrent")
            await self._reply(update, f"Remove failed: {exc}")
            return

        await self._reply(update, f"Removed *{match.name}* (id {match.torrent_id}).", markdown=True)

    async def handle_start_magnet(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        if not update.message:
            return
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is not None:
            self._sessions.clear_pending_prompt(chat_id)

        magnet = ""
        if context and context.args:
            magnet = " ".join(context.args).strip()
        if not magnet and update.message.text:
            raw_text = update.message.text.strip()
            if " " in raw_text:
                magnet = raw_text.split(" ", 1)[1].strip()

        if not magnet:
            await self._reply(update, "Usage: /start_magnet <magnet_url>")
            return
        if not magnet.lower().startswith("magnet:?"):
            await self._reply(
                update,
                "That does not look like a magnet URL. Example: /start_magnet magnet:?xt=urn:btih:<hash>",
            )
            return

        title = self._extract_magnet_name(magnet)
        label = f"*{title}*" if title else "that magnet"
        await self._reply(update, f"Sending {label} to Transmission…", markdown=bool(title))

        loop = asyncio.get_running_loop()
        candidate = Candidate(magnet=magnet, title=title)
        try:
            await loop.run_in_executor(None, self._enqueue_download, candidate, None)
        except Exception as exc:
            LOGGER.exception("Failed to queue magnet")
            await self._reply(update, f"Transmission said nope: {exc}")
            return

        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is not None:
            await self._download_monitor.track_download(chat_id, candidate)
        await self._reply(update, "Queued. I'll ping you when it's ready.")

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

        pending_prompt = self._sessions.get_pending_prompt(chat_id)
        lowered = text.lower()

        if lowered.startswith("search "):
            self._sessions.clear_pending_prompt(chat_id)
            query = text[7:].strip()
            if not query:
                await self._reply(update, "Give me something to search for, e.g. `search the big lebowski`.", markdown=True)
                return
            await self._perform_search(update, query)
            return

        if lowered.startswith("status"):
            self._sessions.clear_pending_prompt(chat_id)
            await self._send_status(update, active_only=False, edit=False)
            return

        if lowered == "help":
            self._sessions.clear_pending_prompt(chat_id)
            await self._send_help(update)
            return

        if lowered in {"menu", "start"}:
            self._sessions.clear_pending_prompt(chat_id)
            await self._send_menu(update)
            return

        if lowered == "cancel" and pending_prompt:
            self._sessions.clear_pending_prompt(chat_id)
            await self._send_menu(update, text="Search cancelled. Choose your next move.")
            return

        if text.isdigit():
            self._sessions.clear_pending_prompt(chat_id)
            await self._handle_selection(update, chat_id, int(text))
            return

        if pending_prompt:
            query = text.strip()
            if pending_prompt.preset_slug:
                prefix = pending_prompt.preset_slug
                if prefix == "all":
                    query = f"all {query}"
                else:
                    query = f"{prefix} {query}"
            self._sessions.clear_pending_prompt(chat_id)
            await self._perform_search(update, query)
            return

        await self._reply(
            update,
            "Tap Search or a category button to get started, or type `search <title>`.",
            reply_markup=self._keyboards.main_menu_keyboard(),
        )

    async def handle_candidate_button(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.data:
            return

        data = query.data
        await query.answer()

        if not self._is_authorized(update):
            return

        chat_id = update.effective_chat.id if update.effective_chat else None

        if data == self.MENU_CALLBACK:
            if chat_id is not None:
                self._sessions.clear_pending_prompt(chat_id)
            await self._send_menu(update, edit=True)
            return

        if data == self.HELP_CALLBACK:
            if chat_id is not None:
                self._sessions.clear_pending_prompt(chat_id)
            await self._send_help(update, edit=True)
            return

        if data == self.SEARCH_CALLBACK:
            if chat_id is None:
                return
            self._sessions.set_pending_prompt(chat_id, None)
            await self._send_search_prompt(update, None, edit=True)
            return

        if data == self.CANCEL_CALLBACK:
            if chat_id is not None:
                self._sessions.clear_pending_prompt(chat_id)
            await self._send_menu(update, edit=True, text="Search cancelled. Choose your next move.")
            return

        if data.startswith(self.CATEGORY_PREFIX):
            if chat_id is None:
                return
            slug = data[len(self.CATEGORY_PREFIX) :]
            self._sessions.set_pending_prompt(chat_id, slug)
            await self._send_search_prompt(update, slug, edit=True)
            return

        if data == self.STATUS_ALL_CALLBACK:
            await self._send_status(update, active_only=False, edit=True)
            return

        if data == self.STATUS_ACTIVE_CALLBACK:
            await self._send_status(update, active_only=True, edit=True)
            return

        if data.startswith(self.STATUS_REFRESH_PREFIX):
            target = data[len(self.STATUS_REFRESH_PREFIX) :]
            await self._send_status(update, active_only=(target == "active"), edit=True)
            return

        if data.startswith(self.PAGE_PREFIX):
            await self._handle_page(update, data)
            return

        if data.startswith(self.MORE_LIKE_PREFIX):
            await self._handle_more_like(update, data)
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

    async def _perform_search(self, update: Update, query: str, edit: bool = False) -> None:
        categories, trimmed_query, preset_slug = extract_preset_from_query(query)
        if not trimmed_query:
            await self._reply(update, "Give me something to search for after the category keyword.", markdown=False)
            return

        if not edit:
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

        ranked = sorted(candidates, key=lambda c: c.rank_tuple(), reverse=True)
        max_keep = max(self._max_results * 5, self._max_results)
        ranked = ranked[:max_keep]
        if not ranked:
            await self._reply(update, "Nothing found. Try a broader query or verify your Jackett config.")
            return

        chat_id = update.effective_chat.id if update.effective_chat else 0
        self._sessions.save_search(chat_id, trimmed_query, ranked, self._max_results, preset_slug, categories)
        await self._send_search_results(update, edit=edit)

    async def _send_menu(self, update: Update, edit: bool = False, text: Optional[str] = None) -> None:
        message = text or "Choose an action or category:"
        await self._edit_or_reply(update, message, reply_markup=self._keyboards.main_menu_keyboard(), edit=edit)

    async def _send_search_prompt(self, update: Update, preset_slug: Optional[str], edit: bool = False) -> None:
        if preset_slug:
            label = describe_preset(preset_slug)
            prompt = f"Send the title to search ({label})."
        else:
            prompt = "Send the title to search."
        await self._edit_or_reply(update, prompt, reply_markup=self._keyboards.search_prompt_keyboard(), edit=edit)

    async def _send_search_results(self, update: Update, edit: bool = False) -> None:
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is None:
            return

        pending = self._sessions.get_search(chat_id)
        if not pending:
            await self._reply(update, "No active search. Tap Search or type `search <title>`.")
            return

        total_pages = max(1, math.ceil(len(pending.candidates) / pending.page_size))
        pending.page = max(0, min(pending.page, total_pages - 1))
        start = pending.page * pending.page_size
        page_candidates = pending.candidates[start : start + pending.page_size]
        indices = list(range(start + 1, start + 1 + len(page_candidates)))

        filter_suffix = f" ({describe_preset(pending.preset_slug)})" if pending.preset_slug else ""
        header = f"Results for {pending.query}{filter_suffix} - page {pending.page + 1}/{total_pages}"
        lines = [header, ""]
        for idx, candidate in enumerate(page_candidates, start=start + 1):
            lines.extend(self._messages.format_candidate_card(idx, candidate))
            lines.append("")
        if lines and lines[-1] == "":
            lines.pop()
        lines.append("Tap a button to download or explore similar results.")

        keyboard = self._keyboards.results_keyboard(indices, pending.page, total_pages)
        await self._edit_or_reply(update, "\n".join(lines), reply_markup=keyboard, edit=edit)

    async def _handle_page(self, update: Update, data: str) -> None:
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is None:
            return

        pending = self._sessions.get_search(chat_id)
        if not pending:
            await self._reply(update, "No active search to page through.")
            return

        try:
            page = int(data[len(self.PAGE_PREFIX) :])
        except ValueError:
            LOGGER.warning("Bad page index from Telegram callback: %s", data)
            return

        total_pages = max(1, math.ceil(len(pending.candidates) / pending.page_size))
        pending.page = max(0, min(page, total_pages - 1))
        await self._send_search_results(update, edit=True)

    async def _handle_more_like(self, update: Update, data: str) -> None:
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is None:
            return

        pending = self._sessions.get_search(chat_id)
        if not pending:
            await self._reply(update, "No active search to expand.")
            return

        try:
            selection = int(data[len(self.MORE_LIKE_PREFIX) :])
        except ValueError:
            LOGGER.warning("Bad more-like index from Telegram callback: %s", data)
            return

        if selection < 1 or selection > len(pending.candidates):
            await self._reply(update, "That result is no longer available. Try another.")
            return

        candidate = pending.candidates[selection - 1]
        query = candidate.title or pending.query
        if not query:
            await self._reply(update, "Couldn't build a related search from that result.")
            return

        if pending.preset_slug:
            prefix = pending.preset_slug
            if prefix == "all":
                query = f"all {query}"
            else:
                query = f"{prefix} {query}"

        await self._perform_search(update, query, edit=True)

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
        await self._reply(update, "Done. Want something else?", reply_markup=self._keyboards.main_menu_keyboard())

    async def _send_status(self, update: Update, active_only: bool, edit: bool) -> None:
        loop = asyncio.get_running_loop()
        try:
            statuses = await loop.run_in_executor(None, self._transmission.list_torrents, active_only)
        except SystemExit as exc:  # defensive
            LOGGER.warning("Transmission status check aborted: %s", exc)
            await self._reply(update, f"Status check failed: {exc}")
            return
        except Exception as exc:  # defensive
            LOGGER.exception("Failed to inspect Transmission")
            await self._reply(update, f"Status check failed: {exc}")
            return

        if not statuses:
            empty_message = "Transmission has no active torrents." if active_only else "Transmission has no torrents."
            await self._edit_or_reply(
                update,
                empty_message,
                reply_markup=self._keyboards.status_keyboard(active_only),
                edit=edit,
            )
            return

        heading = "📥 Active downloads" if active_only else "📥 Download status"
        heading_line = f"{escape_markdown(heading, version=2)}"
        report = self._messages.format_status_report(statuses)
        table_message = f"{heading_line}\n```text\n{report}\n```"
        await self._edit_or_reply(
            update,
            table_message,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=self._keyboards.status_keyboard(active_only),
            edit=edit,
        )

    def enable_background_tasks(self, application) -> None:
        self._download_monitor.enable_background_tasks(application)

    async def _send_help(self, update: Update, edit: bool = False) -> None:
        await self._edit_or_reply(
            update,
            "Quick help:\n"
            "- Use the buttons to search by category, check status, or open this help.\n"
            "- `search <title>` also works if you prefer typing.\n"
            "- Presets: `search movies ...`, `search tv ...`, `search comics ...`, `search software ...`, "
            "`search software mac ...`, `search software win ...`, `search zip ...`, or `search all ...`.\n"
            "- `<number>` or result button: pick a torrent from the last list.\n"
            "- `status`: list torrents with progress + IDs.\n"
            "- `/start_magnet <magnet_url>`: queue a magnet link directly.\n"
            "- `/remove <id or name>`: stop and remove a torrent.\n"
            "- `help`: show this message again.",
            markdown=True,
            reply_markup=self._keyboards.back_keyboard(),
            edit=edit,
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

    async def _edit_or_reply(
        self,
        update: Update,
        text: str,
        markdown: bool = False,
        reply_markup=None,
        parse_mode: Optional[str] = None,
        edit: bool = False,
    ) -> None:
        resolved_parse_mode = parse_mode
        if not resolved_parse_mode and markdown:
            resolved_parse_mode = ParseMode.MARKDOWN
        if edit and update.callback_query:
            try:
                await update.callback_query.edit_message_text(
                    text,
                    parse_mode=resolved_parse_mode,
                    reply_markup=reply_markup,
                )
            except Exception as exc:  # best effort for "message is not modified"
                LOGGER.debug("Failed to edit message: %s", exc)
            return
        await self._reply(update, text, markdown=markdown, reply_markup=reply_markup, parse_mode=resolved_parse_mode)

    def _is_authorized(self, update: Update) -> bool:
        if not self._allowed_chat_id:
            return True
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id != self._allowed_chat_id:
            LOGGER.warning("Ignoring message from unauthorized chat %s", chat_id)
            return False
        return True

    @classmethod
    def _match_removal_target(
        cls,
        statuses: list[TransmissionController.TorrentStatus],
        target: str,
    ) -> tuple[Optional[TransmissionController.TorrentStatus], Optional[str]]:
        cleaned = target.strip()
        id_match = re.fullmatch(r"#?(\d+)", cleaned)
        if id_match:
            torrent_id = int(id_match.group(1))
            for status in statuses:
                if status.torrent_id == torrent_id:
                    return status, None
            return None, f"No torrent with ID {torrent_id} found."

        normalized_target = cls._normalize_title(cleaned)
        if not normalized_target:
            return None, "Provide a torrent ID or name."

        exact_matches = [
            status for status in statuses if status.name and cls._normalize_title(status.name) == normalized_target
        ]
        if len(exact_matches) == 1:
            return exact_matches[0], None

        partial_matches = [
            status
            for status in statuses
            if status.name and normalized_target in cls._normalize_title(status.name)
        ]
        if len(partial_matches) == 1:
            return partial_matches[0], None

        matches = exact_matches or partial_matches
        if not matches:
            return None, "No torrent matched that name. Use `status` to grab the numeric ID."

        preview = ", ".join(
            f"{match.torrent_id}: {match.name}" for match in matches[:5] if match.torrent_id is not None
        )
        return None, f"Multiple matches found. Use `/remove <id>` and pick one of: {preview}"

    @staticmethod
    def _extract_magnet_name(magnet: str) -> Optional[str]:
        try:
            parsed = urlparse(magnet)
        except ValueError:
            return None
        if parsed.scheme and parsed.scheme != "magnet":
            return None
        params = parse_qs(parsed.query)
        names = params.get("dn", [])
        if not names:
            return None
        name = names[0].strip()
        return name or None

    @staticmethod
    def _normalize_title(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

import asyncio
import uuid
from dataclasses import dataclass
from functools import partial
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, Tuple, cast

from telegram.ext import Application

from torrent_finder.models import Candidate
from torrent_finder.transmission import TransmissionController

import logging

LOGGER = logging.getLogger(__name__)


class BotContext(Protocol):
    bot: Any


@dataclass
class TrackedDownload:
    tracking_id: str
    chat_id: int
    title: str
    magnet: str


class DownloadMonitor:
    """Polls Transmission for tracked downloads and notifies Telegram."""

    def __init__(self, transmission: TransmissionController) -> None:
        self._transmission = transmission
        self._tracking_lock = asyncio.Lock()
        self._tracked_downloads: Dict[str, TrackedDownload] = {}
        self._fallback_poll_task: Optional[asyncio.Task] = None
        self._stop_fallback_event: Optional[asyncio.Event] = None

    async def track_download(self, chat_id: int, candidate: Candidate) -> None:
        tracking_id = uuid.uuid4().hex
        tracked = TrackedDownload(
            tracking_id=tracking_id,
            chat_id=chat_id,
            title=candidate.title or "",
            magnet=candidate.magnet or "",
        )
        async with self._tracking_lock:
            self._tracked_downloads[tracking_id] = tracked

    async def poll(self, context: BotContext) -> None:
        bot = getattr(context, "bot", None)
        if bot is None:
            LOGGER.debug("Skipping download poll: no bot available in context.")
            return

        tracked_items = await self._snapshot_tracked()
        if not tracked_items:
            return

        loop = asyncio.get_running_loop()
        try:
            statuses = await loop.run_in_executor(None, self._transmission.list_torrents, False)
        except SystemExit as exc:  # defensive
            LOGGER.warning("Transmission status poll aborted: %s", exc)
            return
        except Exception as exc:  # defensive
            LOGGER.warning("Transmission status poll failed: %s", exc)
            return

        completed: List[Tuple[str, TrackedDownload]] = []
        for tracking_id, tracked in tracked_items:
            status = self._match_status(statuses, tracked)
            if status and status.is_complete:
                completed.append((tracking_id, tracked))
                text = f"✅ Torrent ready: {status.name}"
                await bot.send_message(chat_id=tracked.chat_id, text=text)

        if not completed:
            return

        await self._clear_tracked([tracking_id for tracking_id, _ in completed])

    def enable_background_tasks(self, application: Application, interval_seconds: int = 30) -> None:
        job_queue = getattr(application, "job_queue", None)
        if not job_queue:
            LOGGER.warning(
                "Telegram JobQueue not available; falling back to asyncio polling every %ss. "
                "Install python-telegram-bot[job-queue] for native scheduling.",
                interval_seconds,
            )
            application.post_init = self._chain_lifecycle_callback(
                application.post_init,
                partial(self._start_fallback_polling, interval_seconds=interval_seconds),
            )
            application.post_shutdown = self._chain_lifecycle_callback(
                application.post_shutdown,
                self._stop_fallback_polling,
            )
            return
        job_queue.run_repeating(
            self.poll,
            interval=interval_seconds,
            first=interval_seconds,
            name="torrent-download-monitor",
        )

    async def _start_fallback_polling(self, application: Application, interval_seconds: int) -> None:
        if self._fallback_poll_task:
            return
        self._stop_fallback_event = asyncio.Event()
        self._fallback_poll_task = asyncio.create_task(self._fallback_poll_loop(application, interval_seconds))

    async def _stop_fallback_polling(self, _: Application) -> None:
        if not self._fallback_poll_task or not self._stop_fallback_event:
            return
        self._stop_fallback_event.set()
        await self._fallback_poll_task
        self._fallback_poll_task = None
        self._stop_fallback_event = None

    async def _fallback_poll_loop(self, application: Application, interval_seconds: int) -> None:
        await asyncio.sleep(interval_seconds)
        bot = getattr(application, "bot", None)
        if bot is None:
            LOGGER.debug("Skipping fallback polling: application has no bot.")
            return

        context = cast(BotContext, cast(object, SimpleNamespace(bot=bot)))
        while self._stop_fallback_event and not self._stop_fallback_event.is_set():
            try:
                await self.poll(context)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # defensive, keep the loop alive
                LOGGER.warning("Fallback polling cycle failed: %s", exc, exc_info=True)
            await asyncio.sleep(interval_seconds)

    async def _snapshot_tracked(self) -> List[Tuple[str, TrackedDownload]]:
        async with self._tracking_lock:
            return list(self._tracked_downloads.items())

    async def _clear_tracked(self, tracking_ids: List[str]) -> None:
        async with self._tracking_lock:
            for tracking_id in tracking_ids:
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

    @staticmethod
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

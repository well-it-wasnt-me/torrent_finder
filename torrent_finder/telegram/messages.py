from typing import Dict, List, Optional, Union

from torrent_finder.categories import describe_preset
from torrent_finder.models import Candidate
from torrent_finder.transmission import TransmissionController

DEFAULT_STATUS_DESCRIPTIONS = {
    "downloading": "actively downloading",
    "seeding": "completed and seeding",
    "stopped": "paused or finished",
    "paused": "paused",
    "checking": "verifying data",
    "queued": "waiting in queue",
    "error": "Transmission reported an error",
}


class MessageFactory:
    def __init__(self, status_desc: Optional[Dict[str, str]] = None) -> None:
        # Copy to avoid accidental mutation of defaults.
        self._status_desc = dict(status_desc or DEFAULT_STATUS_DESCRIPTIONS)

    @staticmethod
    def search_prompt(query: str, preset_slug: Optional[str]) -> str:
        if preset_slug == "all":
            return f"Searching all categories for “{query}”…"
        if preset_slug:
            return f"Searching {describe_preset(preset_slug)} for “{query}”…"
        return f"Searching for “{query}”…"

    def explain_status(self, status: str) -> str:
        key = status.lower()
        return self._status_desc.get(key, "status reported by Transmission")

    def format_status_report(self, statuses: List[TransmissionController.TorrentStatus]) -> str:
        def progress_bar(percent: Optional[float], width: int = 10) -> str:
            if percent is None:
                return "?" * width
            filled = int(round(percent / 100.0 * width))
            filled = min(max(filled, 0), width)
            return "#" * filled + "-" * (width - filled)

        def format_eta(eta: Optional[Union[int, float, str]]) -> str:
            if eta is None:
                return "—"
            if isinstance(eta, str):
                return eta
            try:
                seconds = int(float(eta))
            except (TypeError, ValueError):
                return "—"
            minutes = seconds // 60
            hours = minutes // 60
            if hours:
                return f"{hours}h{minutes % 60:02}m"
            if minutes:
                return f"{minutes}m"
            return f"{seconds}s"

        blocks: List[str] = []
        for status in statuses:
            if status.percent_done is None:
                percent = None
            else:
                percent = status.percent_done * 100.0 if status.percent_done <= 1.0 else status.percent_done
            progress = f"{percent:5.1f}%" if percent is not None else " ?"
            bar = progress_bar(percent)
            torrent_id = str(status.torrent_id) if status.torrent_id is not None else "—"
            blocks.extend(
                [
                    f"ID  : {torrent_id}",
                    f"Name: {status.name or '(unknown)'}",
                    f"State: {self.explain_status(status.status)}",
                    f"Done : {progress}   {bar}",
                    f"ETA  : {format_eta(getattr(status, 'eta', None))}",
                    "",
                ]
            )
        if blocks and blocks[-1] == "":
            blocks.pop()
        return "\n".join(blocks)

    def format_status_table(self, statuses: List[TransmissionController.TorrentStatus]) -> str:
        return self.format_status_report(statuses)

    @staticmethod
    def format_bytes(value: Optional[int]) -> str:
        if not value:
            return "unknown"
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(value)
        idx = 0
        while size >= 1024.0 and idx < len(units) - 1:
            size /= 1024.0
            idx += 1
        if idx == 0:
            return f"{int(size)} {units[idx]}"
        return f"{size:.1f} {units[idx]}"

    def format_candidate_card(self, index: int, candidate: Candidate) -> List[str]:
        title = candidate.title or "(untitled)"
        seeders = candidate.seeders if candidate.seeders is not None else "?"
        leechers = candidate.leechers if candidate.leechers is not None else "?"
        size = self.format_bytes(candidate.size_bytes)
        source = candidate.source or "torznab"
        return [
            f"{index}. {title}",
            f"seeds: {seeders} | peers: {leechers} | size: {size} | source: {source}",
        ]

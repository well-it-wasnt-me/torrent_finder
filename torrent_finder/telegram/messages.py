from typing import Dict, List, Optional, Union

from torrent_finder.categories import describe_preset
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

    def format_status_table(self, statuses: List[TransmissionController.TorrentStatus]) -> str:
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

        rows: List[Dict[str, str]] = []
        for status in statuses:
            percent = (status.percent_done * 100.0) if status.percent_done is not None else None
            progress = f"{percent:5.1f}%" if percent is not None else " ?"
            rows.append(
                {
                    "name": status.name or "(unknown)",
                    "status": self.explain_status(status.status),
                    "progress": progress,
                    "eta": format_eta(getattr(status, "eta", None)),
                }
            )

        columns = [
            ("Name", "name"),
            ("Status", "status"),
            ("Progress", "progress"),
            ("ETA", "eta"),
        ]
        widths: List[int] = []
        for header, key in columns:
            width = len(header)
            for row in rows:
                width = max(width, len(row[key]))
            widths.append(width)

        header_line = " | ".join(header.ljust(width) for (header, _), width in zip(columns, widths))
        divider = "-+-".join("-" * width for width in widths)
        body_lines = []
        for row in rows:
            body_lines.append(" | ".join(row[key].ljust(width) for (_, key), width in zip(columns, widths)))

        return "\n".join([header_line, divider, *body_lines])

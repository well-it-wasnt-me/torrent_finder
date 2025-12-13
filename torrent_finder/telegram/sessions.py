from dataclasses import dataclass
from typing import Dict, List, Optional

from torrent_finder.models import Candidate


@dataclass
class PendingSearch:
    query: str
    candidates: List[Candidate]


class UserSessions:
    """Per-chat storage for pending searches and download choices."""

    def __init__(self) -> None:
        self._pending_searches: Dict[int, PendingSearch] = {}
        self._download_choices: Dict[int, Candidate] = {}

    def save_search(self, chat_id: int, query: str, candidates: List[Candidate]) -> None:
        self._pending_searches[chat_id] = PendingSearch(query=query, candidates=candidates)

    def get_search(self, chat_id: int) -> Optional[PendingSearch]:
        return self._pending_searches.get(chat_id)

    def clear_search(self, chat_id: int) -> None:
        self._pending_searches.pop(chat_id, None)

    def remember_download_choice(self, chat_id: int, candidate: Candidate) -> None:
        self._download_choices[chat_id] = candidate

    def pop_download_choice(self, chat_id: int) -> Optional[Candidate]:
        return self._download_choices.pop(chat_id, None)

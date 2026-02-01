from dataclasses import dataclass
from typing import Dict, List, Optional

from torrent_finder.models import Candidate


@dataclass
class PendingSearch:
    query: str
    candidates: List[Candidate]
    page_size: int
    page: int = 0
    preset_slug: Optional[str] = None
    categories: Optional[str] = None


@dataclass
class SearchPrompt:
    preset_slug: Optional[str]


class UserSessions:
    """Per-chat storage for pending searches and download choices."""

    def __init__(self) -> None:
        self._pending_searches: Dict[int, PendingSearch] = {}
        self._download_choices: Dict[int, Candidate] = {}
        self._pending_prompts: Dict[int, SearchPrompt] = {}

    def save_search(
        self,
        chat_id: int,
        query: str,
        candidates: List[Candidate],
        page_size: int,
        preset_slug: Optional[str],
        categories: Optional[str],
    ) -> None:
        self._pending_searches[chat_id] = PendingSearch(
            query=query,
            candidates=candidates,
            page_size=page_size,
            page=0,
            preset_slug=preset_slug,
            categories=categories,
        )

    def get_search(self, chat_id: int) -> Optional[PendingSearch]:
        return self._pending_searches.get(chat_id)

    def clear_search(self, chat_id: int) -> None:
        self._pending_searches.pop(chat_id, None)

    def remember_download_choice(self, chat_id: int, candidate: Candidate) -> None:
        self._download_choices[chat_id] = candidate

    def pop_download_choice(self, chat_id: int) -> Optional[Candidate]:
        return self._download_choices.pop(chat_id, None)

    def set_pending_prompt(self, chat_id: int, preset_slug: Optional[str]) -> None:
        self._pending_prompts[chat_id] = SearchPrompt(preset_slug=preset_slug)

    def get_pending_prompt(self, chat_id: int) -> Optional[SearchPrompt]:
        return self._pending_prompts.get(chat_id)

    def clear_pending_prompt(self, chat_id: int) -> None:
        self._pending_prompts.pop(chat_id, None)

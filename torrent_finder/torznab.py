from __future__ import annotations

"""
Torznab client logic.

This module translates polite search queries into Torznab calls and
returns torrents that might actually be worth your time.
"""

import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from typing import List, Optional

import requests

from .config import TorznabConfig
from .models import Candidate


def _title_matches(query: str, title: str) -> bool:
    """
    Check whether all meaningful tokens from the query appear in the title.

    Parameters
    ----------
    query : str
        Original search text.
    title : str
        Candidate title from Torznab.

    Returns
    -------
    bool
        ``True`` when the title passes the smell test.
    """

    tokens = [token for token in re.split(r"\W+", query.lower()) if len(token) >= 3]
    normalized = title.lower()
    return all(token in normalized for token in tokens) if tokens else True


def _safe_int(value) -> Optional[int]:
    """
    Coerce a value into an integer, shrugging off commas and weird types.

    Parameters
    ----------
    value : Any
        Seed or peer count from Torznab.

    Returns
    -------
    int | None
        Parsed integer, or ``None`` if it wasn't meant to be.
    """

    try:
        return int(str(value).replace(",", ""))
    except Exception:
        return None


class TorznabClient:
    """Thin wrapper around requests.Session dedicated to Torznab endpoints."""

    def __init__(self, config: TorznabConfig):
        """
        Parameters
        ----------
        config : TorznabConfig
            Connection details and etiquette for Torznab.
        """

        self.config = config
        self._session_local = threading.local()

    def _make_session(self) -> requests.Session:
        """
        Create a configured requests session.

        Returns
        -------
        requests.Session
            Session seeded with the configured User-Agent and headers.
        """

        session = requests.Session()
        session.headers.update({"User-Agent": self.config.user_agent, "Accept-Language": "en-US,en;q=0.7"})
        return session

    def _get_session(self) -> requests.Session:
        """
        Return a thread-local session instance.
        """

        session = getattr(self._session_local, "session", None)
        if session is None:
            session = self._make_session()
            self._session_local.session = session
        return session

    def search(self, title: str, debug: bool = False) -> List[Candidate]:
        """
        Query Torznab for candidates that match ``title``.

        Parameters
        ----------
        title : str
            Search phrase, presumably legal and tasteful.
        debug : bool, optional
            When ``True`` emits extra logging so you can narrate the drama.

        Returns
        -------
        list[Candidate]
            Candidates that survived parsing and filtering.
        """

        params = self._build_params(title)

        session = self._get_session()

        try:
            response = session.get(
                self.config.url,
                params=params,
                timeout=self.config.request_timeout,
            )
        except Exception as exc:
            logging.error("Torznab request failed: %s", exc)
            return []

        body_preview = response.text[:600]
        time.sleep(self.config.sleep_between_requests)

        if response.status_code != 200:
            logging.warning("Torznab status %s, head: %r", response.status_code, body_preview)
            return []

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError:
            logging.warning("Torznab non-XML head: %r", body_preview)
            return []

        items = root.findall(".//item")
        if debug:
            logging.info("Torznab raw items: %d", len(items))
            if not items:
                logging.warning("Torznab 200 but zero items. Body head: %r", body_preview)
        elif not items:
            logging.debug("Torznab 200 but zero items. Body head: %r", body_preview)

        candidates = self._parse_items(items, title)

        if debug:
            logging.info("Torznab filtered items (match '%s'): %d", title, len(candidates))
            for candidate in candidates[:5]:
                logging.info(
                    "  match: %s | seeds=%s peers=%s",
                    candidate.title,
                    candidate.seeders,
                    candidate.leechers,
                )

        return candidates

    def _build_params(self, query: str) -> dict[str, str]:
        """
        Build the Torznab parameter payload for both classic and v2.0 endpoints.

        Parameters
        ----------
        query : str
            Search string.

        Returns
        -------
        dict[str, str]
            Query parameters ready for sending.
        """

        params = {"apikey": self.config.apikey}

        # Classic Torznab
        params["t"] = "search"
        params["q"] = query

        # Jackett v2.0 variants
        params["Query"] = query
        params["Title"] = query

        if self.config.categories:
            params["cat"] = self.config.categories
            categories = [item.strip() for item in self.config.categories.split(",") if item.strip()]
            for idx, cat in enumerate(categories):
                params[f"Category[{idx}]"] = cat

        return params

    def _parse_items(self, items, query: str) -> List[Candidate]:
        """
        Convert XML items into Candidate instances.

        Parameters
        ----------
        items : Iterable
            XML ``<item>`` elements straight from Torznab.
        query : str
            Original query, used for title filtering.

        Returns
        -------
        list[Candidate]
            Cleaned and filtered candidate list.
        """

        matches: List[Candidate] = []

        for item in items:
            title = (item.findtext("title") or "").strip()
            if title and not _title_matches(query, title):
                continue

            magnet = self._extract_magnet(item)
            if not magnet:
                continue

            seeders = None
            leechers = None
            for attr in item.findall("{http://torznab.com/schemas/2015/feed}attr"):
                name = (attr.get("name") or "").lower()
                value = _safe_int(attr.get("value"))
                if name == "seeders":
                    seeders = value
                elif name in ("leechers", "peers"):
                    leechers = value

            matches.append(Candidate(magnet=magnet, title=title or None, seeders=seeders, leechers=leechers))

        return matches

    @staticmethod
    def _extract_magnet(item) -> Optional[str]:
        """
        Pluck magnet links from an XML item.

        Parameters
        ----------
        item : xml.etree.ElementTree.Element
            Item node from the RSS feed.

        Returns
        -------
        str | None
            Magnet URI if located, otherwise ``None``.
        """

        enclosure = item.find("enclosure")
        if enclosure is not None:
            magnet = enclosure.get("url", "")
            if magnet.lower().startswith("magnet:"):
                return magnet

        link = item.find("link")
        if link is not None and link.text and link.text.strip().lower().startswith("magnet:"):
            return link.text.strip()

        guid = item.find("guid")
        if guid is not None and guid.text:
            text = guid.text.strip()
            if text.lower().startswith("magnet:"):
                return text

        for attr in item.findall("{http://torznab.com/schemas/2015/feed}attr"):
            name = (attr.get("name") or "").lower()
            if name in {"magneturl", "magneturi", "magnet"}:
                value = (attr.get("value") or "").strip()
                if value.lower().startswith("magnet:"):
                    return value

        return None

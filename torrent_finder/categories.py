from __future__ import annotations

"""Helpers for user-friendly Torznab category presets."""

from dataclasses import dataclass
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class CategoryPreset:
    """Named category shortcut that expands into Torznab category IDs."""

    slug: str
    label: str
    categories: Optional[str]
    aliases: Sequence[str]


_PRESETS: Tuple[CategoryPreset, ...] = (
    CategoryPreset(
        slug="movies",
        label="Movies",
        categories="2000",
        aliases=("movie", "movies", "film", "films"),
    ),
    CategoryPreset(
        slug="tv",
        label="TV Shows",
        categories="5000",
        aliases=("tv", "tvshow", "tv-show", "tv shows", "tv show", "series", "tvseries"),
    ),
    CategoryPreset(
        slug="software",
        label="Software",
        categories="4000",
        aliases=("software", "apps", "application", "applications"),
    ),
    CategoryPreset(
        slug="software-mac",
        label="Software (macOS)",
        categories="4050",
        aliases=("software mac", "mac software", "mac", "macos"),
    ),
    CategoryPreset(
        slug="software-win",
        label="Software (Windows)",
        categories="4010,4020",
        aliases=("software win", "software windows", "win software", "windows software", "windows"),
    ),
    CategoryPreset(
        slug="all",
        label="All categories",
        categories="",
        aliases=("all", "any"),
    ),
)

_PRESETS_BY_SLUG: Dict[str, CategoryPreset] = {preset.slug: preset for preset in _PRESETS}


def available_presets() -> List[str]:
    """Return the list of preset slugs exposed to users."""

    return [preset.slug for preset in _PRESETS]


def categories_for_preset(slug: str) -> Optional[str]:
    """Translate a preset slug into the raw Torznab category string."""

    preset = _PRESETS_BY_SLUG.get(slug)
    if not preset:
        raise KeyError(f"Unknown category preset: {slug}")
    return preset.categories


def describe_preset(slug: str) -> str:
    """Return a human-friendly label for the preset."""

    preset = _PRESETS_BY_SLUG.get(slug)
    if not preset:
        raise KeyError(f"Unknown category preset: {slug}")
    return preset.label


def _build_alias_pattern(alias: str) -> re.Pattern[str]:
    tokens = [token for token in re.split(r"[\s-]+", alias.strip()) if token]
    joined = r"[\s-]+".join(re.escape(token) for token in tokens)
    return re.compile(rf"^\s*{joined}(?:[\s-]+(?P<remainder>.+))?$", re.IGNORECASE)


_ALIAS_RULES: List[Tuple[re.Pattern[str], str, int]] = []
for preset in _PRESETS:
    for alias in preset.aliases:
        pattern = _build_alias_pattern(alias)
        _ALIAS_RULES.append((pattern, preset.slug, len(alias)))

# Prefer longer aliases ("tv show" before "tv").
_ALIAS_RULES.sort(key=lambda item: item[2], reverse=True)


def extract_preset_from_query(query: str) -> Tuple[Optional[str], str, Optional[str]]:
    """Detect category preset prefixes inside a free-form search query.

    Parameters
    ----------
    query : str
        User-supplied string. Anything after the optional category prefix is
        returned untouched (aside from trimming whitespace).

    Returns
    -------
    tuple
        ``(categories, remainder, slug)`` where ``categories`` is the Torznab
        category string (``None`` when no filter applies), ``remainder`` is the
        sanitized search text, and ``slug`` is the matching preset slug (``None``
        if no preset keyword was detected).
    """

    trimmed = query.strip()
    if not trimmed:
        return None, "", None

    for pattern, slug, _ in _ALIAS_RULES:
        match = pattern.match(trimmed)
        if not match:
            continue
        remainder = match.group("remainder") or ""
        remainder = remainder.strip()
        return categories_for_preset(slug), remainder, slug

    return None, trimmed, None

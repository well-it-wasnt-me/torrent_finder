from __future__ import annotations

import unittest

from torrent_finder import categories


class CategoryPresetTests(unittest.TestCase):
    def test_categories_for_known_preset(self) -> None:
        value = categories.categories_for_preset("movies")
        self.assertEqual(value, "2000")

    def test_extract_from_query_with_alias(self) -> None:
        cat, remainder, slug = categories.extract_preset_from_query("TV show The Bear")
        self.assertEqual(cat, "5000")
        self.assertEqual(remainder, "The Bear")
        self.assertEqual(slug, "tv")

    def test_extract_returns_original_when_missing(self) -> None:
        cat, remainder, slug = categories.extract_preset_from_query("dune part two")
        self.assertIsNone(cat)
        self.assertEqual(remainder, "dune part two")
        self.assertIsNone(slug)

    def test_extract_handles_all_keyword(self) -> None:
        cat, remainder, slug = categories.extract_preset_from_query("all dune")
        self.assertEqual(cat, "")
        self.assertEqual(remainder, "dune")
        self.assertEqual(slug, "all")


if __name__ == "__main__":
    unittest.main()

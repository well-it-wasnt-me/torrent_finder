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

    def test_extract_handles_comics_keyword(self) -> None:
        cat, remainder, slug = categories.extract_preset_from_query("comics saga")
        self.assertEqual(cat, "7030")
        self.assertEqual(remainder, "saga")
        self.assertEqual(slug, "comics")

    def test_extract_handles_zip_files_keyword(self) -> None:
        cat, remainder, slug = categories.extract_preset_from_query("zip files release pack")
        self.assertEqual(cat, "8000")
        self.assertEqual(remainder, "release pack")
        self.assertEqual(slug, "zip")

    def test_extract_handles_dump_alias(self) -> None:
        cat, remainder, slug = categories.extract_preset_from_query("dump whatever dune")
        self.assertEqual(cat, "")
        self.assertEqual(remainder, "dune")
        self.assertEqual(slug, "all")

    def test_available_presets_include_new_slugs(self) -> None:
        presets = categories.available_presets()
        self.assertIn("comics", presets)
        self.assertIn("zip", presets)
        self.assertIn("all", presets)


if __name__ == "__main__":
    unittest.main()

"""Tests for SearchHadith, focusing on filtering results and safe field access."""

import pytest

from ansari.tools.search_hadith import SearchHadith


@pytest.fixture
def search_hadith():
    """Create a SearchHadith instance with a dummy API key."""
    return SearchHadith("dummy_api_key")


# --- Filtering tests ---


class TestFilterResults:
    def test_preserves_all_normal_results(self, search_hadith):
        """All results have text content, none should be filtered."""
        results = [
            {
                "id": "bukhari:1",
                "en_text": "English text",
                "ar_text": "Arabic text",
                "grade_en": "Sahih",
                "source_book": "Bukhari",
                "chapter_number": "1",
                "hadith_number": "1",
                "type": "hadith",
            },
        ]
        filtered = search_hadith._filter_results(results)
        assert len(filtered) == 1

    def test_removes_results_without_text(self, search_hadith):
        """Results missing both ar_text and en_text should be removed."""
        results = [
            {"id": "bukhari:1", "type": "hadith"},
            {
                "id": "bukhari:2",
                "en_text": "Some hadith text",
                "ar_text": "Arabic",
                "grade_en": "Sahih",
                "source_book": "Bukhari",
                "chapter_number": "1",
                "hadith_number": "2",
                "type": "hadith",
            },
        ]
        filtered = search_hadith._filter_results(results)
        assert len(filtered) == 1
        assert filtered[0]["id"] == "bukhari:2"

    def test_all_empty_returns_empty(self, search_hadith):
        """When all results lack text, return empty list."""
        results = [
            {"id": "h:1", "type": "hadith"},
            {"id": "h:2", "type": "hadith"},
        ]
        filtered = search_hadith._filter_results(results)
        assert filtered == []

    def test_empty_input(self, search_hadith):
        """Empty input returns empty list."""
        assert search_hadith._filter_results([]) == []

    def test_empty_string_text_filtered(self, search_hadith):
        """Results with empty-string text fields should be filtered."""
        results = [
            {"id": "h:1", "ar_text": "", "en_text": "", "type": "hadith"},
        ]
        filtered = search_hadith._filter_results(results)
        assert filtered == []

    def test_whitespace_only_text_filtered(self, search_hadith):
        """Results with whitespace-only text fields should be filtered."""
        results = [
            {"id": "h:1", "ar_text": "   ", "en_text": "\t\n", "type": "hadith"},
        ]
        filtered = search_hadith._filter_results(results)
        assert filtered == []

    def test_only_ar_text_preserved(self, search_hadith):
        """Result with only Arabic text should be preserved."""
        results = [{"id": "h:1", "ar_text": "Arabic text", "type": "hadith"}]
        filtered = search_hadith._filter_results(results)
        assert len(filtered) == 1

    def test_only_en_text_preserved(self, search_hadith):
        """Result with only English text should be preserved."""
        results = [{"id": "h:1", "en_text": "English text", "type": "hadith"}]
        filtered = search_hadith._filter_results(results)
        assert len(filtered) == 1

    def test_none_text_values_filtered(self, search_hadith):
        """Results with None text values should be filtered."""
        results = [{"id": "h:1", "ar_text": None, "en_text": None, "type": "hadith"}]
        filtered = search_hadith._filter_results(results)
        assert filtered == []


# --- pp_hadith safe access tests ---


class TestPpHadith:
    def test_normal_hadith(self, search_hadith):
        """Test formatting a normal hadith with all fields."""
        h = {
            "id": "bukhari:1",
            "en_text": "Actions are by intentions",
            "grade_en": "Sahih",
            "source_book": "Bukhari",
            "chapter_number": "1",
            "hadith_number": "1",
        }
        result = search_hadith.pp_hadith(h)
        assert "Bukhari" in result
        assert "Actions are by intentions" in result
        assert "Grade: Sahih" in result

    def test_missing_all_fields(self, search_hadith):
        """pp_hadith should not crash when all expected fields are missing."""
        h = {"id": "unknown:1"}
        result = search_hadith.pp_hadith(h)
        assert isinstance(result, str)
        # Should contain at least the id
        assert "unknown:1" in result

    def test_missing_grade(self, search_hadith):
        """pp_hadith should handle missing grade_en gracefully."""
        h = {
            "id": "h:1",
            "en_text": "Some text",
            "source_book": "Muslim",
            "chapter_number": "5",
            "hadith_number": "10",
        }
        result = search_hadith.pp_hadith(h)
        assert "Some text" in result
        assert "Grade:" not in result

    def test_none_grade(self, search_hadith):
        """pp_hadith should handle None grade_en without crashing."""
        h = {
            "id": "h:1",
            "en_text": "Some text",
            "grade_en": None,
            "source_book": "Muslim",
            "chapter_number": "5",
            "hadith_number": "10",
        }
        result = search_hadith.pp_hadith(h)
        assert "Some text" in result

    def test_completely_empty_dict(self, search_hadith):
        """pp_hadith should handle an empty dict without crashing."""
        h = {}
        result = search_hadith.pp_hadith(h)
        assert isinstance(result, str)

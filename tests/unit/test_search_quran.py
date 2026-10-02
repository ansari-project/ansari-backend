"""Tests for SearchQuran, focusing on filtering navigational results and formatting."""

import pytest

from ansari.tools.search_quran import SearchQuran


@pytest.fixture
def search_quran():
    """Create a SearchQuran instance with a dummy API key."""
    return SearchQuran("dummy_api_key")


# --- Filtering tests ---


class TestFilterResults:
    def test_preserves_all_normal_results(self, search_quran):
        """All results have text content, none should be filtered."""
        results = [
            {"id": "12:1", "text": "Arabic text", "en_text": "English text", "type": "quran_verse"},
            {"id": "31:2", "text": "More Arabic", "en_text": "More English", "type": "quran_verse"},
        ]
        filtered = search_quran._filter_results(results)
        assert len(filtered) == 2
        assert filtered == results

    def test_removes_navigational_results(self, search_quran):
        """Mixed results: navigational ones (no text) should be removed."""
        results = [
            {"id": "2:255", "navigational": 1, "type": "quran_verse"},
            {"id": "12:1", "text": "Arabic text", "en_text": "English text", "type": "quran_verse"},
            {"id": "31:2", "text": "More Arabic", "en_text": "More English", "type": "quran_verse"},
        ]
        filtered = search_quran._filter_results(results)
        assert len(filtered) == 2
        assert all(r["id"] != "2:255" for r in filtered)

    def test_all_navigational_returns_empty(self, search_quran):
        """When all results are navigational, return empty list."""
        results = [
            {"id": "2:255", "navigational": 1, "type": "quran_verse"},
            {"id": "3:100", "navigational": 1, "type": "quran_verse"},
        ]
        filtered = search_quran._filter_results(results)
        assert filtered == []

    def test_empty_input(self, search_quran):
        """Empty input returns empty list."""
        assert search_quran._filter_results([]) == []

    def test_empty_string_text_filtered(self, search_quran):
        """Results with empty-string text fields should be filtered."""
        results = [
            {"id": "1:1", "text": "", "en_text": "", "type": "quran_verse"},
            {"id": "2:1", "text": "Real text", "en_text": "Real English", "type": "quran_verse"},
        ]
        filtered = search_quran._filter_results(results)
        assert len(filtered) == 1
        assert filtered[0]["id"] == "2:1"

    def test_whitespace_only_text_filtered(self, search_quran):
        """Results with whitespace-only text fields should be filtered."""
        results = [
            {"id": "1:1", "text": "  \t ", "en_text": "  \n ", "type": "quran_verse"},
            {"id": "2:1", "text": "Real text", "type": "quran_verse"},
        ]
        filtered = search_quran._filter_results(results)
        assert len(filtered) == 1
        assert filtered[0]["id"] == "2:1"

    def test_only_arabic_text_preserved(self, search_quran):
        """Result with only Arabic text (no en_text) should be preserved."""
        results = [
            {"id": "1:1", "text": "Arabic only", "type": "quran_verse"},
        ]
        filtered = search_quran._filter_results(results)
        assert len(filtered) == 1

    def test_only_english_text_preserved(self, search_quran):
        """Result with only English text (no text) should be preserved."""
        results = [
            {"id": "1:1", "en_text": "English only", "type": "quran_verse"},
        ]
        filtered = search_quran._filter_results(results)
        assert len(filtered) == 1

    def test_none_text_values_filtered(self, search_quran):
        """Results with None text values should be filtered."""
        results = [
            {"id": "1:1", "text": None, "en_text": None, "type": "quran_verse"},
        ]
        filtered = search_quran._filter_results(results)
        assert filtered == []

    def test_issue_20_exact_data(self, search_quran):
        """Test with the exact data from issue #20."""
        results = [
            {"id": "2:255", "navigational": 1, "type": "quran_verse"},
            {
                "en_text": "Alif-Lam-Ra. These are the verses of the clear Book.",
                "id": "12:1",
                "text": "الٓر ۚ تِلْكَ ءَايَـٰتُ ٱلْكِتَـٰبِ ٱلْمُبِينِ",
                "type": "quran_verse",
            },
        ]
        filtered = search_quran._filter_results(results)
        assert len(filtered) == 1
        assert filtered[0]["id"] == "12:1"


# --- pp_ayah tests ---


class TestPpAyah:
    def test_normal_ayah(self, search_quran):
        """Test formatting a normal ayah with all fields."""
        ayah = {"id": "2:255", "text": "Arabic", "en_text": "English"}
        result = search_quran.pp_ayah(ayah)
        assert "2:255" in result
        assert "Arabic" in result
        assert "English" in result

    def test_ayah_missing_text(self, search_quran):
        """Test formatting an ayah with missing text field."""
        ayah = {"id": "2:255", "en_text": "English only"}
        result = search_quran.pp_ayah(ayah)
        assert "2:255" in result
        assert "English only" in result

    def test_ayah_missing_all_text(self, search_quran):
        """Test formatting an ayah with no text fields (navigational)."""
        ayah = {"id": "2:255", "navigational": 1, "type": "quran_verse"}
        result = search_quran.pp_ayah(ayah)
        assert "2:255" in result
        # Should not crash, even though text is missing


# --- format_as_ref_list tests ---


class TestFormatAsRefList:
    def test_normal_results(self, search_quran):
        """Test ref list formatting with normal results."""
        results = [
            {"id": "12:1", "text": "Arabic text", "en_text": "English text", "type": "quran_verse"},
        ]
        docs = search_quran.format_as_ref_list(results)
        assert len(docs) == 1
        assert docs[0]["type"] == "document"
        assert "Quran 12:1" in docs[0]["title"]

    def test_empty_results(self, search_quran):
        """Test ref list formatting with empty results."""
        docs = search_quran.format_as_ref_list([])
        assert docs == []


# --- format_as_tool_result tests ---


class TestFormatAsToolResult:
    def test_normal_results(self, search_quran):
        """Test tool result formatting with normal results."""
        results = [
            {"id": "12:1", "text": "Arabic text", "en_text": "English text", "type": "quran_verse"},
        ]
        tool_results = search_quran.format_as_tool_result(results)
        assert len(tool_results) == 1
        assert "Arabic text" in tool_results[0]["text"]
        assert "English text" in tool_results[0]["text"]

    def test_empty_results(self, search_quran):
        """Test tool result formatting with empty results."""
        tool_results = search_quran.format_as_tool_result([])
        assert tool_results == []

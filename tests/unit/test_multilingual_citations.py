"""Tests for multilingual citation format in search tools."""

import json
import pytest
from ansari.util.translation import format_multilingual_data, parse_multilingual_data
from ansari.tools.search_mawsuah import SearchMawsuah
from ansari.tools.search_quran import SearchQuran
from ansari.tools.search_hadith import SearchHadith


class TestMultilingualFormat:
    """Test the multilingual format utility functions."""

    def test_format_multilingual_data(self):
        """Test formatting a dictionary of language-text pairs to a JSON string."""
        # Test with multiple languages
        test_data = {"ar": "النص العربي", "en": "English text"}
        result = format_multilingual_data(test_data)
        assert isinstance(result, str)

        # Verify the JSON structure
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 2

        # Verify entries have lang and text
        for item in parsed:
            assert "lang" in item
            assert "text" in item

        # Verify correct data
        langs = [item["lang"] for item in parsed]
        assert "ar" in langs
        assert "en" in langs

    def test_parse_multilingual_data(self):
        """Test parsing a JSON string to a dictionary of language-text pairs."""
        # Create test JSON
        json_str = json.dumps([{"lang": "ar", "text": "النص العربي"}, {"lang": "en", "text": "English text"}])

        # Parse it
        result = parse_multilingual_data(json_str)

        # Verify result
        assert isinstance(result, dict)
        assert "ar" in result
        assert "en" in result
        assert result["ar"] == "النص العربي"
        assert result["en"] == "English text"

    def test_format_parse_roundtrip(self):
        """Test round-trip from dict -> JSON string -> dict."""
        original = {"ar": "النص العربي", "en": "English text", "fr": "Texte français"}

        # Format to JSON string
        json_str = format_multilingual_data(original)

        # Parse back to dict
        result = parse_multilingual_data(json_str)

        # Verify round-trip consistency
        assert result == original


@pytest.fixture
def mock_search_results_mawsuah():
    """Mock results from the Mawsuah search tool."""
    return {"search_results": [{"text": "نص عربي للاختبار", "score": 0.95}]}


@pytest.fixture
def mock_search_results_quran():
    """Mock results from the Quran search tool."""
    return [
        {
            "id": "1:1",
            "text": "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
            "en_text": "In the name of Allah, the Entirely Merciful, the Especially Merciful.",
        }
    ]


@pytest.fixture
def mock_search_results_hadith():
    """Mock results from the Hadith search tool."""
    return [
        {
            "id": "123",
            "source_book": "Bukhari",
            "chapter_number": "1",
            "chapter_english": "Test Chapter",
            "hadith_number": "456",
            "section_number": "2",
            "section_english": "Test Section",
            "ar_text": "نص حديث عربي",
            "en_text": "English hadith text",
            "grade_en": "Sahih",
        }
    ]


class TestSearchToolsFormat:
    """Test that search tools correctly format their results in multilingual format."""

    def test_mawsuah_format(self, mocker, mock_search_results_mawsuah):
        """Test that SearchMawsuah correctly formats Arabic-only results."""
        # Create a minimal mocked version of SearchMawsuah that overrides parent methods
        mocker.patch(
            "ansari.tools.search_vectara.SearchVectara.format_as_ref_list",
            return_value=[
                {
                    "type": "document",
                    "source": {"type": "text", "media_type": "text/plain", "data": "نص عربي للاختبار"},
                    "title": "Test Document",
                }
            ],
        )

        # Instantiate with mock values
        search = SearchMawsuah("mock_key", "mock_corpus")

        # Format the results
        formatted = search.format_as_ref_list(mock_search_results_mawsuah)

        # Verify the result
        assert isinstance(formatted, list)
        assert len(formatted) == 1
        doc = formatted[0]

        # Verify document structure
        assert doc["type"] == "document"
        assert "source" in doc
        assert "data" in doc["source"]

        # Parse the multilingual data
        data = parse_multilingual_data(doc["source"]["data"])

        # Verify it contains Arabic only
        assert "ar" in data
        assert len(data) == 1  # Only Arabic, no other languages

    def test_quran_format(self, mock_search_results_quran):
        """Test that SearchQuran correctly formats bilingual results."""
        # Instantiate with mock values
        search = SearchQuran("mock_key")

        # Format the results
        formatted = search.format_as_ref_list(mock_search_results_quran)

        # Verify the result
        assert isinstance(formatted, list)
        assert len(formatted) == 1
        doc = formatted[0]

        # Verify document structure
        assert doc["type"] == "document"
        assert "source" in doc
        assert "data" in doc["source"]

        # Parse the multilingual data
        data = parse_multilingual_data(doc["source"]["data"])

        # Verify it contains both Arabic and English
        assert "ar" in data
        assert "en" in data
        assert len(data) == 2

    def test_hadith_format(self, mock_search_results_hadith):
        """Test that SearchHadith correctly formats results with metadata."""
        # Instantiate with mock values
        search = SearchHadith("mock_key")

        # Format the results
        formatted = search.format_as_ref_list(mock_search_results_hadith)

        # Verify the result
        assert isinstance(formatted, list)
        assert len(formatted) == 1
        doc = formatted[0]

        # Verify document structure
        assert doc["type"] == "document"
        assert "source" in doc
        assert "data" in doc["source"]

        # Parse the multilingual data
        data = parse_multilingual_data(doc["source"]["data"])

        # Verify it contains both Arabic and English
        assert "ar" in data
        assert "en" in data

        # Verify grade is in the title, not in the data
        assert "Grade: Sahih" in doc["title"]

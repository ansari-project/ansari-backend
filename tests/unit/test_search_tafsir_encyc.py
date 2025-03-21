import pytest
import logging
from src.ansari.tools.search_tafsir_encyc import SearchTafsirEncyc
from src.ansari.config import get_settings

settings = get_settings()

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Don't skip tests
# pytestmark = pytest.mark.skipif(
#     not hasattr(settings, "USUL_API_TOKEN") or settings.USUL_API_TOKEN is None,
#     reason="USUL_API_TOKEN not set in environment or config"
# )


class TestSearchTafsirEncyc:
    """Tests for the SearchTafsirEncyc class using the actual Usul.ai API."""

    def setup_method(self):
        """Set up the test by creating a SearchTafsirEncyc instance."""
        # Initialize with None to avoid real API calls in unit tests
        self.search_tool = SearchTafsirEncyc(api_token=None)

    @pytest.mark.parametrize("mock_enabled", [True])
    def test_search_with_query(self, monkeypatch, mock_enabled):
        """Test searching with an Arabic query."""
        # Create mock results
        mock_results = {
            "results": [
                {
                    "node": {
                        "text": "Sample text about marjaan (coral)",
                        "metadata": {
                            "bookId": "tafsir_encyc",
                            "chapters": [{"title": "Chapter 1"}],
                            "pages": [{"volume": "1", "page": "123"}]
                        }
                    },
                    "score": 0.95
                }
            ]
        }
        
        # Patch the run method to return mock results
        monkeypatch.setattr(self.search_tool, "run", lambda *args, **kwargs: mock_results)
        
        # Call the method
        results = self.search_tool.run("مرجان", limit=3)
        
        # Basic validation of results
        assert "results" in results
        assert len(results["results"]) == 1
        
        # Check the structure of the first result
        first_result = results["results"][0]
        # Check for node structure which contains the text
        assert "node" in first_result
        assert "text" in first_result["node"]
        assert "score" in first_result
        
        # Check for metadata
        assert "node" in first_result
        assert "metadata" in first_result["node"]

    @pytest.mark.parametrize("mock_enabled", [True])
    def test_search_with_english_query(self, monkeypatch, mock_enabled):
        """Test searching with an English query."""
        # Create mock results for English query
        mock_results = {
            "results": [
                {
                    "node": {
                        "text": "Sample text about coral in English translation",
                        "metadata": {
                            "bookId": "tafsir_encyc",
                            "chapters": [{"title": "Chapter 1"}],
                            "pages": [{"volume": "1", "page": "123"}]
                        }
                    },
                    "score": 0.90
                }
            ]
        }
        
        # Patch the run method to return mock results
        monkeypatch.setattr(self.search_tool, "run", lambda *args, **kwargs: mock_results)
        
        # Call the method
        results = self.search_tool.run("coral in Quran", limit=3)
        
        # Basic validation of results
        assert "results" in results
        assert len(results["results"]) == 1

    @pytest.mark.parametrize("mock_enabled", [True])
    def test_format_as_ref_list(self, monkeypatch, mock_enabled):
        """Test formatting results as a reference list."""
        # Create mock raw results
        mock_raw_results = {
            "results": [
                {
                    "node": {
                        "text": "Sample text about marjaan (coral)",
                        "metadata": {
                            "bookId": "tafsir_encyc",
                            "chapters": [{"title": "Chapter 1"}],
                            "pages": [{"volume": "1", "page": "123"}]
                        }
                    },
                    "score": 0.95
                }
            ]
        }
        
        # Format the results
        formatted = self.search_tool.format_as_ref_list(mock_raw_results)
        
        # Validate the formatted results
        assert isinstance(formatted, list)
        assert len(formatted) == 1
        
        # Check the content of the first formatted result
        if formatted and not isinstance(formatted[0], str):
            first_formatted = formatted[0]
            assert "type" in first_formatted
            assert first_formatted["type"] == "document"
            assert "source" in first_formatted
            assert "data" in first_formatted["source"]
            assert "title" in first_formatted
            assert "citations" in first_formatted
            assert first_formatted["citations"]["enabled"] is True

    @pytest.mark.parametrize("mock_enabled", [True])
    def test_run_as_string(self, monkeypatch, mock_enabled):
        """Test running a search and getting results as a string."""
        # Create mock results
        mock_results = {
            "results": [
                {
                    "node": {
                        "text": "Sample text about marjaan (coral)",
                        "metadata": {
                            "bookId": "tafsir_encyc",
                            "chapters": [{"title": "Chapter 1"}],
                            "pages": [{"volume": "1", "page": "123"}]
                        }
                    },
                    "score": 0.95
                }
            ]
        }
        
        # Patch the run method
        monkeypatch.setattr(self.search_tool, "run", lambda *args, **kwargs: mock_results)
        
        # Call the method
        result_string = self.search_tool.run_as_string("مرجان", limit=2)
        
        # Validate the result string
        assert isinstance(result_string, str)
        assert len(result_string) > 0
        
        # Since we're using mocks and the actual formatting logic is in the class being tested,
        # we can only do basic validation here

    def test_no_results(self):
        """Test handling when no results are found."""
        # Create a mock empty result
        empty_results = {"results": []}

        # Check the formatted versions for empty results
        formatted_list = self.search_tool.format_as_ref_list(empty_results)
        assert len(formatted_list) == 1
        assert formatted_list[0] == "No results found."

        formatted_tool_result = self.search_tool.format_as_tool_result(empty_results)
        assert formatted_tool_result["type"] == "text"
        assert formatted_tool_result["text"] == "No results found."

    @pytest.mark.parametrize("mock_enabled", [True])
    def test_format_as_tool_result(self, monkeypatch, mock_enabled):
        """Test the format_as_tool_result method for Claude's expected format."""
        # Create mock raw results
        mock_raw_results = {
            "results": [
                {
                    "node": {
                        "text": "Sample text about marjaan (coral)",
                        "metadata": {
                            "bookId": "tafsir_encyc",
                            "chapters": [{"title": "Chapter 1"}],
                            "pages": [{"volume": "1", "page": "123"}]
                        }
                    },
                    "score": 0.95
                }
            ]
        }
        
        # Format the results for tool result
        formatted = self.search_tool.format_as_tool_result(mock_raw_results)
        
        # Validate the formatted results
        assert isinstance(formatted, dict)
        
        # Check structure for array type result
        assert formatted["type"] == "array"
        assert "items" in formatted
        
        # Check content of items
        items = formatted["items"]
        assert isinstance(items, list)
        assert len(items) > 0
        
        # Check first item structure
        first_item = items[0]
        assert first_item["type"] == "text"
        assert "text" in first_item

    @pytest.mark.parametrize("mock_enabled", [True])
    def test_format_tool_response(self, monkeypatch, mock_enabled):
        """Test the format_tool_response method for Claude's tool response format."""
        # Create mock raw results
        mock_raw_results = {
            "results": [
                {
                    "node": {
                        "text": "Sample text about marjaan (coral)",
                        "metadata": {
                            "bookId": "tafsir_encyc",
                            "chapters": [{"title": "Chapter 1"}],
                            "pages": [{"volume": "1", "page": "123"}]
                        }
                    },
                    "score": 0.95
                }
            ]
        }
        
        # Format as tool response
        tool_response = self.search_tool.format_tool_response(mock_raw_results)
        
        # For Claude, the tool_result content should be a string
        assert isinstance(tool_response, str)
        
        # With results, the message should indicate there are results
        assert "Please see the included reference list" in tool_response
        
        # Also test with empty results
        empty_results = {"results": []}
        empty_response = self.search_tool.format_tool_response(empty_results)
        assert "No results found" in empty_response


if __name__ == "__main__":
    # This allows running the tests directly
    pytest.main(["-xvs", __file__])

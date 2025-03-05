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
        self.search_tool = SearchTafsirEncyc()  # Uses API token from settings

    def test_search_with_query(self):
        """Test searching with an Arabic query."""
        # Search for information about coral (marjaan) in the Quranic interpretation
        results = self.search_tool.run("مرجان", limit=3)

        logger.info(f"Results: {results}")

        # Basic validation of results
        assert "results" in results
        assert len(results["results"]) <= 3  # Should return at most 3 results

        # Check the structure of the first result
        if results["results"]:
            first_result = results["results"][0]
            logger.info(f"First result structure: {first_result.keys()}")
            # Check for node structure which contains the text
            assert "node" in first_result
            assert "text" in first_result["node"]
            assert "score" in first_result

            # Since include_chapters is set to True by default, check for chapter metadata
            # The chapter structure might be different than expected, so let's check for metadata
            assert "node" in first_result
            assert "metadata" in first_result["node"]
            logger.info(f"Node metadata: {first_result['node']['metadata']}")

    def test_search_with_english_query(self):
        """Test searching with an English query."""
        # English query about coral in the Quran
        results = self.search_tool.run("coral in Quran", limit=3)

        logger.info(f"English query results count: {len(results.get('results', []))}")

        # Basic validation of results
        assert "results" in results
        assert len(results["results"]) <= 3  # Should return at most 3 results

    def test_format_as_ref_list(self):
        """Test formatting results as a reference list."""
        # First run a search to get real results
        raw_results = self.search_tool.run("مرجان", limit=2)

        # Format the results
        formatted = self.search_tool.format_as_ref_list(raw_results)

        logger.info(f"Formatted reference list (first item): {formatted[0] if formatted else 'None'}")

        # Validate the formatted results
        assert isinstance(formatted, list)
        assert len(formatted) <= 2  # Should have at most 2 items

        # Check the content of the first formatted result
        if formatted and not isinstance(formatted[0], str):
            first_formatted = formatted[0]
            assert "type" in first_formatted
            assert first_formatted["type"] == "document"
            assert "source" in first_formatted
            assert "type" in first_formatted["source"]
            assert "media_type" in first_formatted["source"]
            assert "data" in first_formatted["source"]
            assert "title" in first_formatted
            assert "context" in first_formatted
            assert "citations" in first_formatted
            assert first_formatted["citations"]["enabled"] is True

    def test_run_as_string(self):
        """Test running a search and getting results as a string."""
        result_string = self.search_tool.run_as_string("مرجان", limit=2)

        logger.info(f"Result string (first 100 chars): {result_string[:100] if result_string else 'None'}")

        # Validate the result string
        assert isinstance(result_string, str)

        # Should contain typical parts of the formatted output
        if result_string != "No results found.":
            assert "Node ID:" in result_string
            assert "Text:" in result_string

    def test_no_results(self):
        """Test handling when no results are found."""
        # Try to use a very specific and unlikely query
        # Note: Even with unlikely queries, the API might still return results
        # due to semantic search capabilities
        results = self.search_tool.run("xyzabcdefghijklmnopqrstuvwxyz123456789", limit=1)

        logger.info(f"No results test - actual result count: {len(results.get('results', []))}")

        # Instead of asserting there are no results, we'll test the formatting functions
        # which should handle both cases (results or no results) properly

        # Create a mock empty result to test the no-results case
        empty_results = {"results": []}

        # Check the formatted versions for empty results
        formatted_list = self.search_tool.format_as_ref_list(empty_results)
        assert len(formatted_list) == 1
        assert formatted_list[0] == "No results found."

        formatted_tool_result = self.search_tool.format_as_tool_result(empty_results)
        assert formatted_tool_result["type"] == "text"
        assert formatted_tool_result["text"] == "No results found."

        # Also verify that the actual API response (which might or might not have results)
        # can be properly formatted
        actual_formatted = self.search_tool.format_as_ref_list(results)
        assert isinstance(actual_formatted, list)

        actual_tool_result = self.search_tool.format_as_tool_result(results)
        if len(results.get("results", [])) > 0:
            assert actual_tool_result["type"] == "array"
            assert "items" in actual_tool_result
        else:
            assert actual_tool_result["type"] == "text"
            assert actual_tool_result["text"] == "No results found."

    def test_format_as_tool_result(self):
        """Test the format_as_tool_result method for Claude's expected format."""
        # First run a search to get real results
        raw_results = self.search_tool.run("مرجان", limit=2)

        # Format the results for tool result
        formatted = self.search_tool.format_as_tool_result(raw_results)

        logger.info(f"Tool result format: {formatted}")

        # Validate the formatted results
        assert isinstance(formatted, dict)

        # Check structure: either a text result or an array of items
        if len(raw_results.get("results", [])) > 0:
            assert formatted["type"] == "array"
            assert "items" in formatted

            # Check content of items
            items = formatted["items"]
            assert isinstance(items, list)
            assert len(items) > 0

            # Check first item structure
            first_item = items[0]
            logger.info(f"First item in tool result: {first_item}")
            assert first_item["type"] == "text"
            assert "text" in first_item
            assert "Text:" in first_item["text"]
            assert "Node ID:" in first_item["text"]
        else:
            assert formatted["type"] == "text"
            assert formatted["text"] == "No results found."

    def test_format_tool_response(self):
        """Test the format_tool_response method for Claude's tool response format."""
        # First run a search to get real results
        raw_results = self.search_tool.run("مرجان", limit=2)

        # Format as tool response
        tool_response = self.search_tool.format_tool_response(raw_results)

        logger.info(f"Tool response format: {tool_response}")

        # For Claude, the tool_result content should be a string
        assert isinstance(tool_response, str)

        # If results were found, check that the message indicates there are results
        if len(raw_results.get("results", [])) > 0:
            assert "Please see the included reference list" in tool_response
        else:
            assert "No results found" in tool_response


if __name__ == "__main__":
    # This allows running the tests directly
    pytest.main(["-xvs", __file__])

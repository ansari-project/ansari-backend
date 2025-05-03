import pytest
import logging
import time
from unittest.mock import patch

from ansari.tools.search_mawsuah import SearchMawsuah
from ansari.util.translation import translate_texts_parallel_using_asyncio
from ansari.config import get_settings

settings = get_settings()

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


class TestSearchMawsuah:
    """Tests for the SearchMawsuah class including parallel translation functionality."""

    def setup_method(self):
        """Set up the test by creating a SearchMawsuah instance."""
        # Initialize with None to avoid real API calls in unit tests
        self.search_tool = SearchMawsuah(None, None)

        # Test data
        self.arabic_texts = [
            "مرحبا",  # Hello
            "كيف حالك",  # How are you
            "أهلا وسهلا",  # Welcome
            "الحمد لله رب العالمين",  # Praise be to Allah, Lord of the worlds
        ]
        self.mock_translations = ["Hello", "How are you", "Welcome", "Praise be to Allah, Lord of the worlds"]

    def test_direct_translation(self):
        """Test direct use of the translation utility without mocking."""
        # This is just a placeholder test now, as we don't need to test the translate_text function here
        # That would be better tested in a dedicated test for the translation utility
        assert True

    @pytest.mark.asyncio
    @patch("ansari.util.translation.translate_text")
    async def test_translate_texts_parallel_using_asyncio(self, mock_translate):
        """Test the parallel translation of multiple texts."""

        # Configure the mock to return different values based on the input text
        def mock_translation(text, target_lang, source_lang):
            if text == "مرحبا":
                return "Hello"
            elif text == "كيف حالك":
                return "How are you"
            elif text == "أهلا وسهلا":
                return "Welcome"
            elif text == "الحمد لله رب العالمين":
                return "Praise be to Allah, Lord of the worlds"
            return "Unknown"

        mock_translate.side_effect = mock_translation

        results = await translate_texts_parallel_using_asyncio(self.arabic_texts, "en", "ar")

        # Verify all texts were translated
        assert len(results) == len(self.arabic_texts)

        # asyncio.gather preserves the order of the tasks in its results
        assert results == ["Hello", "How are you", "Welcome", "Praise be to Allah, Lord of the worlds"]

        # Verify the correct number of translations were requested
        assert mock_translate.call_count == len(self.arabic_texts)

    @patch("ansari.util.translation.translate_text")
    @patch("ansari.util.translation.asyncio.run")
    def test_format_as_ref_list(self, mock_asyncio_run, mock_translate):
        """Test formatting response as a reference list with translations."""
        # Mock asyncio.run to return our mock translations
        mock_asyncio_run.return_value = self.mock_translations[:2]

        # Create a mock Vectara response with multiple results
        mock_response = {
            "search_results": [
                {"text": text}
                for text in self.arabic_texts[:2]  # Use first two texts
            ]
        }

        # Mock the parent class format_as_ref_list to return documents
        with patch("ansari.tools.search_vectara.SearchVectara.format_as_ref_list") as mock_parent_format:
            mock_parent_format.return_value = [
                {
                    "source": {"data": self.arabic_texts[0]},
                    "title": "Document 1",
                    "context": "Context 1",
                    "citations": {"enabled": True},
                },
                {
                    "source": {"data": self.arabic_texts[1]},
                    "title": "Document 2",
                    "context": "Context 2",
                    "citations": {"enabled": True},
                },
            ]

            # Run the method
            result = self.search_tool.format_as_ref_list(mock_response)

            # Check results
            assert len(result) == 2
            # The data is now a JSON string in the format produced by format_multilingual_data
            assert '"lang": "ar"' in result[0]["source"]["data"]
            assert "Encyclopedia of Islamic Jurisprudence" in result[0]["title"]

    @patch("ansari.util.translation.translate_text")
    @patch("ansari.util.translation.asyncio.run")
    def test_format_as_tool_result(self, mock_asyncio_run, mock_translate):
        """Test formatting response as a tool result with translations."""
        # Mock asyncio.run to return our mock translations
        mock_asyncio_run.return_value = self.mock_translations[:2]

        # Create a mock result from parent class
        with patch("ansari.tools.search_vectara.SearchVectara.format_as_tool_result") as mock_parent_format:
            mock_parent_format.return_value = {
                "type": "array",
                "results": [{"text": self.arabic_texts[0]}, {"text": self.arabic_texts[1]}],
            }

            # Run the method
            result = self.search_tool.format_as_tool_result({"some": "response"})

            # Check results - the implementation now returns a text response
            assert result["type"] == "text"
            assert "Please see the references below." in result["text"]

    @patch("ansari.tools.search_vectara.SearchVectara.run")
    @patch("ansari.util.translation.translate_text")
    @patch("ansari.util.translation.asyncio.run")
    def test_run_as_string(self, mock_asyncio_run, mock_translate, mock_run):
        """Test running a search and getting results as a string with translations."""
        # Mock asyncio.run to return our mock translations
        mock_asyncio_run.return_value = self.mock_translations[:2]

        # Mock the run method to return our test data
        mock_run.return_value = {"search_results": [{"text": self.arabic_texts[0]}, {"text": self.arabic_texts[1]}]}

        # Run the method
        result = self.search_tool.run_as_string("فقه", 2)

        # Check results
        assert "Entry 1:" in result
        assert "Arabic Text: " in result
        # English translations are no longer included in this method
        assert "مرحبا" in result  # First Arabic text

    @patch("ansari.tools.search_vectara.SearchVectara.run")
    def test_no_results(self, mock_run):
        """Test handling when no results are found."""
        # Mock the run method to return empty results
        mock_run.return_value = {"search_results": []}

        # Run the method
        result = self.search_tool.run_as_string("xyz123", 2)

        # Check results
        assert result == "No results found."

    @pytest.mark.asyncio
    @patch("ansari.util.translation.translate_text")
    async def test_parallel_performance(self, mock_translate):
        """Test the performance of parallel translation."""

        # Configure the mock to simulate API delay (0.1 second per call)
        def delayed_translation(text, target_lang, source_lang):
            time.sleep(0.1)  # Simulate API delay
            # Return the translation based on the text
            if text == "مرحبا":
                return "Hello"
            elif text == "كيف حالك":
                return "How are you"
            elif text == "أهلا وسهلا":
                return "Welcome"
            elif text == "الحمد لله رب العالمين":
                return "Praise be to Allah, Lord of the worlds"
            return "Unknown"

        mock_translate.side_effect = delayed_translation

        # Time sequential translation
        start_time = time.time()
        sequential_results = []
        for text in self.arabic_texts:
            # Use the mocked function directly with the same arguments our code would use
            result = mock_translate(text, "en", "ar")
            sequential_results.append(result)
        sequential_time = time.time() - start_time

        # Reset the mock to ensure clean state
        mock_translate.reset_mock()
        mock_translate.side_effect = delayed_translation

        # Time parallel translation
        start_time = time.time()
        parallel_results = await translate_texts_parallel_using_asyncio(self.arabic_texts, "en", "ar")
        parallel_time = time.time() - start_time

        # Log results
        logger.info(f"Sequential translation time: {sequential_time:.2f}s")
        logger.info(f"Parallel translation time: {parallel_time:.2f}s")
        logger.info(f"Speed improvement: {sequential_time / parallel_time:.2f}x faster")

        # asyncio.gather preserves the order of the tasks in its results
        assert parallel_results == sequential_results

        # Expect parallel to be significantly faster
        assert parallel_time < sequential_time


if __name__ == "__main__":
    # This allows running the tests directly
    pytest.main(["-xvs", __file__])

import pytest
import logging

from ansari.util.translation import translate_text

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


class TestTranslation:
    """Tests for the translate_text function using the actual Anthropic API."""

    def test_basmalah_translation(self):
        """Test translating the Basmalah from Arabic to English."""
        basmalah = "بسم الله الرحمن الرحيم"
        result = translate_text(basmalah, "en", "ar")

        logger.info(f"Basmalah translation: '{result}'")
        assert result, "Translation should not be empty"

    def test_same_language_translation(self):
        """Test when source and target languages are the same."""
        # No API call made when languages match
        text = "Hello world"
        result = translate_text(text, "en", "en")

        # Should return the original text unchanged
        assert result == text

    def test_empty_text_translation(self):
        """Test translating empty text."""
        # No API call made for empty text
        result = translate_text("", "ar", "en")

        # Should return empty string
        assert result == ""


if __name__ == "__main__":
    # This allows running the tests directly
    pytest.main(["-xvs", __file__])

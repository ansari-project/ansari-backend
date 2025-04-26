import pytest
import json
import logging

# Import both the original and robust versions for comparison
from ansari.util.translation import parse_multilingual_data as original_parse
from ansari.util.translation import format_multilingual_data
from ansari.util.robust_translation import parse_multilingual_data as robust_parse
from ansari.util.robust_translation import process_document_source_data

from ansari.agents.ansari_claude import AnsariClaude
from ansari.config import get_settings

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


class TestMultilingualDataParsing:
    """Tests for the parse_multilingual_data function and its handling of malformed data."""

    def test_valid_json_parsing(self):
        """Test parsing valid JSON-formatted multilingual data."""
        # Create a valid JSON string
        data = json.dumps([
            {"lang": "ar", "text": "النص العربي"},
            {"lang": "en", "text": "English text"}
        ])
        
        # Parse the data with original parser
        result_original = original_parse(data)
        
        # Parse with robust parser
        result_robust = robust_parse(data)
        
        # Both should give the same results for valid JSON
        assert "ar" in result_original, "Arabic text should be in the original result"
        assert "en" in result_original, "English text should be in the original result"
        assert result_original["ar"] == "النص العربي", "Arabic text should match the input"
        assert result_original["en"] == "English text", "English text should match the input"
        
        # Robust parser should match
        assert result_robust == result_original, "Robust parser should match original for valid JSON"

    def test_malformed_json_handling(self):
        """Test handling of malformed JSON data."""
        # Malformed JSON string (missing quotes, commas, etc.)
        malformed_data = '{lang: ar, text: النص العربي}'
        arabic_text = "النص العربي"
        
        # Original parser raises JSONDecodeError
        with pytest.raises(json.JSONDecodeError):
            original_parse(malformed_data)
        
        # Robust parser should handle it
        result = robust_parse(malformed_data)
        assert isinstance(result, dict), "Result should be a dictionary"
        
        # It should have detected some text
        assert any(result.values()), "Should have extracted some text"
        logger.info(f"Robust parser extracted: {result}")

    def test_invalid_format_handling(self):
        """Test handling of valid JSON but invalid format."""
        # Valid JSON but wrong format (not a list of objects)
        invalid_format = json.dumps({"key": "value"})
        
        # Original parser raises ValueError
        with pytest.raises(ValueError):
            original_parse(invalid_format)
        
        # Robust parser should handle it
        result = robust_parse(invalid_format)
        assert isinstance(result, dict), "Result should be a dictionary"
        assert "text" in result, "Should contain a text key for non-list JSON"
        
    def test_arabic_text_handling(self):
        """Test handling of plain Arabic text."""
        # Arabic text from the example
        arabic_text = "وذهب أكثر الفقهاء إلى أن الإكراه على التلفظ بلفظ ما يمنع ترتيب أثره عليه"
        
        # Original parser raises JSONDecodeError
        with pytest.raises(json.JSONDecodeError):
            original_parse(arabic_text)
        
        # Robust parser should handle it
        result = robust_parse(arabic_text)
        assert "ar" in result, "Should detect Arabic language"
        assert result["ar"] == arabic_text, "Should preserve the original text"

    def test_document_source_processing(self):
        """Test the document source processing function with different types of data."""
        # Test with Arabic text
        arabic_text = "وذهب أكثر الفقهاء إلى أن الإكراه على التلفظ بلفظ ما يمنع ترتيب أثره عليه"
        arabic_doc = {
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain",
                "data": arabic_text
            },
            "title": "Test Document",
            "context": "Test Context",
            "citations": {
                "enabled": True
            }
        }
        
        # Process the document
        processed_doc = process_document_source_data(arabic_doc.copy())
        
        # Check the result
        assert "source" in processed_doc, "Should have a source field"
        assert "data" in processed_doc["source"], "Should have a data field"
        processed_data = processed_doc["source"]["data"]
        logger.info(f"Processed Arabic data: {processed_data}")
        assert "Arabic:" in processed_data, "Should be prefixed with 'Arabic:'"
        
        # Test with real example from the error
        real_example = "وذهب أكثر الفقهاء إلى أن الإكراه على التلفظ بلفظ ما يمنع ترتيب أثره عليه ولو كان كلمة الكفر، لقوله تعالى: ﴿إلا من أكره وقلبه مطمئن بالإيمان﴾(٣)_________(١)مغني المحتاج ٣ / ٣٧٥، والاختيار ٣ / ١٦٩، وبدائع الصنائع ٣ / ٢٤٢، وشرح منتهى الإرادات ٣ / ٢٠٧، والفواكه الدواني ٢ / ٨٥.(٢)سورة النور / ٦ - ٩.(٣)سورة النحل / ١٠٦.ولحديث: إن الله وضع عن أمتي الخطأ والنسيان وما استكرهوا عليه(١).وللتفصيل(ر: إكراه ف ١٨ - ٢٤).د - قصد معاني الألفاظ:\n١٠ - اللفظ هو الصورة التي تحمل مراد المتكلم إلى السامع، فإذا كان صاحب اللفظ جاهلا بمعناه كالأعجمي لم يعد اللفظ صالحا لتأدية هذا المعنى، فيسقط اعتباره."
        real_doc = {
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain",
                "data": real_example
            },
            "title": "Encyclopedia of Quranic Interpretation",
            "context": "Retrieved from the Encyclopedia",
            "citations": {
                "enabled": True
            }
        }
        
        # Process the document with the real example
        processed_real_doc = process_document_source_data(real_doc.copy())
        
        # Check the result
        processed_real_data = processed_real_doc["source"]["data"]
        logger.info(f"Processed real example data (truncated): {processed_real_data[:50]}...")
        assert "Arabic:" in processed_real_data, "Should detect Arabic in real example"
        
        # Test with valid JSON data
        json_data = json.dumps([
            {"lang": "ar", "text": "النص العربي"},
            {"lang": "en", "text": "English text"}
        ])
        json_doc = {
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain",
                "data": json_data
            },
            "title": "Test Document",
            "context": "Test Context",
            "citations": {
                "enabled": True
            }
        }
        
        # Process the document with JSON data
        processed_json_doc = process_document_source_data(json_doc.copy())
        
        # Check the result
        processed_json_data = processed_json_doc["source"]["data"]
        logger.info(f"Processed JSON data: {processed_json_data}")
        assert "Arabic:" in processed_json_data, "Should extract Arabic from JSON"
        assert "English:" in processed_json_data, "Should extract English from JSON"


if __name__ == "__main__":
    # This allows running the tests directly
    pytest.main(["-xvs", __file__])
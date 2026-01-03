# Enhanced version of the translation utility with more robust parsing

import json
import logging
from typing import Dict

from ansari.util.general_helpers import get_language_from_text

# Set up logging
logger = logging.getLogger(__name__)


def format_multilingual_data(text_entries: Dict[str, str]) -> str:
    """Convert a dictionary of language-text pairs to a JSON string.

    This function is used by search tools to format multilingual content
    in a consistent way. The format allows tools that return content in
    multiple languages (like Quran and Hadith) to be properly handled,
    and avoids duplicate translations.

    Args:
        text_entries: Dictionary mapping language codes to text
            e.g., {"ar": "النص العربي", "en": "English text"}

    Returns:
        JSON string representing language-text pairs in the format:
        [
            {"lang": "ar", "text": "النص العربي"},
            {"lang": "en", "text": "English translation"}
        ]
    """
    result = []
    for lang, text in text_entries.items():
        if text:  # Only include non-empty text
            result.append({"lang": lang, "text": text})
    return json.dumps(result)


def parse_multilingual_data(data: str) -> Dict[str, str]:
    """Parse a JSON string representing multilingual content into a dictionary.

    This is an enhanced version of the original parse_multilingual_data function
    with more robust error handling.

    Args:
        data: JSON string in the format returned by format_multilingual_data
             OR plain text that will be detected and handled

    Returns:
        Dictionary mapping language codes to text
        e.g., {"ar": "النص العربي", "en": "English text"}
    """
    # First, try standard JSON parsing
    try:
        parsed = json.loads(data)
        if not isinstance(parsed, list):
            logger.warning("Expected a JSON array but got something else")
            # Fall back to treating as plain text
            return {"text": data}

        result = {}
        for item in parsed:
            if not isinstance(item, dict) or "lang" not in item or "text" not in item:
                logger.warning("JSON item missing 'lang' or 'text' fields")
                continue
            result[item["lang"]] = item["text"]

        # If we extracted any languages, return them
        if result:
            return result

        # Otherwise, treat as plain text
        logger.warning("No valid language entries found in JSON")
        return {"text": data}

    except json.JSONDecodeError:
        # If JSON parsing fails, try to detect if it's Arabic text
        logger.debug("JSON parsing failed, attempting language detection")

        try:
            # If it contains Arabic characters, it's likely Arabic text
            if any(0x0600 <= ord(c) <= 0x06FF for c in data[:50]):
                logger.debug("Detected Arabic text based on character range")
                return {"ar": data}

            # Otherwise use language detection
            lang = get_language_from_text(data)
            logger.debug(f"Detected language: {lang}")

            if lang == "ar":
                return {"ar": data}
            else:
                # Use the detected language
                return {lang: data}

        except Exception as e:
            logger.error(f"Error during language detection: {e}")
            # Fall back to treating as generic text
            return {"text": data}

    except Exception as e:
        logger.error(f"Unexpected error in parse_multilingual_data: {e}")
        # Create a safe fallback dictionary
        return {"text": data}


def process_document_source_data(doc: dict) -> dict:
    """Process a document's source data to ensure it's properly formatted.

    This function tries to parse the document's source data as JSON, and if that fails,
    it formats the text based on language detection.

    Args:
        doc: The document to process

    Returns:
        The processed document
    """
    if "source" not in doc or "data" not in doc["source"]:
        return doc

    try:
        # Try to parse the source data as multilingual data
        original_data = doc["source"]["data"]
        parsed_data = parse_multilingual_data(original_data)

        # Format the data based on the parsed result
        text_list = []
        if "ar" in parsed_data:
            text_list.append(f"Arabic: {parsed_data['ar']}")
        if "en" in parsed_data:
            text_list.append(f"English: {parsed_data['en']}")
        if not text_list and "text" in parsed_data:
            text_list.append(f"Text: {parsed_data['text']}")

        # Set the source data to the formatted text
        if text_list:
            doc["source"]["data"] = "\n\n".join(text_list)

    except Exception as e:
        logger.error(f"Error processing document source data: {e}")
        # Try a simple fallback
        try:
            original_text = doc["source"]["data"]
            if isinstance(original_text, str):
                # Just prefix with "Text:" to maintain expected format
                doc["source"]["data"] = f"Text: {original_text}"
        except Exception:
            pass

    return doc

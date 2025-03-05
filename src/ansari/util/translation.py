# Translation utility for Ansari using Claude models

import anthropic
from typing import Dict, Optional
import asyncio
import json

from ansari.ansari_logger import get_logger
from ansari.config import get_settings
from ansari.util.general_helpers import get_language_from_text

logger = get_logger(__name__)


def translate_text(
    text: str, target_lang: str, source_lang: Optional[str] = None, model: str = "claude-3-5-haiku-20241022"
) -> str:
    """Translates text using Claude models, defaulting to latest Haiku.

    Args:
        text (str): The text to translate
        target_lang (str): Target language code (e.g., "ar", "en") or name (e.g., "Arabic", "English")
        source_lang (Optional[str], optional): Source language code or name. If None, auto-detected.
        model (str, optional): Claude model to use. Defaults to "claude-3-5-haiku-20241022".

    Returns:
        str: The translated text

    Raises:
        Exception: If translation fails
    """
    if not text:
        return ""

    # Get settings and initialize Anthropic client
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

    # Detect source language if not provided
    if not source_lang:
        source_lang = get_language_from_text(text)

    # Return original text if target language is the same as source
    if source_lang == target_lang:
        return text

    try:
        # Call Claude for translation
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=0.0,
            system=(
                "You are a professional translator. Translate the text accurately while preserving meaning, tone, "
                "and formatting. Only return the translation, nothing else."
            ),
            messages=[{"role": "user", "content": f"Translate this text from {source_lang} to {target_lang}:\n\n{text}"}],
        )

        translation = response.content[0].text.strip()
        return translation

    except Exception as e:
        logger.error(f"Translation error: {str(e)}")
        raise


async def translate_texts_parallel(texts: list[str], target_lang: str = "en", source_lang: str = "ar") -> list[str]:
    """
    Translate multiple texts in parallel.

    Args:
        texts: List of texts to translate
        target_lang: Target language code (e.g., "ar", "en")
        source_lang: Source language code (e.g., "ar", "en")

    Returns:
        List of translations
    """
    if not texts:
        return []

    # Create translation tasks for all texts
    tasks = [asyncio.to_thread(translate_text, text, target_lang, source_lang) for text in texts]

    # Run all translations in parallel and return results
    return await asyncio.gather(*tasks)


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

    This is the reverse of format_multilingual_data.

    Args:
        data: JSON string in the format returned by format_multilingual_data

    Returns:
        Dictionary mapping language codes to text
        e.g., {"ar": "النص العربي", "en": "English text"}

    Raises:
        json.JSONDecodeError: If the data is not valid JSON
        ValueError: If the data is not in the expected format
    """
    try:
        parsed = json.loads(data)
        if not isinstance(parsed, list):
            raise ValueError("Expected a JSON array")

        result = {}
        for item in parsed:
            if not isinstance(item, dict) or "lang" not in item or "text" not in item:
                raise ValueError("Expected items with 'lang' and 'text' fields")
            result[item["lang"]] = item["text"]
        return result

    except json.JSONDecodeError:
        raise
    except Exception as e:
        raise ValueError(f"Invalid multilingual data format: {str(e)}")

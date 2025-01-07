from fastapi import Depends, HTTPException, Request
from jwt import PyJWTError
from langdetect import detect

from ansari.ansari_logger import get_logger
from ansari.config import Settings, get_settings

logger = get_logger()


# Defined in a separate file to avoid circular imports between main_*.py files
def validate_cors(request: Request, settings: Settings = Depends(get_settings)) -> bool:
    try:
        # logger.debug(f"Headers of raw request are: {request.headers}")
        origins = get_settings().ORIGINS
        incoming_origin = [
            request.headers.get("origin", ""),  # If coming from ansari's frontend website
            request.headers.get("host", ""),  # If coming from Meta's WhatsApp API
        ]

        mobile = request.headers.get("x-mobile-ansari", "")
        if any(i_o in origins for i_o in incoming_origin) or mobile == "ANSARI":
            logger.debug("CORS OK")
            return True
        raise HTTPException(status_code=502, detail=f"Incoming origin/host: {incoming_origin} is not in origin list")
    except PyJWTError:
        raise HTTPException(status_code=403, detail="Could not validate credentials")


def _check_if_mostly_english(text: str, threshold: float = 0.8):
    """
    Check if the majority of characters in the input string lie within the ASCII range 65 to 122.

    Parameters:
    - text (str): The string to check.
    - threshold (float): The threshold percentage (e.g., 0.8 for 80%).

    Returns:
    - bool: True if the percentage of characters in the range is above the threshold, False otherwise.
    """

    # Count total characters in the input string
    total_chars = len(text)

    if total_chars == 0:
        return False  # If the string is empty, return False

    # Count characters within the ASCII range 65 to 122
    count_in_range = sum(1 for char in text if 65 <= ord(char) <= 122)

    # Calculate the percentage of characters in range
    percentage_in_range = count_in_range / total_chars

    # Check if this percentage meets or exceeds the threshold
    return percentage_in_range >= threshold


def get_language_from_text(text: str) -> str:
    """Extracts the language from the given text.

    Args:
        text (str): The text from which to extract the language.

    Returns:
        str: The language extracted from the given text in ISO 639-1 format ("en", "ar", etc.).

    """

    if len(text) < 45 and _check_if_mostly_english(text):
        # If user starts with small phrases like "Al salamu Alyykom",
        # they get translated to "tl/id/etc." for some reason,
        # so default to "en" in this case
        logger.debug("Defaulting to English due to short English text")
        return "en"

    try:
        detected_lang = detect(text)
    except Exception as e:
        logger.error(f'Error detecting language (so will return "en" instead): {e}')
        return "en"

    return detected_lang

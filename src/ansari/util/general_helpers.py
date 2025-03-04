# This file aims to provide general (miscellaneous) utility functions that can be used across the codebase.

import unicodedata as ud
from typing import Literal

from fastapi import Depends, HTTPException, Request
from jwt import PyJWTError
from langdetect import detect

from ansari.ansari_logger import get_logger
from ansari.config import Settings, get_settings

logger = get_logger(__name__)


def get_extended_origins(settings: Settings = Depends(get_settings)):
    origins = get_settings().ORIGINS

    # This if condition only runs in local development
    # Also, if we don't execute the code below, we'll get a "400 Bad Request" error when
    # trying to access the API from the local frontend
    if get_settings().DEV_MODE:
        # Change "8081" to the port of your frontend server (8081 is the default there)
        local_origin = "http://localhost:8081"
        zrok_origin = get_settings().ZROK_SHARE_TOKEN.get_secret_value() + ".share.zrok.io"

        if local_origin not in origins:
            origins.append(local_origin)
        if zrok_origin not in origins:
            origins.append(zrok_origin)

    # Make sure CI/CD of GitHub Actions is allowed
    if "testserver" not in origins:
        github_actions_origin = "testserver"
        origins.append(github_actions_origin)

    return origins


# Defined in a separate file to avoid circular imports between main_*.py files
def validate_cors(request: Request, settings: Settings = Depends(get_settings)) -> bool:
    try:
        # logger.debug(f"Headers of raw request are: {request.headers}")
        origins = get_extended_origins()
        incoming_origin = [
            request.headers.get("origin", ""),  # If coming from ansari's frontend website
            request.headers.get("host", ""),  # If coming from Meta's WhatsApp API
        ]

        mobile = request.headers.get("x-mobile-ansari", "")
        if any(i_o in origins for i_o in incoming_origin) or mobile == "ANSARI":
            logger.debug("CORS OK")
            return True
        else:
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


def get_language_direction_from_text(text: str) -> Literal["ltr", "rtl"]:
    """Extracts the language direction from the given text.

    Args:
        text (str): The text from which to extract the language direction.

    Returns:
        str: The language direction extracted from the given text in "ltr" or "rtl" format.

    Notes:
        Determining the direction of a string is complex. But if you are looking at simple approximations,
        you can look at the bidirectional property values in the string.

        Now, there are two methods to determine the overall direction of a line:
        * First strong: matching the first strong character encountered when iterating through the text.
        * Direction strong: look at how many characters in the string are strong LTR and strong RTL, and selecting their max.

        This function uses the first method, which is simpler and faster, and is actually how whatsapp renders text. Source:
        * https://stackoverflow.com/a/75739782/13626137

    """

    try:
        # Determine the bidirectional property of each character in the text
        bidi_properties = [ud.bidirectional(char) for char in text]

        # Map bidirectional properties to "ltr", "rtl", or "-"
        directions = []
        for prop in bidi_properties:
            if prop == "L":
                directions.append("ltr")
            elif prop in ["AL", "R"]:
                directions.append("rtl")
            else:
                directions.append("-")

        # Return the first strong direction encountered
        for direction in directions:
            if direction in ["ltr", "rtl"]:
                return direction
    except Exception as e:
        logger.warning(f'Failure detecting language direction (so will return "ltr" instead) Details: {e}')
        return "ltr"

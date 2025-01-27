from typing import Optional, Union

import requests


def _format_list_param(param: Union[str, list[Union[str, int]]]) -> str:
    """Formats a list or string parameter for API requests."""
    return ",".join(map(str, param)) if isinstance(param, list) else str(param)


def get_verse_by_key(
    verse_key: str,
    language: str = "en",
    words: bool = False,
    translations: Optional[Union[str, list[int]]] = None,
    audio: Optional[int] = None,
    tafsirs: Optional[Union[str, list[int]]] = None,
    word_fields: Optional[Union[str, list[str]]] = None,
    translation_fields: Optional[Union[str, list[str]]] = None,
    fields: Optional[Union[str, list[str]]] = None,
) -> Optional[dict]:
    """Fetches a specific Quran verse by key from Quran.com API.

    Args:
        verse_key: Verse key (chapter:verse), e.g., '1:1'.
        language: Language for word translations (default: 'en').
        words: Include words (default: False).
        translations: Comma-separated string or list of translation IDs.
        audio: Recitation ID for audio.
        tafsirs: Comma-separated string or list of tafsir IDs.
        word_fields: Comma-separated string or list of word fields.
        translation_fields: Comma-separated string or list of translation fields.
        fields: Comma-separated string or list of ayah fields.

    Returns:
        Verse data as dict, or None on failure.

    Raises:
        requests.exceptions.HTTPError: On unsuccessful HTTP request.
    """
    base_url = "https://api.quran.com/api/v4"
    url = f"{base_url}/verses/by_key/{verse_key}"

    params = {"language": language, "words": str(words).lower()}
    if translations:
        params["translations"] = _format_list_param(translations)
    if audio:
        params["audio"] = audio
    if tafsirs:
        params["tafsirs"] = _format_list_param(tafsirs)
    if word_fields:
        params["word_fields"] = _format_list_param(word_fields)
    if translation_fields:
        params["translation_fields"] = _format_list_param(translation_fields)
    if fields:
        params["fields"] = _format_list_param(fields)

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error: {http_err}")
        raise http_err
    except Exception as err:
        print(f"Error: {err}")
        return None


def get_uthmani_ayah(
    chapter_number=None,
    juz_number=None,
    page_number=None,
    hizb_number=None,
    rub_el_hizb_number=None,
    verse_key=None,
    simple=False,
    output_format="string",
):
    """
    Fetches Uthmani script of Quranic ayat from the Quran.com API.
    You can choose between simple script (without tashkiq) or full Uthmani script (with tashkiq).

    You can filter results using query parameters:
    - chapter_number: Get script of a specific surah.
    - juz_number: Get script of a specific juz.
    - page_number: Get script of a Madani Muhsaf page.
    - hizb_number: Get script of a specific hizb.
    - rub_el_hizb_number: Get script of a Rub el Hizb.
    - verse_key: Get script of a specific ayah (e.g., '1:1' for Al-Fatiha ayah 1).

    Leave all query parameters as None to fetch the script of the whole Quran.

    Args:
        chapter_number (int, optional): Chapter number (1-114). Defaults to None.
        juz_number (int, optional): Juz number (1-30). Defaults to None.
        page_number (int, optional): Page number (1-604). Defaults to None.
        hizb_number (int, optional): Hizb number (1-60). Defaults to None.
        rub_el_hizb_number (int, optional): Rub el Hizb number (1-240). Defaults to None.
        verse_key (str, optional): Verse key (e.g., '1:1'). Defaults to None.
        simple (bool, optional): If True, fetches Uthmani simple script (no tashkeel).
                                 If False (default), fetches full Uthmani script (with tashkeel).
        output_format (str, optional): Desired output format.
            - "dict" (default): Returns a list of ayah dictionaries.
            - "list": Returns a list of strings, where each string is the text of an ayah.
            - "string": Returns a single string containing all ayah texts concatenated.

    Returns:
        list or str or None: Based on output_format, returns:
            - list of ayah dictionaries if output_format is "dict".
            - list of strings if output_format is "list".
            - single string if output_format is "string".
            - None if there's an error during the API request or data processing.
            Returns an empty list or empty string if no ayat are found matching the criteria,
            depending on output_format.
    """

    base_url = "https://api.quran.com/api/v4"
    script_options = {
        True: {"api_path": "/quran/verses/uthmani_simple", "text_key": "text_uthmani_simple"},
        False: {"api_path": "/quran/verses/uthmani", "text_key": "text_uthmani"},
    }
    options = script_options[simple]
    api_path = options["api_path"]
    text_key = options["text_key"]

    url = base_url + api_path
    params = {}
    query_params = {
        "chapter_number": chapter_number,
        "juz_number": juz_number,
        "page_number": page_number,
        "hizb_number": hizb_number,
        "rub_el_hizb_number": rub_el_hizb_number,
        "verse_key": verse_key,
    }
    for key, value in query_params.items():
        if value is not None:
            params[key] = value

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if "verses" in data:
            verses = data["verses"]
            output_formatters = {
                "dict": lambda verses: [{"id": v["id"], "verse_key": v["verse_key"], text_key: v[text_key]} for v in verses],
                "list": lambda verses: [v[text_key] for v in verses],
                "string": lambda verses: " * ".join([v[text_key] for v in verses]),
            }
            formatter = output_formatters.get(output_format, output_formatters["dict"])  # Default to dict
            return formatter(verses)
        else:
            if output_format == "string":
                return ""
            elif output_format == "list":
                return []
            else:  # "dict" or invalid format
                return []

    except requests.exceptions.RequestException as e:
        print(f"Error during API request: {e}")
        return None
    except ValueError as e:
        print(f"Error decoding JSON response: {e}")
        return None
    except KeyError as e:
        print(f"Error accessing data in JSON response: {e}")
        return None


def get_ayah_and_rub_hizb_text(ayah_key: str) -> Optional[tuple[str, str]]:
    """
    Fetches the text of a specific ayah and its rubul-hizb from Quran.com API.

    Args:
        ayah_key: Verse key (chapter:verse), e.g., '1:1'.

    Returns:
        A tuple containing the ayah text and the rubul-hizb text as strings,
        or None if there's an error.
    """
    try:
        verse_data = get_verse_by_key(ayah_key, fields="rub_el_hizb_number")
        if verse_data and "verse" in verse_data:
            rub_el_hizb_number = verse_data["verse"].get("rub_el_hizb_number")
            if rub_el_hizb_number is not None:
                ayah_text = get_uthmani_ayah(verse_key=ayah_key, output_format="string")
                rub_hizb_text = get_uthmani_ayah(rub_el_hizb_number=rub_el_hizb_number, output_format="string")
                return ayah_text, rub_hizb_text
            else:
                print(f"Rub el Hizb number not found for verse key: {ayah_key}")
                return None, None
        else:
            print(f"Could not retrieve verse data for key: {ayah_key}")
            return None, None
    except Exception as e:
        print(f"Error in get_ayah_and_rub_hizb_text: {e}")
        return None, None

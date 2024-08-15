"""
This module provides a robust and efficient interface for fetching and parsing Tafsir Ibn Kathir
from the Quran.com API. It offers granular retrieval options, seamless pagination handling,
optional text cleaning, and progress visualization for a smooth and informative user experience.

Key Features:

- **Granular Retrieval:** Fetch tafsir for individual ayahs, complete surahs, or the entire Quran.
- **Pagination Handling:** Automatically traverses paginated API responses for comprehensive data retrieval.
- **Text Cleaning:** Optionally utilizes BeautifulSoup to remove HTML tags for clean text extraction.
- **Progress Visualization:** Provides progress bar integration for monitoring lengthy operations.
- **Flexible API Interaction:** Leverages different API endpoints for optimal performance based on the request.

Example Usage:

```python
# Instantiate the Tafsir Fetcher
tafsir_fetcher = QuranTafsirFetcher()

# Retrieve Tafsir for the first Ayah of the first Surah
tafsir = tafsir_fetcher.fetch_ayah_tafsir(1, 1)

# Retrieve Tafsir for the entire Quran
quran_tafsir = tafsir_fetcher.fetch_quran_tafsir()
```
"""

import json
from urllib.request import urlopen

import requests
from bs4 import BeautifulSoup
from tqdm.notebook import tqdm

# Constants for API endpoints
API_BASE_URL_V4 = "https://api.quran.com/api/v4/tafsirs"
API_BASE_URL_QDC = "https://api.quran.com/api/qdc/tafsirs"
API_BASE_URL_CDN = "https://api.qurancdn.com/api/qdc/tafsirs"

# Default Tafsir source identifier
DEFAULT_TAFSIR_SOURCE = "en-tafisr-ibn-kathir"


class QuranTafsirFetcher:
    """
    Facilitates the retrieval and management of Tafsir Ibn Kathir data from the Quran.com API.

    This class encapsulates the complexities of API interaction, pagination, and optional text cleaning,
    providing a clean and intuitive interface for fetching Tafsir data.
    """

    def __init__(self, tafsir_source=DEFAULT_TAFSIR_SOURCE, use_beautiful_soup=False):
        """
        Initializes the Tafsir Fetcher with specified configuration.

        Args:
            tafsir_source (str): The identifier for the Tafsir source.
                                  Defaults to "en-tafisr-ibn-kathir" (English Tafsir Ibn Kathir).
            use_beautiful_soup (bool): Whether to use BeautifulSoup to clean the Tafsir text.
                                       Defaults to False.
        """
        self.tafsir_source = tafsir_source
        self.use_beautiful_soup = use_beautiful_soup

    def fetch_ayah_tafsir(self, surah_number: int, ayah_number: int) -> dict:
        """
        Retrieves the Tafsir for a specific Ayah (verse).

        Args:
            surah_number (int): The Surah (chapter) number.
            ayah_number (int): The Ayah (verse) number within the Surah.

        Returns:
            dict: A dictionary containing the Tafsir data for the specified Ayah.
        """
        url = f"{API_BASE_URL_V4}/{self.tafsir_source}/by_ayah/{surah_number}:{ayah_number}"
        response = self._make_api_request(url)
        return response.json().get("tafsir", {})

    def fetch_surah_tafsir(
        self, surah_number: int, text_only=True, show_progress=False
    ) -> list:
        """
        Retrieves all Tafsirs for a given Surah (chapter).

        Args:
            surah_number (int): The Surah (chapter) number.
            text_only (bool): Whether to return only the Tafsir text or the complete API response.
                                     Defaults to True (returns only the text).
            show_progress (bool): Whether to display a progress bar during the retrieval process.
                                  Defaults to False.

        Returns:
            list: A list of Tafsir texts or objects for the specified Surah.
        """
        return self._fetch_tafsir_paginated(
            f"{API_BASE_URL_QDC}/{self.tafsir_source}/by_chapter/{surah_number}",
            text_only,
            show_progress,
            f"Retrieving Tafsirs for Surah {surah_number}",
        )

    def fetch_juz_tafsir(
        self, juz_number: int, text_only=True, show_progress=False
    ) -> list:
        """
        Retrieves all Tafsirs for a given Juz (part of the Quran).

        Args:
            juz_number (int): The Juz number (1-30).
            text_only (bool): Whether to return only the Tafsir text or the complete API response.
                                     Defaults to True (returns only the text).
            show_progress (bool): Whether to display a progress bar during the retrieval process.
                                  Defaults to False.

        Returns:
            list: A list of Tafsir texts or objects for the specified Juz.
        """
        return self._fetch_tafsir_paginated(
            f"{API_BASE_URL_CDN}/{self.tafsir_source}/by_juz/{juz_number}",
            text_only,
            show_progress,
            f"Retrieving Tafsirs for Juz {juz_number}",
        )

    def fetch_quran_tafsir(
        self, text_only=True, show_progress=False, use_juz_api=False
    ) -> list:
        """
        Retrieves Tafsirs for the entire Quran.

        Args:
            text_only (bool): Whether to return only the Tafsir text or the complete API response.
                                     Defaults to True (returns only the text).
            show_progress (bool): Whether to display a progress bar during the retrieval process.
                                  Defaults to False.
            use_juz_api (bool): Whether to use the Juz-based API or the Surah-based API.
                                Defaults to False (uses the Surah-based API).

        Returns:
            list: A list of lists, where each inner list contains the Tafsirs for a specific Surah.
        """
        if use_juz_api:
            return self._fetch_all_surahs_tafsir_by_juz(text_only, show_progress)
        else:
            return self._fetch_all_surahs_tafsir_by_surah(text_only, show_progress)

    def _fetch_all_surahs_tafsir_by_surah(
        self, text_only=True, show_progress=False
    ) -> list:
        """
        Helper function to fetch Tafsirs for all Surahs using the Surah-based API.
        """
        surah_range = range(1, 115)
        if show_progress:
            surah_range = tqdm(
                surah_range, desc="Retrieving Tafsirs for All Surahs (using surah API)"
            )

        return [
            self.fetch_surah_tafsir(surah_number, text_only, show_progress=False)
            for surah_number in surah_range
        ]

    def _fetch_all_surahs_tafsir_by_juz(
        self, text_only=True, show_progress=False
    ) -> list:
        """
        Helper function to fetch Tafsirs for all Surahs using the Juz-based API.
        """
        all_tafsirs = []
        for juz_number in tqdm(
            range(1, 31), desc="Retrieving Tafsirs for All Surahs (using juz API)"
        ):
            all_tafsirs.extend(
                self.fetch_juz_tafsir(
                    juz_number, text_only, show_progress=show_progress
                )
            )
        return all_tafsirs

    def _fetch_tafsir_paginated(
        self, base_url: str, text_only: bool, show_progress: bool, description: str
    ) -> list:
        """
        Helper function to handle paginated API responses.
        """
        all_tafsirs = []
        current_page = 1
        total_pages = 1

        if show_progress:
            progress_bar = tqdm(total=total_pages, desc=description, unit="page")

        while current_page <= total_pages:
            url = f"{base_url}?page={current_page}"
            try:
                response = self._make_api_request(url)
                tafsirs, pagination_data = self._parse_api_response(response)

                if text_only:
                    all_tafsirs.extend(self._extract_text_from_tafsirs(tafsirs))
                else:
                    all_tafsirs.extend(tafsirs)

                total_pages = pagination_data.get("total_pages", 0)
                current_page += 1

                if show_progress:
                    progress_bar.update(1)

            except requests.exceptions.RequestException as error:
                print(f"Error fetching data: {error}")
                break

        if show_progress:
            progress_bar.close()

        return all_tafsirs

    def _make_api_request(self, url: str) -> requests.Response:
        """
        Helper function to make an API request with error handling.
        """
        headers = {"Accept": "application/json"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response

    def _parse_api_response(
        self, response: requests.Response
    ) -> tuple[list[dict], dict]:
        """
        Helper function to parse the JSON response from the API.
        """
        data = response.json()
        return data.get("tafsirs", []), data.get("pagination", {})

    def _extract_text_from_tafsirs(self, tafsirs: list[dict]) -> list[str]:
        """
        Helper function to extract and clean the text from each Tafsir object.
        """
        if self.use_beautiful_soup:
            return [BeautifulSoup(tafsir["text"], "lxml").text for tafsir in tafsirs]
        else:
            return [tafsir["text"] for tafsir in tafsirs]

    def fetch_entire_quran_tafsir_by_ayah(
        self, text_only=True, show_progress=False
    ) -> dict:
        """
        Fetches the Tafsir for the entire Quran using the Ayah API.

        Args:
            text_only (bool): Whether to return only the Tafsir text or the complete API response.
                                     Defaults to True (returns only the text).
            show_progress (bool): Whether to display a progress bar during the retrieval process.
                                  Defaults to False.

        Returns:
            list: A list of Tafsir texts or objects for the entire Quran.
        """
        all_ayah_tafsirs = {}
        for surah_number, ayah_count in tqdm(
            enumerate(self.fetch_ayah_count_per_surah(), start=1),
            desc="Retrieving Tafsirs for the Entire Quran",
            disable=not show_progress,
        ):
            for ayah_number in range(1, ayah_count + 1):
                try:
                    response = self.fetch_ayah_tafsir(surah_number, ayah_number)
                    if text_only:
                        all_ayah_tafsirs[(surah_number, ayah_number)] = response.get(
                            "text", ""
                        )
                    else:
                        all_ayah_tafsirs[(surah_number, ayah_number)] = response
                except requests.exceptions.RequestException as error:
                    print(
                        f"Error fetching data for surah {surah_number}, ayah {ayah_number}: {error}"
                    )
                    all_ayah_tafsirs[(surah_number, ayah_number)] = None
        return all_ayah_tafsirs

    def fetch_ayah_count_per_surah(self) -> list[int]:
        """
        Fetches the number of Ayahs in each Surah.

        Returns:
            list[int]: A list of integers representing the number of Ayahs in each Surah.
        """

        # Define the URL of the surah.json file
        url = "https://raw.githubusercontent.com/semarketir/quranjson/master/source/surah.json"

        # Download the JSON data
        response = urlopen(url)
        data = json.loads(response.read().decode("utf-8"))

        # Extract the ayat count for each surah
        ayat_counts = [surah["count"] for surah in data]
        return ayat_counts


if __name__ == "__main__":
    tafsir_fetcher = QuranTafsirFetcher()
    all_ayat_tafsirs = tafsir_fetcher.fetch_entire_quran_tafsir_by_ayah(
        text_only=True, show_progress=True
    )
    with open("ayat_tafsirs.json", "w") as f:
        json.dump(
            {
                f"{ayah_id[0]}:{ayah_id[1]}": tafsir
                for ayah_id, tafsir in all_ayat_tafsirs.items()
            },
            f,
            indent=1,
            ensure_ascii=False,
        )

    # Example usage
    # Instantiate the Tafsir Fetcher
    # tafsir_fetcher = QuranTafsirFetcher()

    # # --- Fetching Tafsir for a Single Ayah ---
    # # Retrieve Tafsir for the first Ayah of the first Surah (Al-Fatiha)
    # ayah_tafsir = tafsir_fetcher.fetch_ayah_tafsir(surah_number=1, ayah_number=1)
    # print(ayah_tafsir)

    # # --- Fetching Tafsir for an Entire Surah ---
    # # Retrieve Tafsir for Surah Al-Fatiha (Surah 1)
    # surah_tafsir = tafsir_fetcher.fetch_surah_tafsir(surah_number=1)
    # print(surah_tafsir)

    # # --- Fetching Tafsir for a Juz ---
    # # Retrieve Tafsir for Juz 1
    # juz_tafsir = tafsir_fetcher.fetch_juz_tafsir(juz_number=1)
    # print(juz_tafsir)

    # # --- Fetching Tafsir for the Entire Quran ---
    # # Using the Surah-based API (default)
    # quran_tafsir_by_surah = tafsir_fetcher.fetch_quran_tafsir()
    # print(quran_tafsir_by_surah)

    # # Using the Juz-based API
    # quran_tafsir_by_juz = tafsir_fetcher.fetch_quran_tafsir(use_juz_api=True)
    # print(quran_tafsir_by_juz)

    # # --- Options: text_only and show_progress ---
    # # Fetching only the Tafsir text for Surah Al-Fatiha
    # surah_tafsir_text_only = tafsir_fetcher.fetch_surah_tafsir(surah_number=1, text_only=True)
    # print(surah_tafsir_text_only)

    # # Fetching Tafsir for Surah Al-Baqarah (Surah 2) with a progress bar
    # surah_tafsir_with_progress = tafsir_fetcher.fetch_surah_tafsir(surah_number=2, show_progress=True)
    # print(surah_tafsir_with_progress)

    # # --- Using BeautifulSoup for Text Cleaning ---
    # # Instantiate the Tafsir Fetcher with BeautifulSoup enabled
    # tafsir_fetcher_with_bs = QuranTafsirFetcher(use_beautiful_soup=True)

    # # Fetching Tafsir for Surah Al-Fatiha with HTML tags removed
    # surah_tafsir_cleaned = tafsir_fetcher_with_bs.fetch_surah_tafsir(surah_number=1)
    # print(surah_tafsir_cleaned)

    # # --- Fetching the Entire Quran Tafsir using the Ayah API ---
    # # This method fetches Tafsir Ayah by Ayah, which might be slower but more granular
    # entire_quran_tafsir_by_ayah = tafsir_fetcher.fetch_entire_quran_tafsir_by_ayah(show_progress=True)
    # print(entire_quran_tafsir_by_ayah)

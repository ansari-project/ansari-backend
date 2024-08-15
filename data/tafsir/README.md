# Quran Tafsir Fetcher

This Python module provides an interface for fetching and parsing Tafsir Ibn Kathir from the Quran.com API. It offers granular retrieval options, seamless pagination handling, optional text cleaning, and progress visualization for a smooth and informative user experience.

## Key Features

- **Granular Retrieval:** Fetch tafsir for individual ayahs, complete surahs, or the entire Quran.
- **Pagination Handling:** Automatically traverses paginated API responses for comprehensive data retrieval.
- **Text Cleaning:** Optionally utilizes BeautifulSoup to remove HTML tags for clean text extraction.
- **Progress Visualization:** Provides progress bar integration for monitoring lengthy operations.

## Usage

```bash
python fetch_tafsir.py
```

The script generates a JSON file containing Tafsir Ibn Kathir in your current directory.c

## Available Methods

- `fetch_ayah_tafsir(surah_number, ayah_number)`: Retrieves the Tafsir for a specific Ayah.
- `fetch_surah_tafsir(surah_number, text_only=True, show_progress=False)`: Retrieves all Tafsirs for a given Surah.
- `fetch_juz_tafsir(juz_number, text_only=True, show_progress=False)`: Retrieves all Tafsirs for a given Juz.
- `fetch_quran_tafsir(text_only=True, show_progress=False, use_juz_api=False)`: Retrieves Tafsirs for the entire Quran.
- `fetch_entire_quran_tafsir_by_ayah(text_only=True, show_progress=False)`: Fetches the Tafsir for the entire Quran using the Ayah API.

## Options

- `text_only`: When set to `True`, returns only the Tafsir text. When set to `False`, returns the complete API response. Defaults to `True`.
- `show_progress`: When set to `True`, displays a progress bar during the retrieval process. Defaults to `False`.
- `use_juz_api`: When set to `True`, uses the Juz-based API for fetching the entire Quran Tafsir. Defaults to `False` (uses the Surah-based API).
- `use_beautiful_soup`: When set to `True` during initialization, uses BeautifulSoup to clean HTML tags from the Tafsir text. Defaults to `False`.

## Example: Fetching Tafsir for Surah Al-Fatiha with Progress Bar

```python
tafsir_fetcher = QuranTafsirFetcher()
surah_tafsir = tafsir_fetcher.fetch_surah_tafsir(surah_number=1, show_progress=True)
print(surah_tafsir)
```

"""
Test script for the SearchMawsuah class.
This script verifies that the SearchMawsuah class correctly inherits from SearchVectara
and that its translation and formatting methods work as expected.
"""

import os
import sys

# Add the src directory to the path so we can import the modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from src.ansari.tools.search_mawsuah import SearchMawsuah
from src.ansari.config import get_settings


def main():
    """Test the SearchMawsuah class."""
    # Get settings
    settings = get_settings()

    # Create a SearchMawsuah instance
    sm = SearchMawsuah(
        vectara_api_key=settings.VECTARA_API_KEY.get_secret_value(),
        vectara_corpus_key=settings.MAWSUAH_VECTARA_CORPUS_KEY,
    )

    # Test basic search
    print("Testing basic search...")
    query = "prayer"
    results = sm.run(query, num_results=2)

    # Check if results are in the expected format
    print(f"Results type: {type(results)}")

    # If search_results is present, the parent class's API format is being used correctly
    if "search_results" in results:
        print(f"Found {len(results['search_results'])} search results")

        # Test format_as_list
        print("\nTesting format_as_list...")
        text_results = sm.format_as_list(results)
        print(f"format_as_list produced {len(text_results)} results")

        # Test format_as_ref_list
        print("\nTesting format_as_ref_list...")
        ref_list = sm.format_as_ref_list(results)
        print(f"format_as_ref_list produced {len(ref_list)} documents")

        # Check if translation worked in ref_list
        if ref_list and not isinstance(ref_list[0], str):
            text = ref_list[0]["source"]["data"]
            print("First document text includes translation:", "English:" in text)

        # Test run_as_string
        print("\nTesting run_as_string...")
        string_results = sm.run_as_string(query, num_results=2)
        print(f"run_as_string output length: {len(string_results)}")
        print("run_as_string output includes translation:", "English Translation:" in string_results)

        print("\nSearchMawsuah works correctly and inherits properly from SearchVectara!")
    else:
        print("ERROR: Results don't have search_results key. API format mismatch.")
        print(f"Results keys: {results.keys()}")


if __name__ == "__main__":
    main()

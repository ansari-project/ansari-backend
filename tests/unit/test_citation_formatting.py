"""Tests for citation formatting in Quran and Hadith searches."""

import unittest
from unittest.mock import patch, MagicMock
import json

from ansari.tools.search_quran import SearchQuran
from ansari.tools.search_hadith import SearchHadith
from ansari.agents.ansari_claude import AnsariClaude
from ansari.config import Settings


class TestCitationFormatting(unittest.TestCase):
    """Tests to verify that citations are properly formatted without JSON data."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock settings
        self.settings = Settings(
            OPENAI_API_KEY="mock-openai-key",
            ANTHROPIC_API_KEY="mock-anthropic-key",
            KALEMAT_API_KEY="mock-kalemat-key",
            ANTHROPIC_MODEL="claude-3-opus-20240229",
            DEBUG_MODE=True,
        )
        
        # Create mock MessageLogger
        self.message_logger = MagicMock()
        
        # Initialize an AnsariClaude agent with mock settings and logger
        self.agent = AnsariClaude(self.settings, self.message_logger)

    @patch('ansari.tools.search_quran.SearchQuran.run')
    def test_quran_search_sleeplessness_citation_format(self, mock_run):
        """Test that Quran search for 'sleeplessness' doesn't return JSON in citations."""
        # Mock the API response for Quran search
        mock_results = [
            {
                "id": "25:47",
                "text": "وَهُوَ ٱلَّذِى جَعَلَ لَكُمُ ٱلَّيْلَ لِبَاسًا وَٱلنَّوْمَ سُبَاتًا وَجَعَلَ ٱلنَّهَارَ نُشُورًا",
                "en_text": "He is the One Who has made the night for you as a cover, and made sleep for resting, and the day for rising."
            },
            {
                "id": "78:9",
                "text": "وَجَعَلْنَا نَوْمَكُمْ سُبَاتًا",
                "en_text": "and made your sleep for rest,"
            }
        ]
        mock_run.return_value = mock_results
        
        # Create a Quran search tool instance
        quran_tool = SearchQuran(kalimat_api_key="mock-key")
        
        # Get ref_list from the tool
        ref_list = quran_tool.format_as_ref_list(mock_results)
        
        # Check that the data field doesn't contain JSON
        for doc in ref_list:
            self.assertIsInstance(doc, dict)
            self.assertIn("source", doc)
            self.assertIn("data", doc["source"])
            data = doc["source"]["data"]
            
            # Verify data is just text, not JSON
            with self.assertRaises(ValueError):
                # This should raise ValueError since data is not JSON
                json.loads(data)
            
            # Verify data is the Arabic text
            self.assertTrue(
                data == mock_results[0]["text"] or data == mock_results[1]["text"],
                f"Expected data to be Arabic text, but got: {data}"
            )

    @patch('ansari.tools.search_hadith.SearchHadith.run')
    def test_hadith_search_day_of_judgment_citation_format(self, mock_run):
        """Test that Hadith search for 'signs of the day of judgment' doesn't return JSON in citations."""
        # Mock the API response for Hadith search
        mock_results = [
            {
                "id": "1_2_37_50",
                "source_book": "Bukhari",
                "chapter_number": "2",
                "chapter_english": "Belief",
                "section_number": "37",
                "section_english": "The asking of Jibreel about Iman, Islam, Ihsan",
                "hadith_number": "50",
                "ar_text": "عَنْ أَبِي هُرَيْرَةَ، قَالَ كَانَ النَّبِيُّ صلى الله عليه وسلم بَارِزًا يَوْمًا لِلنَّاسِ...",
                "en_text": "Narrated Abu Huraira: One day while the Prophet (ﷺ) was sitting in the company of some people, (The angel) Gabriel came and asked, \"What is faith?\"...",
                "grade_en": "Sahih-Authentic"
            },
            {
                "id": "3_39_1598_4178",
                "source_book": "AbuDaud",
                "chapter_number": "39",
                "chapter_english": "Battles",
                "section_number": "1598",
                "section_english": "Signs of the hour",
                "hadith_number": "4178",
                "ar_text": "قال رسول الله صلى الله عليه وسلم: لا تقوم الساعة حتى تكون عشر آيات...",
                "en_text": "The Messenger of Allah (peace be upon him) said: The last hour will not come or happen until there appear ten signs before it...",
                "grade_en": "Sahih - Authentic"
            }
        ]
        mock_run.return_value = mock_results
        
        # Create a Hadith search tool instance
        hadith_tool = SearchHadith(kalimat_api_key="mock-key")
        
        # Get ref_list from the tool
        ref_list = hadith_tool.format_as_ref_list(mock_results)
        
        # Check that the data field doesn't contain JSON
        for doc in ref_list:
            self.assertIsInstance(doc, dict)
            self.assertIn("source", doc)
            self.assertIn("data", doc["source"])
            data = doc["source"]["data"]
            
            # Verify data is just text, not JSON
            with self.assertRaises(ValueError):
                # This should raise ValueError since data is not JSON
                json.loads(data)
            
            # Verify data is the Arabic text or English text (fallback)
            self.assertTrue(
                data == mock_results[0]["ar_text"] or data == mock_results[1]["ar_text"] or
                data == mock_results[0]["en_text"] or data == mock_results[1]["en_text"],
                f"Expected data to be text, but got: {data}"
            )
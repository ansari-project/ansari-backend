import requests
import logging
from ansari.util.translation import format_multilingual_data

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

KALEMAT_BASE_URL = "https://api.kalimat.dev/search"
TOOL_NAME = "search_hadith"


class SearchHadith:
    def __init__(self, kalimat_api_key):
        self.api_key = kalimat_api_key
        self.base_url = KALEMAT_BASE_URL

    def get_tool_description(self):
        return {
            "type": "function",
            "function": {
                "name": "search_hadith",
                "description": "Search for relevant Hadith narrations based on a specific topic.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Topic or subject matter to search for in Hadith collections",
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    def get_tool_name(self):
        return TOOL_NAME

    def run(self, query: str, num_results: int = 10):
        headers = {"x-api-key": self.api_key}
        payload = {
            "query": query,
            "numResults": num_results,
            "indexes": '["sunnah_lk"]',
            "getText": 2,
        }

        response = requests.get(self.base_url, headers=headers, params=payload)

        if response.status_code != 200:
            print(
                f"Query failed with code {response.status_code}, reason {response.reason}, text {response.text}",
            )
            response.raise_for_status()

        return response.json()

    def pp_hadith(self, h):
        en = h["en_text"]
        grade = h["grade_en"].strip()
        if grade:
            grade = f"\nGrade: {grade}\n"
        src = f"Collection: {h['source_book']} Chapter: {h['chapter_number']} Hadith: {h['hadith_number']} LK id: {h['id']}"
        result = f"{src}\n{en}\n{grade}"
        return result

    def format_as_list(self, results):
        """Format raw API results as a list of strings."""
        return [self.pp_hadith(r) for r in results]

    def format_as_ref_list(self, results):
        """Format raw API results as a list of reference documents for Claude."""
        documents = []
        for result in results:
            source_book = result.get("source_book", "")
            chapter = result.get("chapter_number", "")
            chapter_name = result.get("chapter_english", "")
            hadith = result.get("hadith_number", "")
            section_number = result.get("section_number", "")
            section_name = result.get("section_english", "")
            id = result.get("id", "")
            text = result.get("en_text", "")
            ar_text = result.get("ar_text", "")
            grade = result.get("grade_en", "").strip()

            # Create citation title (including grade if available)
            title = (
                f"{source_book} - Chapter {chapter}: {chapter_name}, "
                f"Section {section_number}: {section_name}, Hadith {hadith}, LK id {id}"
            )
            if grade:
                title += f" (Grade: {grade})"

            # Format both Arabic and English texts in multilingual JSON format
            # This is expected by the base_search.py documentation
            text_entries = {}
            if ar_text:
                text_entries["ar"] = ar_text
            if text:
                text_entries["en"] = text
                
            # Format as multilingual JSON data
            doc_text = format_multilingual_data(text_entries)
            
            document = {
                "type": "document",
                "source": {"type": "text", "media_type": "text/plain", "data": doc_text},
                "title": title,
                "context": "Retrieved from hadith collections",
                "citations": {"enabled": True},
            }
            documents.append(document)

        return documents

    def format_as_tool_result(self, results):
        """Format raw API results as a tool result dictionary."""
        formatted_results = []
        for result in results:
            formatted_results.append(
                {
                    "type": "text",
                    "text": f"""
                Hadith: {result.get("en_text", "")} \n\n
                Source: {result.get("source_book", "")}, Hadith {result.get("hadith_number", "")}\n\n
                Grade: {result.get("grade_en", "")}\n
                """,
                }
            )

        return formatted_results

    def run_as_list(self, query: str, num_results: int = 10):
        print(f'Searching hadith for "{query}"')
        results = self.run(query, num_results)
        return self.format_as_list(results)

    def run_as_string(self, query: str, num_results: int = 3):
        results = self.run(query, num_results)
        return "\n".join(self.format_as_list(results))

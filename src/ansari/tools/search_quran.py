import requests
from ansari.ansari_logger import get_logger
from ansari.util.translation import format_multilingual_data

logger = get_logger(__name__)
KALEMAT_BASE_URL = "https://api.kalimat.dev/search"
TOOL_NAME = "search_quran"


class SearchQuran:
    def __init__(self, kalimat_api_key):
        self.api_key = kalimat_api_key
        self.base_url = KALEMAT_BASE_URL

    def get_tool_description(self):
        return {
            "type": "function",
            "function": {
                "name": "search_quran",
                "description": """
                Search and retrieve relevant ayahs based on a specific topic. 
                Returns multiple ayahs when applicable.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": """
                            Topic or subject matter to search for within the Holy Quran.
                            Make this as specific as possible.
                            Do not include the word quran in the request. 

                            Returns results both as tool results and as 
                            references for citations.
                            """,
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
            "getText": 1,  # 1 is the Qur'an
        }

        response = requests.get(self.base_url, headers=headers, params=payload)

        if response.status_code != 200:
            logger.error(
                f"Query failed with code {response.status_code}, reason {response.reason}, text {response.text}",
            )
            response.raise_for_status()

        # Return the JSON response directly as in the original implementation
        return response.json()

    def pp_ayah(self, ayah):
        # Added debug logging to understand the ayah structure
        logger.debug(f"Ayah data type: {type(ayah)}")
        logger.debug(f"Ayah content: {str(ayah)[:200]}")

        # Handle if ayah is not a dictionary
        if not isinstance(ayah, dict):
            logger.error(f"Expected ayah to be a dict but got {type(ayah)}")
            return f"Error: Invalid ayah format - {str(ayah)[:100]}..."

        try:
            ayah_num = ayah["id"]
            ayah_ar = ayah.get("text", "Not retrieved")
            ayah_en = ayah.get("en_text", "Not retrieved")
            result = f"Ayah: {ayah_num}\nArabic Text: {ayah_ar}\n\nEnglish Text: {ayah_en}\n\n"
            return result
        except Exception as e:
            logger.error(f"Error formatting ayah: {str(e)}")
            logger.error(f"Problematic ayah: {str(ayah)}")
            return f"Error processing ayah: {str(e)}"

    def format_as_list(self, results):
        """Format raw API results as a list of strings."""
        return [self.pp_ayah(r) for r in results]

    def format_as_ref_list(self, results):
        """Format raw API results as a list of document objects for Claude.

        Args:
            results: Raw API results

        Returns:
            List of document objects formatted for Claude
        """
        documents = []
        for result in results:
            id = result.get("id", "")
            arabic = result.get("text", "")
            english = result.get("en_text", "")

            # Create citation title
            title = f"Quran {id}"

            # Format both Arabic and English texts in multilingual JSON format
            # This is expected by the base_search.py documentation
            text_entries = {}
            if arabic:
                text_entries["ar"] = arabic
            if english:
                text_entries["en"] = english
                
            # Format as multilingual JSON data
            doc_text = format_multilingual_data(text_entries)
            
            documents.append(
                {
                    "type": "document",
                    "source": {"type": "text", "media_type": "text/plain", "data": doc_text},
                    "title": title,
                    "context": "Retrieved from the Holy Quran",
                    "citations": {"enabled": True},
                }
            )

        return documents

    def format_as_tool_result(self, results):
        """Format raw API results as a tool result dictionary."""
        formatted_results = []
        for result in results:
            formatted_results.append(
                {
                    "type": "text",
                    "text": f"""
                Arabic text: {result.get("text", "")} \n\n
                English text: {result.get("en_text", "")}\n\n
                Ayah number: {result.get("id", "")}\n
                """,
                }
            )

        return formatted_results

    def run_as_list(self, query: str, num_results: int = 10):
        logger.info(f'Searching quran for "{query}"')
        results = self.run(query, num_results)
        logger.debug(f"Results from API: {type(results)}")
        try:
            # Use the direct approach from the original implementation
            formatted_results = []
            for r in results:
                ayah_str = self.pp_ayah(r)
                formatted_results.append(ayah_str)
            return formatted_results
        except Exception as e:
            import traceback

            logger.error(f"Error formatting results: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            logger.error(f"Results that caused error: {results}")
            return [f"Error processing results: {str(e)} - {traceback.format_exc()}"]

    def run_as_string(self, query: str, num_results: int = 10):
        results = self.run(query, num_results)
        try:
            return "\n".join([self.pp_ayah(r) for r in results])
        except Exception as e:
            logger.error(f"Error formatting results as string: {str(e)}")
            return f"Error processing results: {str(e)}"

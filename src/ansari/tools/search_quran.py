import requests

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
                }
            }
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
            print(
                f"Query failed with code {response.status_code}, reason {response.reason}, text {response.text}",
            )
            response.raise_for_status()

        return response.json()

    def pp_ayah(self, ayah):
        ayah_num = ayah["id"]
        ayah_ar = ayah.get("text", "Not retrieved")
        ayah_en = ayah.get("en_text", "Not retrieved")
        result = f"Ayah: {ayah_num}\nArabic Text: {ayah_ar}\nEnglish Text: {ayah_en}\n"
        return result

    def format_as_list(self, results):
        """Format raw API results as a list of strings."""
        return [self.pp_ayah(r) for r in results]

    def format_as_tool_result(self, results):
        """Format raw API results as a tool result dictionary."""
        formatted_results = []
        for result in results:
            formatted_results.append({
                "type": "text",
                "text": f"""
                Arabic text: {result.get("text", "")} \n\n
                English text: {result.get("en_text", "")}\n\n
                Ayah number: {result.get("id", "")}\n
                """
            })
        
        return formatted_results

    def format_as_reference_list(self, results):
        """Format raw API results as a list of reference documents for Claude."""
        documents = []
        for result in results:
            id = result.get("id", "")
            arabic = result.get("text", "")
            english = result.get("en_text", "")
            
            # Create citation title
            title = f"Quran {id}"
            
            # Combine Arabic and English text
            text = f"Arabic: {arabic}\nEnglish: {english}"
            
            documents.append({
                "type": "document",
                "source": {
                    "type": "text",
                    "media_type": "text/plain",
                    "data": text
                },
                "title": title,
                "context": "Retrieved from the Holy Quran",
                "citations": {"enabled": True}
            })
            
        return documents

    def run_as_list(self, query: str, num_results: int = 10):
        print(f'Searching quran for "{query}"')
        results = self.run(query, num_results)
        return self.format_as_list(results)

    def run_as_string(self, query: str, num_results: int = 10):
        results = self.run(query, num_results)
        return "\n".join(self.format_as_list(results))

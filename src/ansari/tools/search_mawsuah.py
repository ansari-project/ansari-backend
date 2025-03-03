import json
import logging
import os
import requests
from typing import List, Dict, Any, Optional
from anthropic import Anthropic

VECTARA_BASE_URL = "https://api.vectara.io:443/v1/query"
TOOL_NAME = "search_mawsuah"

# Set up logging
logger = logging.getLogger(__name__)


class SearchMawsuah:
    def __init__(self, vectara_auth_token, vectara_customer_id, vectara_corpus_id, anthropic_api_key=None):
        self.auth_token = vectara_auth_token
        self.customer_id = vectara_customer_id
        self.corpus_id = vectara_corpus_id
        self.base_url = VECTARA_BASE_URL
        self.anthropic_api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")

    def get_tool_description(self):
        return {
            "type": "function",
            "function": {
                "name": TOOL_NAME,
                "description": (
                    "Queries an encyclopedia of Islamic jurisprudence (fiqh) for relevant rulings. "
                    "You call this tool when you need to provide information about Islamic law. "
                    "Regardless of the language used in the original conversation, you will translate "
                    "the query into Arabic before searching the encyclopedia. The tool returns a list "
                    "of **potentially** relevant matches, which may include multiple paragraphs."
                ),
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The topic to search for in the fiqh encyclopedia. "
                        "You will translate this query into Arabic.",
                    },
                },
                "required": ["query"],
            },
        }

    def get_tool_name(self):
        return TOOL_NAME

    def run(self, query: str, num_results: int = 5):
        print(f'Searching al-mawsuah for "{query}"')
        # Headers
        headers = {
            "x-api-key": self.auth_token,
            "customer-id": self.customer_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        data = {
            "query": [
                {
                    "query": query,
                    "queryContext": "",
                    "start": 0,
                    "numResults": num_results,
                    "contextConfig": {
                        "charsBefore": 0,
                        "charsAfter": 0,
                        "sentencesBefore": 2,
                        "sentencesAfter": 2,
                        "startTag": "<match>",
                        "endTag": "</match>",
                    },
                    "corpusKey": [
                        {
                            "customerId": self.customer_id,
                            "corpusId": self.corpus_id,
                            "semantics": 0,
                            "metadataFilter": "",
                            "lexicalInterpolationConfig": {"lambda": 0.1},
                            "dim": [],
                        },
                    ],
                    "summary": [],
                },
            ],
        }

        response = requests.post(self.base_url, headers=headers, data=json.dumps(data))

        if response.status_code != 200:
            print(
                f"Query failed with code {response.status_code}, reason {response.reason}, text {response.text}",
            )
            response.raise_for_status()

        return response.json()

    def pp_response(self, response):
        results = []
        for response_item in response["responseSet"]:
            for result in response_item["response"]:
                results.append(result["text"])
        return results

    def translate_text(self, arabic_text: str) -> str:
        """
        Translate Arabic text to English using Anthropic's Claude API.
        
        Args:
            arabic_text: The Arabic text to translate
            
        Returns:
            The English translation of the text
        """
        if not self.anthropic_api_key:
            logger.warning("No Anthropic API key provided, skipping translation")
            return ""
            
        try:
            client = Anthropic(api_key=self.anthropic_api_key)
            response = client.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=1000,
                system="You are a translator specializing in Arabic to English translation. Translate the provided text accurately and fluently, preserving the meaning, tone, and context.",
                messages=[{"role": "user", "content": f"Translate this Arabic text to English: {arabic_text}"}]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return ""

    def format_as_ref_list(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Format raw API results as a list of reference documents for Claude.
        Each reference will include both the original Arabic text and its English translation.
        
        Args:
            response: The raw API response from Vectara
            
        Returns:
            A list of reference documents formatted for Claude with Arabic and English text
        """
        if not response.get("responseSet"):
            return ["No results found."]
            
        documents = []
        for response_item in response.get("responseSet", []):
            for i, result in enumerate(response_item.get("response", [])):
                # Get the Arabic text
                arabic_text = result.get("text", "")
                
                # Get English translation
                english_translation = self.translate_text(arabic_text)
                
                # Create citation title and combined text
                title = f"Encyclopedia of Islamic Jurisprudence, Entry {i+1}"
                
                # Combine Arabic and English text
                combined_text = f"Arabic: {arabic_text}\n\nEnglish: {english_translation}" if english_translation else arabic_text
                
                documents.append({
                    "type": "document",
                    "source": {
                        "type": "text",
                        "media_type": "text/plain",
                        "data": combined_text
                    },
                    "title": title,
                    "context": "Retrieved from Encyclopedia of Islamic Jurisprudence",
                    "citations": {"enabled": True}
                })
                
        return documents

    def format_as_tool_result(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format raw API results as a tool result dictionary for Claude.
        
        Args:
            response: The raw API response from Vectara
            
        Returns:
            A tool result dictionary with formatted results
        """
        if not response.get("responseSet") or not response["responseSet"][0].get("response"):
            return {
                "type": "text",
                "text": "No results found."
            }
            
        items = []
        for response_item in response.get("responseSet", []):
            for result in response_item.get("response", []):
                arabic_text = result.get("text", "")
                english_translation = self.translate_text(arabic_text)
                
                formatted_text = f"Arabic Text: {arabic_text}\n\n"
                if english_translation:
                    formatted_text += f"English Translation: {english_translation}\n\n"
                
                items.append({
                    "type": "text",
                    "text": formatted_text
                })
        
        return {
            "type": "array",
            "items": items
        }

    def format_tool_response(self, response: Dict[str, Any]) -> str:
        """
        Format the final tool response as a string.
        
        Args:
            response: The raw API response from Vectara
            
        Returns:
            A string message about the search results
        """
        if not response.get("responseSet") or not response["responseSet"][0].get("response"):
            return "No results found for the query in the Encyclopedia of Islamic Jurisprudence."
            
        count = 0
        for response_item in response.get("responseSet", []):
            count += len(response_item.get("response", []))
            
        return f"Found {count} relevant results from the Encyclopedia of Islamic Jurisprudence. Please see the included reference list for details."

    def run_as_list(self, query: str, num_results: int = 10):
        return self.pp_response(self.run(query, num_results))

    def run_as_json(self, query: str, num_results: int = 10):
        return {"matches": self.pp_response(self.run(query, num_results))}
        
    def run_as_string(self, query: str, num_results: int = 10) -> str:
        """Return results as a human-readable string with both Arabic and English."""
        response = self.run(query, num_results)
        
        if not response.get("responseSet") or not response["responseSet"][0].get("response"):
            return "No results found."
            
        results = []
        for response_item in response.get("responseSet", []):
            for i, result in enumerate(response_item.get("response", [])):
                arabic_text = result.get("text", "")
                english_translation = self.translate_text(arabic_text)
                
                entry = f"Entry {i+1}:\n"
                entry += f"Arabic Text: {arabic_text}\n"
                if english_translation:
                    entry += f"English Translation: {english_translation}\n"
                
                results.append(entry)
                
        return "\n\n".join(results)

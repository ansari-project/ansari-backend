import json
import logging
import os
from typing import Dict, List, Any
from anthropic import Anthropic
from ansari.tools.search_vectara import SearchVectara

TOOL_NAME = "search_mawsuah"

# Set up logging
logger = logging.getLogger(__name__)


class SearchMawsuah(SearchVectara):
    def __init__(self, vectara_api_key, vectara_corpus_key):
        # Initialize the SearchVectara parent with the necessary parameters
        super().__init__(
            vectara_api_key=vectara_api_key,
            vectara_corpus_key=vectara_corpus_key,
            fn_name=TOOL_NAME,
            fn_description=(
                "Queries an encyclopedia of Islamic jurisprudence (fiqh) for relevant rulings. "
                "You call this tool when you need to provide information about Islamic law. "
                "Regardless of the language used in the original conversation, you will translate "
                "the query into Arabic before searching the encyclopedia. The tool returns a list "
                "of **potentially** relevant matches, which may include multiple paragraphs."
            ),
            params=[
                {
                    "name": "query",
                    "type": "string",
                    "description": "The topic to search for in the fiqh encyclopedia. "
                    "You will translate this query into Arabic.",
                }
            ],
            required_params=["query"]
        )
        
        # Get Anthropic API key from environment
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")

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
        # Get base documents from parent class
        documents = super().format_as_ref_list(response)
        
        if not documents:
            return ["No results found."]
            
        # Enhance each document with a translation
        for i, doc in enumerate(documents):
            if isinstance(doc, str):
                continue
                
            # Get the Arabic text from the document
            arabic_text = doc["source"]["data"]
            
            # Get English translation
            english_translation = self.translate_text(arabic_text)
            
            # Combine Arabic and English text
            combined_text = f"Arabic: {arabic_text}\n\nEnglish: {english_translation}" if english_translation else arabic_text
            
            # Update the document with combined text
            doc["source"]["data"] = combined_text
            doc["title"] = f"Encyclopedia of Islamic Jurisprudence, Entry {i+1}"
                
        return documents

    def format_as_tool_result(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format raw API results as a tool result dictionary for Claude.
        
        Args:
            response: The raw API response from Vectara
            
        Returns:
            A tool result dictionary with formatted results
        """
        # Get base tool result from parent class
        result = super().format_as_tool_result(response)
        
        # If no results were found, return as is
        if not result.get("results", []):
            return {
                "type": "text",
                "text": "No results found."
            }
            
        # Add translations to each result
        items = []
        for entry in result.get("results", []):
            arabic_text = entry.get("text", "")
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

    def run_as_string(self, query: str, num_results: int = 10, **kwargs) -> str:
        """Return results as a human-readable string with both Arabic and English."""
        # Get the response using the parent's run method
        response = self.run(query, num_results, **kwargs)
        
        # Handle no results case
        if not response.get("search_results"):
            return "No results found."
            
        # Process results
        results = []
        for i, result in enumerate(response.get("search_results", [])):
            arabic_text = result.get("text", "")
            english_translation = self.translate_text(arabic_text)
            
            entry = f"Entry {i+1}:\n"
            entry += f"Arabic Text: {arabic_text}\n"
            if english_translation:
                entry += f"English Translation: {english_translation}\n"
            
            results.append(entry)
                
        return "\n\n".join(results)

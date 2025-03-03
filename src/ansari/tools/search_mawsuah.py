import logging
import asyncio
from typing import Dict, List, Any
from ansari.tools.search_vectara import SearchVectara
from ansari.util.translation import translate_text, translate_texts_parallel

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
        
        # Extract Arabic texts from documents that aren't strings
        arabic_texts = []
        valid_doc_indices = []
        
        for i, doc in enumerate(documents):
            if isinstance(doc, str):
                continue
                
            arabic_texts.append(doc["source"]["data"])
            valid_doc_indices.append(i)
        
        # Translate all texts in parallel
        english_translations = asyncio.run(translate_texts_parallel(arabic_texts, "en", "ar"))
        
        # Update documents with translations
        for idx, trans_idx in enumerate(valid_doc_indices):
            doc = documents[trans_idx]
            arabic_text = arabic_texts[idx]
            english_translation = english_translations[idx]
            
            # Combine Arabic and English text
            combined_text = f"Arabic: {arabic_text}\n\nEnglish: {english_translation}"
            
            # Update the document with combined text
            doc["source"]["data"] = combined_text
            doc["title"] = f"Encyclopedia of Islamic Jurisprudence"
                
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
        
        # Extract all Arabic texts from results
        entries = result.get("results", [])
        arabic_texts = [entry.get("text", "") for entry in entries]
        
        # Translate all texts in parallel
        english_translations = asyncio.run(translate_texts_parallel(arabic_texts, "en", "ar"))
        
        # Add translations to each result
        items = []
        for i, entry in enumerate(entries):
            arabic_text = arabic_texts[i]
            english_translation = english_translations[i]
            
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
        
        # Extract all Arabic texts from results
        search_results = response.get("search_results", [])
        arabic_texts = [result.get("text", "") for result in search_results]
        
        # Translate all texts in parallel
        english_translations = asyncio.run(translate_texts_parallel(arabic_texts, "en", "ar"))
        
        # Process results
        results = []
        for i, result in enumerate(search_results):
            arabic_text = arabic_texts[i]
            english_translation = english_translations[i]
            
            entry = f"Entry {i+1}:\n"
            entry += f"Arabic Text: {arabic_text}\n"
            if english_translation:
                entry += f"English Translation: {english_translation}\n"
            
            results.append(entry)
                
        return "\n\n".join(results)

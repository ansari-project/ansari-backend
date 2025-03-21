import logging
from typing import Dict, List, Any
from ansari.tools.search_vectara import SearchVectara
from ansari.util.translation import format_multilingual_data

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
            required_params=["query"],
        )

    def format_as_ref_list(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Format raw API results as a list of reference documents for Claude.
        Each reference will include only the original Arabic text for efficiency.
        The English translation will be added later only for the parts that are cited.

        Args:
            response: The raw API response from Vectara

        Returns:
            A list of reference documents formatted for Claude with Arabic text
        """
        # Get base documents from parent class
        documents = super().format_as_ref_list(response)

        if not documents:
            return ["No results found."]

        # Update documents with just Arabic text and citation support
        for doc in documents:
            if isinstance(doc, str):
                continue

            # Keep only the Arabic text and remove HTML tags
            text = doc["source"]["data"]
            text = text.replace("<em>", "").replace("</em>", "")

            # Convert to multilingual format (Arabic only)
            # Note: Mawsuah only returns results in Arabic, so we only have Arabic text here.
            # The English translation will be added later by AnsariClaude when a citation is actually used.
            doc["source"]["data"] = format_multilingual_data({"ar": text})
            doc["title"] = "Encyclopedia of Islamic Jurisprudence"
            doc["citations"] = {"enabled": True}

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
            return {"type": "text", "text": "No results found."}

        return {"type": "text", "text": "Please see the references below."}

    def run_as_string(self, query: str, num_results: int = 10, **kwargs) -> str:
        """Return results as a human-readable string with Arabic text only."""
        # Get the response using the parent's run method
        response = self.run(query, num_results, **kwargs)

        # Handle no results case
        if not response.get("search_results"):
            return "No results found."

        # Process results
        results = []
        for i, result in enumerate(response.get("search_results", [])):
            arabic_text = result.get("text", "").replace("<em>", "").replace("</em>", "")

            entry = f"Entry {i + 1}:\n"
            entry += f"Arabic Text: {arabic_text}\n"

            results.append(entry)

        return "\n\n".join(results)

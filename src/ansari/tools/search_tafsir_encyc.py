from ansari.tools.search_usul import SearchUsul
from ansari.config import get_settings
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)
settings = get_settings()


class SearchTafsirEncyc(SearchUsul):
    """Search tool for the Encyclopedia of Quranic Interpretation Based on Narrations (موسوعة التفسير بالمأثور).

    This tool allows searching within the Encyclopedia of Quranic Interpretation Based on Narrations,
    a comprehensive collection of Quranic exegesis based on traditional narrations,
    using the Usul.ai API.
    """

    def __init__(self, api_token: str = None):
        """Initialize the search tool for the Encyclopedia of Quranic Interpretation.

        Args:
            api_token: Optional API authentication token. If not provided, uses the token from config.
        """
        token = api_token or settings.USUL_API_TOKEN.get_secret_value()
        super().__init__(
            api_token=token,
            book_id=settings.TAFSIR_ENCYC_BOOK_ID,
            version_id=settings.TAFSIR_ENCYC_VERSION_ID,
            tool_name=settings.TAFSIR_ENCYC_TOOL_NAME,
        )

    def get_tool_description(self):
        """Override the base tool description to provide encyclopedia-specific details."""
        base_description = super().get_tool_description()

        # Update the description to be specific to the Tafsir Encyclopedia
        function_dict = base_description["function"]
        function_dict["description"] = """
        Search and retrieve relevant passages from the Encyclopedia of Quranic Interpretation Based on Narrations 
        (موسوعة التفسير بالمأثور), a comprehensive collection of Quranic commentary 
        derived from traditional sources and narrations.
        Returns multiple passages when applicable.
        """

        # Update the query description
        function_dict["parameters"]["properties"]["query"]["description"] = """
        Topic, verse, or subject matter to search for within the Encyclopedia of Quranic Interpretation
        Based on Narrations. Make this as specific as possible.
        Can be in any language, but Arabic queries may yield better results.
        
        Returns results both as tool results and as references for citations.
        """

        return base_description
        
    def format_as_ref_list(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format raw results as a list of reference objects for the tafsir encyclopedia.
        
        This implementation returns a list of structured objects rather than strings.

        Args:
            results: Raw results from run()

        Returns:
            List of formatted reference objects
        """
        formatted_results = []

        # Check for empty results in different ways:
        # 1. results is None or empty dict
        # 2. "results" key doesn't exist
        # 3. "results" key exists but is an empty list
        if not results or "results" not in results or not results.get("results", []):
            return [{"message": "No results found."}]

        for result in results.get("results", []):
            # Initialize the reference object with default values
            ref_obj = {
                "id": "Unknown",
                "page": "Unknown",
                "volume": "",
                "text": "",
                "chapters": [],
                "source": "Encyclopedia of Quranic Interpretation Based on Narrations"
            }
            
            # Handle the API response structure
            if "node" in result:
                node = result["node"]
                ref_obj["text"] = node.get("text", "")

                # Extract node ID and page info from metadata if available
                if "metadata" in node:
                    metadata = node["metadata"]
                    book_id = metadata.get("bookId", "")
                    ref_obj["id"] = f"{book_id}" if book_id else "Unknown"

                    # Extract page information
                    if "pages" in metadata and len(metadata["pages"]) > 0:
                        page = metadata["pages"][0]
                        ref_obj["page"] = page.get("page", "Unknown")
                        ref_obj["volume"] = page.get("volume", "")

                    # Extract chapter information
                    if "chapters" in metadata and len(metadata["chapters"]) > 0:
                        for chapter in metadata["chapters"]:
                            chapter_title = chapter.get("title", "")
                            if chapter_title:
                                ref_obj["chapters"].append({"title": chapter_title})
            else:
                # Fallback to original structure if "node" is not present
                ref_obj["text"] = result.get("text", "")
                ref_obj["id"] = result.get("nodeId", "Unknown")
                ref_obj["page"] = result.get("page", "Unknown")

                if "chapter" in result:
                    chapter_title = result["chapter"].get("title", "")
                    if chapter_title:
                        ref_obj["chapters"].append({"title": chapter_title})

            formatted_results.append(ref_obj)

        # If after processing all results we still have an empty list,
        # return a message object
        if not formatted_results:
            return [{"message": "No results found."}]

        return formatted_results
    
    def _ref_object_to_string(self, ref_obj: Dict[str, Any]) -> str:
        """Convert a reference object to a string representation.
        
        Args:
            ref_obj: A reference object
            
        Returns:
            String representation of the reference
        """
        if "message" in ref_obj:
            return ref_obj["message"]
            
        # Start with ID and page/volume
        result = f"Node ID: {ref_obj['id']}\n"
        
        if ref_obj.get("volume"):
            result += f"Page: {ref_obj['page']} (Vol: {ref_obj['volume']})\n"
        else:
            result += f"Page: {ref_obj['page']}\n"
            
        # Add chapters if available
        if ref_obj.get("chapters"):
            chapters_text = []
            for chapter in ref_obj["chapters"]:
                if chapter.get("title"):
                    chapters_text.append(chapter["title"])
            
            if chapters_text:
                result += f"Chapter: {', '.join(chapters_text)}\n"
        
        # Add the main text
        result += f"Text: {ref_obj['text']}\n"
        
        return result
        
    def run_as_string(self, query: str, limit: int = 10, page: int = 1, include_chapters: bool = True) -> str:
        """Run search and return results as a single string.

        Args:
            query: The search query
            limit: Maximum number of results
            page: Page number for pagination
            include_chapters: Whether to include chapter details

        Returns:
            String of formatted results
        """
        results = self.run(query, limit, page, include_chapters)
        ref_objects = self.format_as_ref_list(results)
        
        # Convert each reference object to a string
        string_results = [self._ref_object_to_string(ref_obj) for ref_obj in ref_objects]
        
        return "\n".join(string_results)
        
    def format_as_tool_result(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Format raw results as a tool result for Claude based on structured references.

        Args:
            results: Raw results from run()

        Returns:
            Dict containing formatted results for Claude
        """
        formatted_refs = self.format_as_ref_list(results)
        
        # Check if we have actual results or just a "no results" message
        if len(formatted_refs) == 1 and "message" in formatted_refs[0]:
            return {"type": "text", "text": formatted_refs[0]["message"]}
            
        # Otherwise, convert each reference to a tool result item
        formatted_items = []
        for ref in formatted_refs:
            # Create a text representation for the tool result
            text = self._ref_object_to_string(ref)
            
            formatted_items.append({
                "type": "text",
                "text": text
            })
            
        return {"type": "array", "items": formatted_items}
        
    def format_tool_response(self, results: Dict[str, Any]) -> str:
        """Format a message about the results for tool response.
        
        Args:
            results: Raw results from run()
            
        Returns:
            A message describing the results
        """
        if not results or "results" not in results or not results.get("results", []):
            return "No results found for your query in the Encyclopedia of Quranic Interpretation."
            
        count = len(results.get("results", []))
        return f"Found {count} relevant passage(s) in the Encyclopedia of Quranic Interpretation. Please see the included reference list for details."

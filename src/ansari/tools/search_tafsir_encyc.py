from ansari.tools.search_usul import SearchUsul
from ansari.config import get_settings
from typing import Dict, Any, List
from ansari.ansari_logger import get_logger

logger = get_logger(__name__)
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
        # We'll create a completely new description rather than inheriting from super()
        return {
            "type": "function",
            "function": {
                "name": self.get_tool_name(),
                "description": """
                Search and retrieve relevant passages from the Encyclopedia of Quranic Interpretation Based on Narrations 
                (موسوعة التفسير بالمأثور), a comprehensive collection of Quranic commentary 
                derived from traditional sources and narrations.
                Returns multiple passages when applicable.
                """,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": """
                            Topic, verse, or subject matter to search for within the Encyclopedia of Quranic Interpretation
                            Based on Narrations. Make this as specific as possible.
                            Can be in any language, but Arabic queries may yield better results.
                            
                            Returns results both as tool results and as references for citations.
                            """,
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    def format_as_list(self, results: Dict[str, Any]) -> List[str]:
        """Format raw results as a list of strings.

        Args:
            results: Raw results from run()

        Returns:
            List of strings formatted for search results
        """
        # Check for empty results in different ways:
        if not results or "results" not in results or not results.get("results", []):
            return ["No results found."]

        formatted_results = []
        for result in results.get("results", []):
            # Extract data from the result
            if "node" in result:
                node = result["node"]
                text = node.get("text", "")
                node_id = "Unknown"
                page_info = "Unknown"
                volume_info = ""
                chapter_info = ""

                # Extract metadata if available
                if "metadata" in node:
                    metadata = node["metadata"]
                    node_id = metadata.get("bookId", "Unknown")

                    # Extract page and volume information
                    if "pages" in metadata and len(metadata["pages"]) > 0:
                        page = metadata["pages"][0]
                        page_info = page.get("page", "Unknown")
                        volume_info = page.get("volume", "")

                    # Extract chapter information
                    if "chapters" in metadata and len(metadata["chapters"]) > 0:
                        chapter = metadata["chapters"][0]
                        chapter_info = chapter.get("title", "")
            else:
                # Fallback to original structure if "node" is not present
                text = result.get("text", "")
                node_id = result.get("nodeId", "Unknown")
                page_info = result.get("page", "Unknown")
                volume_info = ""

                if "chapter" in result:
                    chapter_info = result["chapter"].get("title", "")
                else:
                    chapter_info = ""

            # Create formatted string with available information
            parts = ["Encyclopedia of Quranic Interpretation"]
            if volume_info:
                parts.append(f"Volume: {volume_info}")
            if page_info:
                parts.append(f"Page: {page_info}")
            if node_id:
                parts.append(f"ID: {node_id}")

            header = ", ".join(parts)

            if chapter_info:
                formatted_text = f"{header}\nChapter: {chapter_info}\n\n{text}"
            else:
                formatted_text = f"{header}\n\n{text}"

            formatted_results.append(formatted_text)

        return formatted_results if formatted_results else ["No results found."]

    def format_as_ref_list(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format raw results as a list of reference documents for Claude.

        Args:
            results: Raw results from run()

        Returns:
            List of document objects formatted for Claude
        """
        # Check for empty results in different ways:
        if not results or "results" not in results or not results.get("results", []):
            return ["No results found."]

        documents = []
        for result in results.get("results", []):
            # Extract score if available
            score = result.get("score", None)

            # Extract data from the result
            if "node" in result:
                node = result["node"]
                text = node.get("text", "")
                page_info = "Unknown"
                volume_info = ""
                chapter_info = ""

                # Extract metadata if available
                if "metadata" in node:
                    metadata = node["metadata"]
                    metadata.get("bookId", "Unknown")

                    # Extract page and volume information
                    if "pages" in metadata and len(metadata["pages"]) > 0:
                        page = metadata["pages"][0]
                        page_info = page.get("page", "Unknown")
                        volume_info = page.get("volume", "")

                    # Extract chapter information
                    if "chapters" in metadata and len(metadata["chapters"]) > 0:
                        chapter = metadata["chapters"][0]
                        chapter_info = chapter.get("title", "")
            else:
                # Fallback to original structure if "node" is not present
                text = result.get("text", "")
                result.get("nodeId", "Unknown")
                page_info = result.get("page", "Unknown")
                volume_info = ""

                if "chapter" in result:
                    chapter_info = result["chapter"].get("title", "")
                else:
                    chapter_info = ""

            # Create citation title with available information
            title_parts = []
            title_parts.append("Encyclopedia of Quranic Interpretation")
            if volume_info:
                title_parts.append(f"Volume {volume_info}")
            if page_info and page_info != "Unknown":
                title_parts.append(f"Page {page_info}")
            # Add chapter info to the title if available
            if chapter_info:
                title_parts.append(f"Chapter: {chapter_info}")

            title = ", ".join(title_parts)

            # Content is just the text
            data = text

            # Create the context string including relevance score if available
            context = "Retrieved from the Encyclopedia of Quranic Interpretation Based on Narrations"
            if score is not None:
                context += f" (Relevance score: {score:.2f})"

            # Create the document object
            documents.append(
                {
                    "type": "document",
                    "source": {"type": "text", "media_type": "text/plain", "data": data},
                    "title": title,
                    "context": context,
                    "citations": {"enabled": True},
                }
            )

        return documents if documents else ["No results found."]

    def _ref_object_to_string(self, ref_obj: Dict[str, Any]) -> str:
        """Convert a reference object to a string representation.

        Args:
            ref_obj: A reference object

        Returns:
            String representation of the reference
        """
        if isinstance(ref_obj, str):
            return ref_obj

        if "type" not in ref_obj or ref_obj["type"] != "document":
            # Handle old format or unexpected format
            return str(ref_obj)

        # Extract data from the document object
        title = ref_obj.get("title", "")
        data = ""
        if "source" in ref_obj and "data" in ref_obj["source"]:
            data = ref_obj["source"]["data"]

        # Format as string
        result = f"Node ID: {title}\n"
        result += f"Text: {data}\n"

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
        if len(formatted_refs) == 1 and isinstance(formatted_refs[0], str):
            return {"type": "text", "text": formatted_refs[0]}

        # Otherwise, convert each reference to a tool result item
        formatted_items = []
        for ref in formatted_refs:
            # Create a text representation for the tool result
            text = self._ref_object_to_string(ref)

            formatted_items.append({"type": "text", "text": text})

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
        return (
            f"Found {count} relevant passage(s) in the Encyclopedia of Quranic Interpretation. "
            "Please see the included reference list for details."
        )

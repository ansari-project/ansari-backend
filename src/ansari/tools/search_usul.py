import requests
from typing import Dict, List, Any
from ansari.tools.base_search import BaseSearchTool
from ansari.config import get_settings

settings = get_settings()


class SearchUsul(BaseSearchTool):
    """Base class for searching Islamic texts using the Usul.ai API."""

    def __init__(self, api_token: str, book_id: str, version_id: str, tool_name: str = None):
        """Initialize the Usul.ai search tool.

        Args:
            api_token: The API authentication token
            book_id: The ID of the book to search
            version_id: The version ID of the book
            tool_name: Optional custom tool name (defaults to 'search_usul')
        """
        self.api_token = api_token
        self.book_id = book_id
        self.version_id = version_id
        self.base_url = f"{settings.USUL_BASE_URL}/{book_id}/{version_id}"
        self._tool_name = tool_name or settings.USUL_TOOL_NAME_PREFIX

    def get_tool_name(self) -> str:
        """Get the name of the tool."""
        return self._tool_name

    def get_tool_description(self) -> Dict[str, Any]:
        """Get the tool description in OpenAI function format."""
        return {
            "type": "function",
            "function": {
                "name": self.get_tool_name(),
                "description": """
                Search and retrieve relevant passages from Islamic texts based on a specific topic.
                Returns multiple passages when applicable.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": """
                            Topic or subject matter to search for within Islamic texts.
                            Make this as specific as possible.
                            Can be in any language.
                            
                            Returns results both as tool results and as 
                            references for citations.
                            """,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (1-50). Defaults to 10.",
                        },
                        "page": {
                            "type": "integer",
                            "description": "Page number for paginated results. Defaults to 1.",
                        },
                        "include_chapters": {
                            "type": "boolean",
                            "description": "Whether to include chapter details for each result. Defaults to true.",
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    def run(self, query: str, limit: int = 10, page: int = 1, include_chapters: bool = False) -> Dict[str, Any]:
        """Execute the search and return raw results.

        Args:
            query: The search query in any language
            limit: Maximum number of results (1-50)
            page: Page number for pagination
            include_chapters: Whether to include chapter details

        Returns:
            Dict containing raw search results
        """
        headers = {"Authorization": f"Bearer {self.api_token}"}
        params = {
            "q": query,
            "limit": min(max(1, limit), 50),  # Ensure limit is between 1-50
            "page": max(1, page),  # Ensure page is at least 1
        }

        if include_chapters:
            params["include_chapters"] = "true"

        response = requests.get(self.base_url, headers=headers, params=params)

        if response.status_code != 200:
            print(
                f"Query failed with code {response.status_code}, reason {response.reason}, text {response.text}",
            )
            response.raise_for_status()

        return response.json()

    def format_as_ref_list(self, results: Dict[str, Any]) -> List[str]:
        """Format raw results as a list of reference strings.

        Args:
            results: Raw results from run()

        Returns:
            List of formatted reference strings
        """
        formatted_results = []

        # Check for empty results in different ways:
        # 1. results is None or empty dict
        # 2. "results" key doesn't exist
        # 3. "results" key exists but is an empty list
        if not results or "results" not in results or not results.get("results", []):
            return ["No results found."]

        for result in results.get("results", []):
            # Handle the new API response structure
            if "node" in result:
                node = result["node"]
                text = node.get("text", "")

                # Extract node ID and page info from metadata if available
                page_info = "Unknown"
                chapter_info = ""

                if "metadata" in node:
                    metadata = node["metadata"]

                    # Extract page information
                    if "pages" in metadata and len(metadata["pages"]) > 0:
                        page = metadata["pages"][0]
                        page_num = page.get("page", "")
                        volume = page.get("volume", "")
                        page_info = f"{page_num}" + (f" (Vol: {volume})" if volume else "")

                    # Extract chapter information
                    if "chapters" in metadata and len(metadata["chapters"]) > 0:
                        chapter = metadata["chapters"][0]
                        chapter_title = chapter.get("title", "")
                        chapter_info = f"\nChapter: {chapter_title}"
            else:
                # Fallback to original structure if "node" is not present
                text = result.get("text", "")
                page_info = result.get("page", "")
                chapter_info = ""

                if "chapter" in result:
                    chapter_title = result["chapter"].get("title", "")
                    chapter_info = f"\nChapter: {chapter_title}"

            formatted_results.append(f"Page: {page_info}{chapter_info}\nText: {text}\n")

        # If after processing all results we still have an empty list,
        # return the "No results found" message
        if not formatted_results:
            return ["No results found."]

        return formatted_results

    def format_as_tool_result(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Format raw results as a tool result for Claude.

        Args:
            results: Raw results from run()

        Returns:
            Dict containing formatted results for Claude
        """
        formatted_results = []

        # Check for empty results in different ways:
        # 1. results is None or empty dict
        # 2. "results" key doesn't exist
        # 3. "results" key exists but is an empty list
        if not results or "results" not in results or not results.get("results", []):
            return {"type": "text", "text": "No results found."}

        for result in results.get("results", []):
            # Handle the new API response structure
            if "node" in result:
                node = result["node"]
                text = node.get("text", "")

                # Extract node ID and page info from metadata if available
                node_id = "Unknown"
                page_info = "Unknown"
                chapter_info = ""

                if "metadata" in node:
                    metadata = node["metadata"]
                    book_id = metadata.get("bookId", "")
                    node_id = f"{book_id}" if book_id else "Unknown"

                    # Extract page information
                    if "pages" in metadata and len(metadata["pages"]) > 0:
                        page = metadata["pages"][0]
                        page_num = page.get("page", "")
                        volume = page.get("volume", "")
                        page_info = f"{page_num}" + (f" (Vol: {volume})" if volume else "")

                    # Extract chapter information
                    if "chapters" in metadata and len(metadata["chapters"]) > 0:
                        chapter = metadata["chapters"][0]
                        chapter_title = chapter.get("title", "")
                        chapter_info = f"\nChapter: {chapter_title}"
            else:
                # Fallback to original structure if "node" is not present
                text = result.get("text", "")
                node_id = result.get("nodeId", "")
                page_info = result.get("page", "")
                chapter_info = ""

                if "chapter" in result:
                    chapter_title = result["chapter"].get("title", "")
                    chapter_info = f"\nChapter: {chapter_title}"

            formatted_results.append(
                {
                    "type": "text",
                    "text": f"""
                Text: {text}\n\n
                Node ID: {node_id}\n
                Page: {page_info}{chapter_info}
                """,
                }
            )

        # If after processing all results we still have an empty list,
        # return the "No results found" message
        if not formatted_results:
            return {"type": "text", "text": "No results found."}

        return {"type": "array", "items": formatted_results}

    def run_as_list(self, query: str, limit: int = 10, page: int = 1, include_chapters: bool = True) -> List[str]:
        """Run search and return results as a list of strings.

        Args:
            query: The search query
            limit: Maximum number of results
            page: Page number for pagination
            include_chapters: Whether to include chapter details

        Returns:
            List of formatted result strings
        """
        print(f'Searching Usul.ai for "{query}"')
        results = self.run(query, limit, page, include_chapters)
        return self.format_as_ref_list(results)

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
        return "\n".join(self.format_as_ref_list(results))

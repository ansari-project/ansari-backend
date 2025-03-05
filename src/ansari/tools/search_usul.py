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
                    },
                    "required": ["query"],
                },
            },
        }

    def run(self, query: str, limit: int = 10, include_chapters: bool = True) -> Dict[str, Any]:
        """Execute the search and return raw results, automatically fetching all available pages.

        Args:
            query: The search query in any language
            limit: Maximum number of results per page (1-50)
            include_chapters: Whether to include chapter details (defaults to True)

        Returns:
            Dict containing raw search results with all pages combined
        """
        headers = {"Authorization": f"Bearer {self.api_token}"}
        params = {
            "q": query,
            "limit": min(max(1, limit), 50),  # Ensure limit is between 1-50
            "page": 1,  # Always start with page 1
            "include_chapters": "true" if include_chapters else "false",
        }

        # Get the first page of results
        response = requests.get(self.base_url, headers=headers, params=params)

        if response.status_code != 200:
            print(
                f"Query failed with code {response.status_code}, reason {response.reason}, text {response.text}",
            )
            response.raise_for_status()

        results = response.json()

        # If there's only one page, return the results
        if not results.get("hasNextPage", False):
            return results

        # Otherwise, fetch all remaining pages and merge the results
        all_results = results.get("results", [])
        current_page = results.get("currentPage", 1)
        total_pages = results.get("totalPages", 1)

        # Fetch remaining pages
        while current_page < total_pages:
            current_page += 1
            params["page"] = current_page

            response = requests.get(self.base_url, headers=headers, params=params)

            if response.status_code != 200:
                print(
                    f"Query for page {current_page} failed with code {response.status_code}, reason {response.reason}",
                )
                break

            page_results = response.json()
            all_results.extend(page_results.get("results", []))

        # Create a new result object with just the combined results
        final_results = {"results": all_results, "total": len(all_results)}

        return final_results

    def format_as_ref_list(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format raw results as a list of reference documents for Claude.

        Args:
            results: Raw results from run()

        Returns:
            List of document objects formatted for Claude in the format required by BaseSearchTool
        """
        # Check for empty results in different ways
        if not results or "results" not in results or not results.get("results", []):
            return ["No results found."]

        documents = []
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

            # Create citation title with available information
            title_parts = []
            title_parts.append("Islamic Legal Principles")
            if volume_info:
                title_parts.append(f"Volume {volume_info}")
            if page_info and page_info != "Unknown":
                title_parts.append(f"Page {page_info}")
            if node_id and node_id != "Unknown":
                title_parts.append(f"ID: {node_id}")

            title = ", ".join(title_parts)

            # Add chapter info to the data if available
            if chapter_info:
                data = f"Chapter: {chapter_info}\n\n{text}"
            else:
                data = text

            # Create the document object following BaseSearchTool's required format
            documents.append(
                {
                    "type": "document",
                    "source": {"type": "text", "media_type": "text/plain", "data": data},
                    "title": title,
                    "context": "Retrieved from principles of Islamic jurisprudence (usul al-fiqh)",
                    "citations": {"enabled": True},
                }
            )

        return documents

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

    def run_as_list(self, query: str, limit: int = 10, include_chapters: bool = True) -> List[str]:
        """Run search and return results as a list of strings.

        Args:
            query: The search query
            limit: Maximum number of results per page
            include_chapters: Whether to include chapter details (defaults to True)

        Returns:
            List of formatted result strings
        """
        print(f'Searching Usul.ai for "{query}"')
        results = self.run(query, limit, include_chapters)
        ref_docs = self.format_as_ref_list(results)

        # Convert document objects to strings using the base class helper
        return [self.format_document_as_string(doc) for doc in ref_docs]

    def run_as_string(self, query: str, limit: int = 10, include_chapters: bool = True) -> str:
        """Run search and return results as a single string.

        Args:
            query: The search query
            limit: Maximum number of results per page
            include_chapters: Whether to include chapter details (defaults to True)

        Returns:
            String of formatted results
        """
        results = self.run(query, limit, include_chapters)
        ref_docs = self.format_as_ref_list(results)

        # Format documents as strings using the base class helper and join
        formatted_strings = [self.format_document_as_string(doc) for doc in ref_docs]
        return "\n\n".join(formatted_strings)

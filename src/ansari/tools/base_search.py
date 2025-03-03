from abc import ABC, abstractmethod
from typing import Dict, List, Any, Union


class BaseSearchTool(ABC):
    """Base class for all search tools."""

    @abstractmethod
    def get_tool_name(self) -> str:
        """Get the name of the tool."""
        pass

    @abstractmethod
    def get_tool_description(self) -> Dict[str, Any]:
        """Get the tool description in OpenAI function format."""
        pass

    @abstractmethod
    def run(self, query: str, **kwargs) -> Dict[str, Any]:
        """Execute the search and return raw results.

        Args:
            query: The search query
            **kwargs: Additional search parameters

        Returns:
            Dict containing raw search results
        """
        pass

    @abstractmethod
    def format_as_ref_list(self, results: Dict[str, Any]) -> List[Union[Dict[str, Any], str]]:
        """Format raw results as a list of document dictionaries.

        Args:
            results: Raw results from run()

        Returns:
            List of document dictionaries in the format:
            {
                "type": "document",
                "source": {"type": "text", "media_type": "text/plain", "data": str},
                "title": str,
                "context": str,
                "citations": {"enabled": bool},
                ...
            }
            
            Or a list containing a single string "No results found." if no results.
        """
        pass

    @abstractmethod
    def format_as_tool_result(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Format raw results as a tool result for Claude.

        Args:
            results: Raw results from run()

        Returns:
            Dict containing formatted results for Claude
        """
        pass
        
    def format_document_as_string(self, document: Dict[str, Any]) -> str:
        """Helper method to format a document object as a string.
        
        Args:
            document: A document dictionary as returned by format_as_ref_list
            
        Returns:
            A string representation of the document
        """
        if isinstance(document, str):
            return document
            
        if document.get("type") != "document" or "source" not in document:
            return str(document)
            
        title = document.get("title", "")
        data = document["source"].get("data", "")
        context = document.get("context", "")
        
        result = f"{title}\n"
        if context:
            result += f"Context: {context}\n"
        result += f"{data}"
        
        return result

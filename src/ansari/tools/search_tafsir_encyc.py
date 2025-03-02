from ansari.tools.search_usul import SearchUsul
from ansari.config import get_settings
from typing import Dict, List, Any

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
            tool_name=settings.TAFSIR_ENCYC_TOOL_NAME
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
        

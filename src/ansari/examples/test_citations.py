from dotenv import load_dotenv
import os
import anthropic
from ansari.tools.search_quran import SearchQuran
import sys


def create_quran_document(ayah: dict) -> dict:
    """Convert an ayah to a document format that supports citations."""
    return {
        "type": "document",
        "source": {
            "type": "content",
            "content": [
                {"type": "text", "text": f"Arabic Text: {ayah['text']}"},
                {"type": "text", "text": f"English Text: {ayah['en_text']}"},
            ],
        },
        "title": f"Quran {ayah['id']}",
        "citations": {"enabled": True},
    }


def get_prompt(query: str) -> str:
    return f"""Based on these Quranic verses, please explain the Islamic teachings about {query}. 
    
    Tell me how many verses are below, and how many you actually used. 
    """


def format_response_with_citations(response) -> str:
    """Format the response with numbered citations and a references section."""
    citations = []
    formatted_text = ""

    # First pass: collect citations and build citation map
    citation_map = {}  # Maps doc_title to citation number
    for content in response.content:
        if content.type == "text" and hasattr(content, "citations") and content.citations:
            for citation in content.citations:
                doc_title = citation.document_title
                if doc_title not in citation_map:
                    text = (
                        citation.cited_text.split("English Text:", 1)[1].strip()
                        if "English Text:" in citation.cited_text
                        else citation.cited_text.strip()
                    )
                    citations.append({"doc_title": doc_title, "text": text})
                    citation_map[doc_title] = len(citations)

    # Second pass: format text with citation numbers
    for content in response.content:
        if content.type == "text":
            text = content.text
            if hasattr(content, "citations") and content.citations:
                # Add citation numbers after the text block
                citation_nums = []
                for citation in content.citations:
                    ref_num = citation_map[citation.document_title]
                    citation_nums.append(str(ref_num))
                text += f" [{', '.join(citation_nums)}]"
            formatted_text += text

    # Add references section
    if citations:
        formatted_text += "\n\nReferences:\n"
        for i, citation in enumerate(citations, 1):
            formatted_text += f"[{i}] {citation['doc_title']}: {citation['text']}\n\n"

    return formatted_text


def get_request_params(query: str) -> dict:
    load_dotenv()

    # Get API keys
    kalemat_api_key = os.getenv("KALEMAT_API_KEY")
    if not kalemat_api_key:
        raise ValueError("KALEMAT_API_KEY environment variable not set")

    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    # Initialize clients
    quran_search = SearchQuran(kalemat_api_key)

    # Search for relevant ayahs
    search_results = quran_search.run(query, num_results=15)
    documents = [create_quran_document(ayah) for ayah in search_results]

    # Create message with documents and prompt
    return {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": documents}, {"role": "user", "content": get_prompt(query)}],
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_citations.py <query>")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(**get_request_params(query))
    print("Response:")
    print(format_response_with_citations(response))

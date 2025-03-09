#!/usr/bin/env python
"""
Command line tool to print search results from various Ansari search tools.
This tool takes a query and search tool name, and pretty prints the returned value.
"""

import json
from enum import Enum
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel

from ansari.config import get_settings
from ansari.tools.search_hadith import SearchHadith
from ansari.tools.search_mawsuah import SearchMawsuah
from ansari.tools.search_quran import SearchQuran
from ansari.tools.search_tafsir_encyc import SearchTafsirEncyc

# Remove usul import
# Remove vectara import
from ansari.ansari_logger import get_logger

logger = get_logger(__name__)
settings = get_settings()
console = Console()
app = typer.Typer(help="Ansari search tools result printer")


class OutputFormat(str, Enum):
    """Output format options for search results."""

    RAW = "raw"
    STRING = "string"
    LIST = "list"
    FORMATTED = "formatted"
    REF_LIST = "ref_list"


def format_json(data: Any) -> str:
    """Format data as indented JSON for better readability."""
    return json.dumps(data, ensure_ascii=False, indent=2)


def pretty_print_results(results: Any, output_format: str) -> None:
    """Pretty print results based on the specified format."""
    if not results:
        console.print("[bold red]No results found.[/bold red]")
        return

    if output_format == OutputFormat.RAW:
        console.print_json(json.dumps(results))
    elif output_format == OutputFormat.STRING:
        if isinstance(results, str):
            console.print(results)
        else:
            console.print_json(json.dumps(results))
    elif output_format == OutputFormat.LIST:
        if isinstance(results, list):
            for i, item in enumerate(results, 1):
                console.print(Panel(f"{item}", title=f"Result {i}", border_style="blue"))
                console.print()
        else:
            console.print_json(json.dumps(results))
    elif output_format == OutputFormat.REF_LIST:
        if isinstance(results, list):
            # Pretty print the entire ref_list as formatted JSON
            console.print_json(format_json(results))
        else:
            console.print_json(json.dumps(results))
    else:
        if isinstance(results, dict) and "tool_result" in results:
            console.print(Panel(format_json(results["tool_result"]), title="Tool Result", border_style="green"))
            if "response_message" in results:
                console.print(Panel(results["response_message"], title="Response Message", border_style="yellow"))
        else:
            console.print(results)


def create_search_tool(tool_name: str) -> Any:
    """Create and return the appropriate search tool instance based on the tool name."""
    tools = {
        "hadith": lambda: SearchHadith(
            kalimat_api_key=settings.KALEMAT_API_KEY.get_secret_value() if hasattr(settings, "KALEMAT_API_KEY") else ""
        ),
        "mawsuah": lambda: SearchMawsuah(
            vectara_api_key=settings.VECTARA_API_KEY.get_secret_value(), vectara_corpus_key=settings.MAWSUAH_CORPUS_ID
        ),
        "quran": lambda: SearchQuran(
            kalimat_api_key=settings.KALEMAT_API_KEY.get_secret_value() if hasattr(settings, "KALEMAT_API_KEY") else ""
        ),
        "tafsir": lambda: SearchTafsirEncyc(api_token=settings.USUL_API_TOKEN.get_secret_value()),
    }

    if tool_name.lower() not in tools:
        available_tools = ", ".join(tools.keys())
        console.print(f"[bold red]Error:[/bold red] Unknown tool '{tool_name}'")
        console.print(f"Available tools: {available_tools}")
        raise typer.Exit(code=1)

    return tools[tool_name.lower()]()


@app.command()
def main(
    query: str = typer.Argument(..., help="The search query to run"),
    tool_name: str = typer.Option(..., "--tool", "-t", help="The search tool to use"),
    output_format: OutputFormat = typer.Option(OutputFormat.FORMATTED, "--format", "-f", help="Output format"),
):
    """
    Search using the specified tool and print the results.
    """
    try:
        with console.status(f"Searching for '{query}' using {tool_name}..."):
            # Create the appropriate search tool
            search_tool = create_search_tool(tool_name)

            # Run the search
            raw_results = search_tool.run(query)

        # Format based on the specified output format
        if output_format == OutputFormat.RAW:
            results = raw_results
        elif output_format == OutputFormat.STRING:
            if hasattr(search_tool, "run_as_string"):
                results = search_tool.run_as_string(query)
            else:
                # Fallback for tools without run_as_string method
                tool_result = search_tool.format_as_tool_result(raw_results)
                results = format_json(tool_result)
        elif output_format == OutputFormat.LIST:
            if hasattr(search_tool, "format_as_list"):
                results = search_tool.format_as_list(raw_results)
            else:
                results = ["Format not supported for this tool"]
        elif output_format == OutputFormat.REF_LIST:
            if hasattr(search_tool, "format_as_ref_list"):
                results = search_tool.format_as_ref_list(raw_results)
            else:
                results = ["Format not supported for this tool"]
        else:  # formatted
            tool_result = search_tool.format_as_tool_result(raw_results)
            response_message = ""
            if hasattr(search_tool, "format_tool_response"):
                response_message = search_tool.format_tool_response(raw_results)

            results = {"tool_result": tool_result, "response_message": response_message}

        # Print the results
        pretty_print_results(results, output_format)

    except Exception as e:
        logger.exception(f"Error running search: {e}")
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

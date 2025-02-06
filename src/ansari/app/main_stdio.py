# This file aims to process input from standard input and generate answers using a specified LLM model.

import logging
import typer
from typing import Optional

from ansari.agents import Ansari
from ansari.agents.ansari_claude import AnsariClaude
from ansari.config import get_settings
from ansari.presenters.stdio_presenter import StdioPresenter

app = typer.Typer()

@app.command()
def main(
    agent: str = typer.Option(
        "Ansari",
        "--agent",
        "-a",
        help="Agent to use (AnsariClaude or Ansari)"
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        "-l",
        help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        case_sensitive=False
    )
):
    """
    Run the Ansari agent in stdio mode
    """
    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')
    
    logging.basicConfig(level=numeric_level)
    settings = get_settings()
    
    if agent == "AnsariClaude":
        agent_instance = AnsariClaude(settings)
    elif agent == "Ansari":
        agent_instance = Ansari(settings)
    else:
        raise ValueError(f"Unknown agent type: {agent}. Must be one of: AnsariClaude, Ansari")
    
    presenter = StdioPresenter(agent_instance)
    presenter.present()

if __name__ == "__main__":
    app()

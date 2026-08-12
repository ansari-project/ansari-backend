# This file aims to process input from standard input and generate answers using a specified LLM model.

import logging
import typer
from typing import Optional


from ansari.agents import Ansari
from ansari.agents.ansari_claude import AnsariClaude
from ansari.ansari_logger import get_logger
from ansari.config import get_settings
from ansari.presenters.stdio_presenter import StdioPresenter

logger = get_logger(__name__)

app = typer.Typer()


@app.command()
def main(
    agent: str = typer.Option("Ansari", "--agent", "-a", help="Agent to use (AnsariClaude or Ansari)"),
    log_level: str = typer.Option(
        "INFO", "--log-level", "-l", help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)", case_sensitive=False
    ),
    input: Optional[str] = typer.Option(
        None, "--input", "-i", help="Input to send to the agent. If not provided, starts interactive mode."
    ),
    stream: bool = typer.Option(
        False, "--stream", "-s", help="Stream the output word by word. If False, prints the complete answer at once."
    ),
):
    """
    Run the Ansari agent. If input is provided, process it and exit.
    If no input is provided, start interactive mode.
    """
    # Convert log level string to logging constant
    # Get the root logger and set its level to match the CLI argument
    # Note: We don't use logging.basicConfig() to avoid duplicate logs
    # Our custom get_logger() function has already configured the loggers
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {log_level}")

    # Update the logger's level
    logging.getLogger().setLevel(numeric_level)
    # Also update our module's logger level
    logger.setLevel(numeric_level)

    settings = get_settings()

    if agent == "AnsariClaude":
        agent_instance = AnsariClaude(settings)
    elif agent == "Ansari":
        agent_instance = Ansari(settings)
    else:
        raise ValueError(f"Unknown agent type: {agent}. Must be one of: AnsariClaude, Ansari")

    # Print greeting
    print(agent_instance.greet())

    if input:
        # Process single input and exit
        result = agent_instance.process_input(input)
        # Handle the result which could be either a generator or other iterable
        if result:
            print("Model response:")
            if stream:
                # Stream output word by word
                for word in result:
                    print(word, end="", flush=True)
                print()
            else:
                # Collect the entire response and print at once
                complete_response = "".join([word for word in result if word is not None])
                print(complete_response)
    else:
        # No input provided, start interactive mode
        presenter = StdioPresenter(agent_instance, skip_greeting=True, stream=stream)
        presenter.present()


if __name__ == "__main__":
    logger.debug("Starting the Ansari chatbot in terminal (stdio)...")
    app()

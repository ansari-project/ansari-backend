import typer
import logging
from typing import Optional

from ansari.agents import Ansari
from ansari.config import get_settings
from ansari.presenters.file_presenter import FilePresenter
from ansari.presenters.ayah_file_presenter import AyahFilePresenter

logging.basicConfig(
    level=logging.DEBUG,
)


def main(
    input_file: str,
    output_file: str,
    ayah_mode: bool = typer.Option(
        False,
        "--ayah-mode",
        "-a",
        help="Process input as ayah questions (CSV format: surah:ayah,question)",
    ),
    use_query_generation: bool = typer.Option(
        True,
        "--use-query-generation",
        "-q",
        help="Use query generation step in ayah mode",
    ),
    answer_column: str = typer.Option(
        "answer",
        "--answer-column",
        "-c",
        help="Name of the column to store answers in the output CSV (ayah mode only)",
    ),
    system_message: Optional[str] = typer.Option(
        None,
        "--system-message",
        "-s",
        help="The name of the system message file. If not provided, uses default.",
    ),
    model: str = typer.Option(
        "gpt-4",
        "--model",
        "-m",
        help="The LLM model to use (e.g., gpt-4, gpt-3.5-turbo)",
    ),
):
    """
    Process input file and generate answers

    Args:
        input_file: Path to input file
        output_file: Path to output file
        ayah_mode: Whether to process in ayah mode
        use_query_generation: Whether to use query generation
        answer_column: Name of column to store answers
        system_message: The name of the system message file. If not provided, uses default.
        model: The LLM model to use for generating answers
    """
    settings = get_settings()

    if system_message:
        settings.AYAH_SYSTEM_PROMPT_FILE_NAME = system_message

    # Set the model in settings
    settings.MODEL = model

    if ayah_mode:
        presenter = AyahFilePresenter(
            settings=settings, use_query_generation=use_query_generation, answer_column=answer_column
        )
    else:
        ansari = Ansari(settings)
        presenter = FilePresenter(ansari)

    presenter.present(input_file, output_file)


if __name__ == "__main__":
    typer.run(main)

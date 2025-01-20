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
    ayah_mode: Optional[bool] = typer.Option(
        False,
        "--ayah-mode",
        "-a",
        help="Process input as ayah questions (CSV format: surah,ayah,question)",
    ),
    use_query_generation: Optional[bool] = typer.Option(
        False,
        "--use-query-generation",
        "-q",
        help="Use query generation step in ayah mode",
    ),
    answer_column: Optional[str] = typer.Option(
        "answer",
        "--answer-column",
        "-c",
        help="Name of the column to store answers in the output CSV (ayah mode only)",
    ),
):
    """
    Process questions and generate answers.
    
    In regular mode, each line of the input file is treated as a question.
    
    In ayah mode (--ayah-mode):
    - Input: CSV file with columns for surah, ayah, and question
    - Output: CSV file with the same columns plus an additional column for answers
    """
    settings = get_settings()
    
    if ayah_mode:
        presenter = AyahFilePresenter(settings, use_query_generation, answer_column)
    else:
        ansari = Ansari(settings)
        presenter = FilePresenter(ansari)
    
    presenter.present(input_file, output_file)

if __name__ == "__main__":
    typer.run(main)

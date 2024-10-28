import typer

from agents.ansari import Ansari
from config import get_settings
from presenters.file_presenter import FilePresenter

if __name__ == "__main__":
    ansari = Ansari(get_settings())
    typer.run(FilePresenter(ansari).present)

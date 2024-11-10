import typer

from ansari.agents import Ansari
from ansari.config import get_settings
from ansari.presenters.file_presenter import FilePresenter

if __name__ == "__main__":
    ansari = Ansari(get_settings())
    typer.run(FilePresenter(ansari).present)

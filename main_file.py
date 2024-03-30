import typer

from agents.ansari import Ansari
from presenters.file_presenter import FilePresenter

if __name__ == "__main__":
    ansari = Ansari()
    typer.run(FilePresenter(ansari).present)

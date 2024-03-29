import typer
from presenters.file_presenter import FilePresenter
from agents.ansari import Ansari

if __name__ == "__main__":
    ansari = Ansari()
    typer.run(FilePresenter(ansari).present)

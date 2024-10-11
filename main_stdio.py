import logging

from agents.ansari import Ansari
from presenters.stdio_presenter import StdioPresenter

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = Ansari()
    presenter = StdioPresenter(agent)
    presenter.present()

import logging

from agents.ansari import Ansari
from config import get_settings
from presenters.stdio_presenter import StdioPresenter

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = Ansari(get_settings())
    presenter = StdioPresenter(agent)
    presenter.present()

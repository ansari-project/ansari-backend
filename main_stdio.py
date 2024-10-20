import logging

from config import Settings, get_settings
from agents.ansari import Ansari
from presenters.stdio_presenter import StdioPresenter

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = Ansari(get_settings())
    presenter = StdioPresenter(agent)
    presenter.present()

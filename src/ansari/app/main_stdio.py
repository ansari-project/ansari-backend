import logging

from ansari.agents import Ansari
from ansari.config import get_settings
from ansari.presenters.stdio_presenter import StdioPresenter

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = Ansari(get_settings())
    presenter = StdioPresenter(agent)
    presenter.present()

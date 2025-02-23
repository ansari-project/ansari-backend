# This file aims to process input from standard input and generate answers using a specified LLM model.

from ansari.agents import Ansari
from ansari.ansari_logger import get_logger
from ansari.config import get_settings
from ansari.presenters.stdio_presenter import StdioPresenter

logger = get_logger()

if __name__ == "__main__":
    logger.debug("Starting the Ansari chatbot in terminal (stdio)...")
    agent = Ansari(get_settings())
    presenter = StdioPresenter(agent)
    presenter.present()

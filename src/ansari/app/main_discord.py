# This file aims to process input from Discord and generate answers back to Discord using a specified LLM model.

from presenters.discord_presenter import DiscordPresenter

from ansari.agents import Ansari
from ansari.config import get_settings

# This work involves 3 agents, with Ansari as primary.
agent = Ansari(get_settings())
presenter = DiscordPresenter(
    agent,
    token=get_settings().DISCORD_TOKEN.get_secret_value(),
)

# This starts the UI.
presenter.present()

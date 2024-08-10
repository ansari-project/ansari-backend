from agents.ansari import Ansari
from presenters.discord_presenter import DiscordPresenter

from config import get_settings

# This work involves 3 agents, with Ansari as primary.
agent = Ansari()
presenter = DiscordPresenter(
    agent, token=get_settings().DISCORD_TOKEN.get_secret_value()
)

# This starts the UI.
presenter.present()

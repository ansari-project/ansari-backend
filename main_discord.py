from presenters.discord_presenter import DiscordPresenter
from agents.ansari import Ansari
import os


# This work involves 3 agents, with Ansari as primary.
agent = Ansari()
presenter = DiscordPresenter(agent, token=os.getenv("DISCORD_TOKEN"))

# This starts the UI.
presenter.present()

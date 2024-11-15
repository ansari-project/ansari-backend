from ansari.agents import Ansari
from ansari.config import get_settings
from presenters.discord_presenter import DiscordPresenter

# This work involves 3 agents, with Ansari as primary.
agent = Ansari(get_settings())
presenter = DiscordPresenter(
    agent,
    token=get_settings().DISCORD_TOKEN.get_secret_value(),
)

# This starts the UI.
presenter.present()

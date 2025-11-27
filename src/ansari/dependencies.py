"""
Global dependencies for the Ansari application.

This file initializes shared resources like the database connection and the API presenter.
Moving these initializations here avoids circular dependency issues that occur when
routers (like whatsapp_router) try to import these objects from main_api.py while
main_api.py is trying to import the routers.

Best Practice:
Separating instantiation of global objects (Singletons) from the main application entry point
allows them to be imported by any part of the application without triggering the
execution of the main application logic or creating import cycles.
"""

from ansari.agents import Ansari, AnsariClaude
from ansari.ansari_db import AnsariDB
from ansari.config import get_settings
from ansari.presenters.api_presenter import ApiPresenter

# Initialize Database
# This is a singleton instance used throughout the application
db = AnsariDB(get_settings())

# Initialize Agent
# We determine which agent to use based on settings
agent_type = get_settings().AGENT

if agent_type == "Ansari":
    ansari = Ansari(get_settings())
elif agent_type == "AnsariClaude":
    ansari = AnsariClaude(get_settings())
else:
    raise ValueError(f"Unknown agent type: {agent_type}. Must be one of: Ansari, AnsariClaude")

# Initialize Presenter
# The presenter handles the interaction between the API and the Agent
presenter = ApiPresenter(ansari)
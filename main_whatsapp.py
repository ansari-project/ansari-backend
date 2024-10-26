from agents.ansari import Ansari
from config import get_settings
from presenters.whatsapp_presenter import WhatsAppPresenter

# Initialize the agent
agent = Ansari(get_settings())

# Initialize the presenter with the agent and credentials
presenter = WhatsAppPresenter(
    agent,
    access_token=get_settings().WHATSAPP_ACCESS_TOKEN.get_secret_value(),
    phone_number_id=get_settings().WHATSAPP_PHONE_NUMBER_ID,
    version=get_settings().WHATSAPP_VERSION,
)

# Define the webhook to handle incoming messages (don't forget to run the server using uvicorn)
presenter.present()

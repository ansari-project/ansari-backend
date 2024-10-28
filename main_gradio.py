from agents.ansari import Ansari
from config import get_settings
from presenters.gradio_presenter import GradioPresenter

if __name__ == "__main__":
    agent = Ansari(get_settings())
    presenter = GradioPresenter(
        agent,
        app_name="Ansari",
        favicon_path="./favicon.ico",
    )
    presenter.present()

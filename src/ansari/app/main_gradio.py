from ansari.agents import Ansari
from ansari.config import get_settings
from ansari.presenters.gradio_presenter import GradioPresenter

if __name__ == "__main__":
    agent = Ansari(get_settings())
    presenter = GradioPresenter(
        agent,
        app_name="Ansari",
        favicon_path="./favicon.ico",
    )
    presenter.present()

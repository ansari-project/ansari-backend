from hermetic.presenters.gradio_presenter import GradioPresenter
from agents.ansari import Ansari

ta = Ansari()
gp = GradioPresenter(app_name='Ansari')

gp.present(ta)
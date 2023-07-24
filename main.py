from hermetic.presenters.gradio_presenter import GradioPresenter
from agents.ansari_agent import AnsariAgent

ta = AnsariAgent()
gp = GradioPresenter(app_name='Ansari')

gp.present(ta)
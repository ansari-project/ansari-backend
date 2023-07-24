from hermetic.presenters.gradio_presenter import GradioPresenter
from agents.ansari import Ansari
from agents.quran_decider import QuranDecider
from hermetic.core.environment import Environment
from hermetic.stores.file_store import FileStore
from hermetic.core.prompt_mgr import PromptMgr

# Note: I am hoping this will be migrated to a config file
# in the future. But for now this is code-as-configuration. 

env = Environment(presenter = GradioPresenter(app_name='Ansari'),
                  store =  FileStore(root_dir = 'ansari-stores'), 
                  prompt_mgr = PromptMgr(hot_reload=True))

env.add_agent(id = 'ansari', agent = Ansari(env))
env.set_primary_agent('ansari')
env.add_agent(id = 'quran_decider', agent = QuranDecider(env))
env.start()



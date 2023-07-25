from hermetic.presenters.gradio_presenter import GradioPresenter
from agents.ansari import Ansari
from agents.quran_decider import QuranDecider
from agents.query_extractor import QueryExtractor
from tools.kalemat import Kalemat
from hermetic.core.environment import Environment
from hermetic.stores.file_store import FileStore
from hermetic.core.prompt_mgr import PromptMgr

# Note: I am hoping this will be migrated to a config file
# in the future. But for now this is code-as-configuration. 

env = Environment(presenter = GradioPresenter(app_name='Ansari'),
                  store =  FileStore(root_dir = 'ansari-stores'), 
                  prompt_mgr = PromptMgr(hot_reload=True))

# This work involves 3 agents, with Ansari as primary. 
ansari = Ansari(env)
env.set_primary_agent('ansari')
decider = QuranDecider(env)
query_extractor = QueryExtractor(env)

# We also use one tool, which is Kalemat lookup 
kalemat = Kalemat(env)

# This starts the UI. 
env.start()



from hermetic.presenters.gradio_presenter import GradioPresenter
from agents.ansari_langchain import AnsariLangchain
from agents.quran_decider import QuranDecider
from agents.query_extractor import QueryExtractor
from tools.kalemat import Kalemat
from hermetic.core.environment import Environment
from hermetic.stores.file_store import FileStore
from hermetic.core.prompt_mgr import PromptMgr

# Note: I am hoping this will be migrated to a config file
# in the future. But for now this is code-as-configuration. 

CSS ="""
.contain { display: flex; flex-direction: column; }x
#component-0 { height: 100%; }
#chatbot { flex-grow: 1; }
"""

env = Environment(store =  FileStore(root_dir = 'ansari-stores'), 
                  prompt_mgr = PromptMgr(hot_reload=True))

# This work involves 3 agents, with Ansari as primary. 
ansari = AnsariLangchain(env)
env.set_primary_agent('ansari-langchain')
decider = QuranDecider(env)
query_extractor = QueryExtractor(env)

# We also use one tool, which is Kalemat lookup 
kalemat = Kalemat(env)

presenter = GradioPresenter(app_name='Ansari', 
                            favicon_path='./favicon.ico', 
                            env=env)

# This starts the UI. 
presenter.present()



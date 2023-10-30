from hermetic.presenters.stdio_presenter import StdioPresenter
from hermetic.core.prompt_mgr import PromptMgr
from hermetic.core.environment import Environment
from agents.ansari_fn import AnsariFn
from tools.kalemat import Kalemat
from hermetic.core.environment import Environment
from hermetic.stores.file_store import FileStore
from hermetic.core.prompt_mgr import PromptMgr

env = Environment(store =  FileStore(root_dir = 'ansari-stores'), 
                  prompt_mgr = PromptMgr(hot_reload=True))

# This work involves 3 agents, with Ansari as primary. 
kalemat = Kalemat(env)
ansari = AnsariFn(env)


env.set_primary_agent('ansarifn')

sp = StdioPresenter()

sp.present(env)

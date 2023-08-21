from hermetic.presenters.stdio_presenter import StdioPresenter
from agents.ansari import Ansari
from hermetic.core.prompt_mgr import PromptMgr
from hermetic.core.environment import Environment

env = Environment(prompt_mgr=PromptMgr())
aa = Ansari(env)
env.set_primary_agent(aa)
sp = StdioPresenter()

sp.present(env)

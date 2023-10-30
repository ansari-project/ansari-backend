from hermetic.agents.openai_chat_agent import OpenAIChatAgent
from hermetic.core.prompt_mgr import PromptMgr

MODEL = 'gpt-4'
NAME = 'quran_filter'
class QuranFilter(OpenAIChatAgent): 
    def __init__(self, env):
        super().__init__(model = MODEL, environment = env, id=NAME)

        self.env = env
        self.env.add_agent(NAME, self)
        self.filter = self.env.prompt_mgr.bind('filter_relevant_verses')
        
    def process_input
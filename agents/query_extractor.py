from hermetic.agents.openai_chat_agent import OpenAIChatAgent
from hermetic.core.prompt_mgr import PromptMgr
from constants import MODEL, RICH_MODEL

NAME = 'query_extractor'
class QueryExtractor(OpenAIChatAgent): 
    def __init__(self, env):
        super().__init__(model = 'gpt-3.5-turbo', environment = env)
        self.env.add_agent(NAME, self)
        self.extract = self.env.prompt_mgr.bind('extract_query_from_question')
        
    def update_message_history(self, inp): 
        # Add the message with the query in it
        extracted = self.extract.render(question=inp)
        print('extracted is: ', extracted)
        self.message_history.append({
            'role': 'user', 
            'content': extracted
            })


